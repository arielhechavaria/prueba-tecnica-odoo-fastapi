"""End-to-end API -> Odoo checks. Opt-in because they write to the live database:
    docker compose run --rm --no-deps -e RUN_INTEGRATION=1 api python -m pytest tests/test_integration.py
"""
import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_odoo
from app.odoo import OdooClient, OdooError

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to run"
)

DAY = ("2031-03-01T09:00:00Z", "2031-03-01T18:00:00Z")
INSIDE = {"from": "2031-03-01T10:00:00Z", "to": "2031-03-01T12:00:00Z"}


@pytest.fixture
def odoo():
    http = httpx.Client(base_url=os.environ["ODOO_URL"], timeout=30)
    return OdooClient(
        http,
        os.environ["ODOO_DB"],
        os.environ["ODOO_USER"],
        os.environ["ODOO_PASSWORD"],
    )


@pytest.fixture
def world(odoo):
    """A unique bus plus helpers; everything created is removed afterwards."""
    tag = uuid.uuid4().hex[:8]
    bus_id = odoo.call(
        "tourism.resource", "create", [{"name": f"it-bus-{tag}", "kind": "bus"}], {}
    )
    event_ids = []
    app.dependency_overrides[get_odoo] = lambda: odoo
    api = TestClient(app)

    def new_event(allocate=True):
        body = {"name": f"it-event-{tag}", "start_date": DAY[0]}
        event_id = api.post("/events", json=body).json()["id"]
        event_ids.append(event_id)
        if allocate:
            allocate_bus(event_id)
        return event_id

    def allocate_bus(event_id):
        return odoo.call(
            "tourism.allocation",
            "create",
            [{
                "event_id": event_id,
                "resource_id": bus_id,
                "date_start": "2031-03-01 09:00:00",
                "date_end": "2031-03-01 18:00:00",
            }],
            {},
        )

    def bus_is_available():
        rows = api.get("/resources/available", params=INSIDE).json()
        return any(row["id"] == bus_id for row in rows)

    yield api, new_event, allocate_bus, bus_is_available
    app.dependency_overrides.clear()
    if event_ids:  # allocations cascade with their event
        odoo.call("tourism.event", "unlink", [event_ids], {})
    odoo.call("tourism.resource", "unlink", [[bus_id]], {})


def test_lifecycle_reserves_holds_and_releases_the_resource(world):
    api, new_event, _, bus_is_available = world
    assert bus_is_available()
    event_id = new_event()
    assert not bus_is_available()  # reserved
    assert api.post(f"/events/{event_id}/start").json()["state"] == "durante"
    assert not bus_is_available()  # in use
    assert api.post(f"/events/{event_id}/finish").json()["state"] == "despues"
    assert bus_is_available()  # released


def test_overlapping_allocation_is_rejected_by_odoo(world):
    _, new_event, allocate_bus, _ = world
    new_event()
    other = new_event(allocate=False)
    with pytest.raises(OdooError) as exc:
        allocate_bus(other)
    assert exc.value.kind == "validation"
    assert "ya está asignado" in exc.value.message


def test_invalid_transition_is_409_and_keeps_state(world):
    api, new_event, _, _ = world
    event_id = new_event()
    assert api.post(f"/events/{event_id}/finish").status_code == 409
    assert api.get(f"/events/{event_id}").json()["state"] == "antes"
    api.post(f"/events/{event_id}/start")
    assert api.post(f"/events/{event_id}/start").status_code == 409


def test_finished_event_frees_the_slot_for_a_new_event(world):
    api, new_event, allocate_bus, _ = world
    first = new_event()
    api.post(f"/events/{first}/start")
    api.post(f"/events/{first}/finish")
    allocate_bus(new_event(allocate=False))  # no longer conflicts


def test_missing_event_is_404_through_odoo(world):
    api, *_ = world
    assert api.post("/events/999999/start").status_code == 404
