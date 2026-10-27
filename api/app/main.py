import os
from datetime import datetime
from functools import lru_cache
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.odoo import OdooClient, OdooError

app = FastAPI(title="Tourism events API")

STATUS_BY_KIND = {"validation": 409, "not_found": 404}


class EventIn(BaseModel):
    name: str
    start_date: datetime
    location: str | None = None
    capacity: int | None = None
    description: str | None = None


class EventPatch(BaseModel):
    name: str | None = None
    start_date: datetime | None = None
    location: str | None = None
    capacity: int | None = None
    description: str | None = None


class EventOut(BaseModel):
    id: int
    name: str
    start_date: datetime
    state: Literal["antes", "durante", "despues"]
    location: str | None
    capacity: int
    description: str | None


class ResourceOut(BaseModel):
    id: int
    name: str
    kind: Literal["guide", "bus", "lodging"]


@lru_cache
def get_odoo() -> OdooClient:
    http = httpx.Client(base_url=os.environ["ODOO_URL"], timeout=30)
    return OdooClient(
        http,
        db=os.environ["ODOO_DB"],
        user=os.environ["ODOO_USER"],
        password=os.environ["ODOO_PASSWORD"],
    )


@app.exception_handler(OdooError)
def odoo_error_handler(_request, exc: OdooError) -> JSONResponse:
    return JSONResponse(
        {"detail": exc.message}, status_code=STATUS_BY_KIND.get(exc.kind, 502)
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/events", response_model=list[EventOut])
def list_events(odoo: OdooClient = Depends(get_odoo)):
    return odoo.list_events()


@app.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventIn, odoo: OdooClient = Depends(get_odoo)):
    return odoo.create_event(body.model_dump(exclude_none=True))


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, odoo: OdooClient = Depends(get_odoo)):
    return odoo.get_event(event_id)


@app.patch("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventPatch, odoo: OdooClient = Depends(get_odoo)):
    return odoo.update_event(event_id, body.model_dump(exclude_unset=True))


@app.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, odoo: OdooClient = Depends(get_odoo)):
    odoo.delete_event(event_id)
    return Response(status_code=204)


@app.post("/events/{event_id}/start", response_model=EventOut)
def start_event(event_id: int, odoo: OdooClient = Depends(get_odoo)):
    return odoo.start_event(event_id)


@app.post("/events/{event_id}/finish", response_model=EventOut)
def finish_event(event_id: int, odoo: OdooClient = Depends(get_odoo)):
    return odoo.finish_event(event_id)


@app.get("/resources/available", response_model=list[ResourceOut])
def available_resources(
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    odoo: OdooClient = Depends(get_odoo),
):
    if end <= start:
        raise HTTPException(422, "'to' must be after 'from'")
    return odoo.available_resources(start, end)
