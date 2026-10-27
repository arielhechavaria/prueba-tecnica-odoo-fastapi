from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_odoo
from app.odoo import OdooError

ORDER = ["antes", "durante", "despues"]


class FakeOdoo:
    def __init__(self):
        self.events = {}
        self.next_id = 1
        self.available_args = None

    def _get(self, event_id):
        if event_id not in self.events:
            raise OdooError("not_found", "Record does not exist")
        return self.events[event_id]

    def list_events(self):
        return list(self.events.values())

    def get_event(self, event_id):
        return self._get(event_id)

    def create_event(self, vals):
        event = {"id": self.next_id, "state": "antes", "location": None,
                 "capacity": 0, "description": None, **vals}
        self.events[self.next_id] = event
        self.next_id += 1
        return event

    def update_event(self, event_id, vals):
        self._get(event_id).update(vals)
        return self.events[event_id]

    def delete_event(self, event_id):
        self._get(event_id)
        del self.events[event_id]

    def _advance(self, event_id, source):
        event = self._get(event_id)
        if event["state"] != source:
            raise OdooError("validation", f"cannot move from {event['state']}")
        event["state"] = ORDER[ORDER.index(source) + 1]
        return event

    def start_event(self, event_id):
        return self._advance(event_id, "antes")

    def finish_event(self, event_id):
        return self._advance(event_id, "durante")

    def available_resources(self, start, end):
        self.available_args = (start, end)
        return [{"id": 2, "name": "Ana", "kind": "guide"}]


@pytest.fixture
def fake():
    return FakeOdoo()


@pytest.fixture
def client(fake):
    app.dependency_overrides[get_odoo] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


def create(client, **extra):
    body = {"name": "City tour", "start_date": "2026-11-01T09:00:00Z", **extra}
    return client.post("/events", json=body)


def test_create_event_returns_201_and_starts_in_antes(client):
    response = create(client, location="Madrid", capacity=20)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "City tour"
    assert body["state"] == "antes"
    assert body["location"] == "Madrid"
    assert body["start_date"].startswith("2026-11-01T09:00:00")


def test_create_event_requires_name_and_start_date(client):
    assert client.post("/events", json={"name": "x"}).status_code == 422


def test_state_cannot_be_set_on_create(client):
    body = create(client, state="despues").json()
    assert body["state"] == "antes"


def test_list_and_get_event(client):
    event_id = create(client).json()["id"]
    assert [e["id"] for e in client.get("/events").json()] == [event_id]
    assert client.get(f"/events/{event_id}").json()["name"] == "City tour"


def test_get_missing_event_is_404(client):
    assert client.get("/events/99").status_code == 404


def test_patch_updates_only_sent_fields(client):
    event_id = create(client, location="Madrid").json()["id"]
    body = client.patch(f"/events/{event_id}", json={"name": "Renamed"}).json()
    assert body["name"] == "Renamed"
    assert body["location"] == "Madrid"


def test_patch_cannot_change_state(client):
    event_id = create(client).json()["id"]
    body = client.patch(f"/events/{event_id}", json={"state": "despues"}).json()
    assert body["state"] == "antes"


def test_delete_event_is_204_then_404(client):
    event_id = create(client).json()["id"]
    assert client.delete(f"/events/{event_id}").status_code == 204
    assert client.get(f"/events/{event_id}").status_code == 404


def test_start_then_finish_follow_the_sequence(client):
    event_id = create(client).json()["id"]
    assert client.post(f"/events/{event_id}/start").json()["state"] == "durante"
    assert client.post(f"/events/{event_id}/finish").json()["state"] == "despues"


def test_invalid_transitions_are_409(client):
    event_id = create(client).json()["id"]
    assert client.post(f"/events/{event_id}/finish").status_code == 409
    client.post(f"/events/{event_id}/start")
    assert client.post(f"/events/{event_id}/start").status_code == 409


def test_transition_of_missing_event_is_404(client):
    assert client.post("/events/99/start").status_code == 404


def test_available_resources_passes_range_as_utc(client, fake):
    response = client.get(
        "/resources/available",
        params={"from": "2026-11-01T09:00:00Z", "to": "2026-11-01T18:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json() == [{"id": 2, "name": "Ana", "kind": "guide"}]
    assert fake.available_args == (
        datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 18, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-01T18:00:00Z", "to": "2026-11-01T09:00:00Z"},
        {"from": "2026-11-01T09:00:00Z", "to": "2026-11-01T09:00:00Z"},
        {"from": "2026-11-01T09:00:00Z"},
    ],
)
def test_available_resources_rejects_bad_range(client, params):
    assert client.get("/resources/available", params=params).status_code == 422


def test_health_still_works(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_unexpected_odoo_error_is_502(client, fake):
    def boom():
        raise OdooError("other", "kaboom")

    fake.list_events = boom
    assert client.get("/events").status_code == 502
