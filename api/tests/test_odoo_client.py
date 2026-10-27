import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.odoo import OdooClient, OdooError


def make_client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://odoo")
    return OdooClient(http, db="tourism", user="admin", password="admin")


def rpc_result(result):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


def rpc_error(name, message):
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": 200, "message": "Odoo Server Error",
                      "data": {"name": name, "message": message}},
        },
    )


class Recorder:
    """Answers authenticate, then call_kw with queued replies; records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append((request.url.path, body["params"]))
        if request.url.path == "/web/session/authenticate":
            return rpc_result({"uid": 2})
        return self.replies.pop(0)


def test_authenticates_once_and_calls_call_kw():
    rec = Recorder(rpc_result([]), rpc_result([]))
    client = make_client(rec)
    client.call("tourism.event", "search_read", [[]], {"fields": ["name"]})
    client.call("tourism.event", "search_read", [[]], {})
    paths = [path for path, _ in rec.requests]
    assert paths == [
        "/web/session/authenticate",
        "/web/dataset/call_kw",
        "/web/dataset/call_kw",
    ]
    assert rec.requests[0][1] == {"db": "tourism", "login": "admin", "password": "admin"}
    assert rec.requests[1][1] == {
        "model": "tourism.event",
        "method": "search_read",
        "args": [[]],
        "kwargs": {"fields": ["name"]},
    }


def test_reauthenticates_once_when_session_expired():
    rec = Recorder(
        rpc_error("odoo.http.SessionExpiredException", "expired"), rpc_result([1])
    )
    client = make_client(rec)
    assert client.call("tourism.event", "search", [[]], {}) == [1]
    assert [p for p, _ in rec.requests].count("/web/session/authenticate") == 2


@pytest.mark.parametrize(
    "name,kind",
    [
        ("odoo.exceptions.ValidationError", "validation"),
        ("odoo.exceptions.MissingError", "not_found"),
        ("odoo.exceptions.AccessError", "other"),
    ],
)
def test_odoo_errors_are_classified(name, kind):
    client = make_client(Recorder(rpc_error(name, "boom")))
    with pytest.raises(OdooError) as exc:
        client.call("tourism.event", "action_start", [[1]], {})
    assert exc.value.kind == kind
    assert exc.value.message == "boom"


def test_wrong_credentials_raise_auth_error():
    def handler(request):
        return rpc_result({"uid": False})

    with pytest.raises(OdooError) as exc:
        make_client(handler).call("tourism.event", "search", [[]], {})
    assert exc.value.kind == "auth"


def test_get_event_missing_is_not_found_and_fields_are_normalized():
    row = {"id": 7, "name": "Tour", "start_date": "2026-11-01 09:00:00",
           "state": "antes", "location": False, "capacity": 0, "description": False}
    client = make_client(Recorder(rpc_result([row]), rpc_result([])))
    event = client.get_event(7)
    assert event["location"] is None and event["description"] is None
    assert event["start_date"] == datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    with pytest.raises(OdooError) as exc:
        client.get_event(8)
    assert exc.value.kind == "not_found"


def test_create_event_sends_utc_naive_string():
    rec = Recorder(rpc_result(5), rpc_result([{"id": 5, "name": "T", "state": "antes",
        "start_date": "2026-11-01 09:00:00", "location": False, "capacity": 0,
        "description": False}]))
    client = make_client(rec)
    client.create_event({"name": "T", "start_date": datetime(2026, 11, 1, 11, tzinfo=timezone(timedelta(hours=2)))})
    create_params = rec.requests[1][1]
    assert create_params["method"] == "create"
    assert create_params["args"] == [{"name": "T", "start_date": "2026-11-01 09:00:00"}]


def test_available_resources_excludes_resources_with_active_overlap():
    rec = Recorder(
        rpc_result([{"resource_id": [1, "Bus 1"]}, {"resource_id": [1, "Bus 1"]}]),
        rpc_result([{"id": 2, "name": "Ana", "kind": "guide"}]),
    )
    client = make_client(rec)
    start = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    end = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
    assert client.available_resources(start, end) == [
        {"id": 2, "name": "Ana", "kind": "guide"}
    ]
    alloc = rec.requests[1][1]
    assert alloc["model"] == "tourism.allocation"
    assert alloc["kwargs"]["domain"] == [
        ["status", "!=", "released"],
        ["date_start", "<", "2026-11-01 18:00:00"],
        ["date_end", ">", "2026-11-01 09:00:00"],
    ]
    res = rec.requests[2][1]
    assert res["model"] == "tourism.resource"
    assert res["kwargs"]["domain"] == [["id", "not in", [1]]]


def test_method_returning_none_has_no_result_key():
    # Odoo omits "result" when a method (e.g. action_start) returns None.
    rec = Recorder(httpx.Response(200, json={"jsonrpc": "2.0", "id": None}))
    assert make_client(rec).call("tourism.event", "action_start", [[1]], {}) is None
