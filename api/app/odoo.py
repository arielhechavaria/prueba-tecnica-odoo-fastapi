from datetime import datetime, timezone

import httpx

ODOO_FORMAT = "%Y-%m-%d %H:%M:%S"
EVENT_FIELDS = ["name", "start_date", "state", "location", "capacity", "description"]
ERROR_KINDS = {
    "odoo.exceptions.ValidationError": "validation",
    "odoo.exceptions.UserError": "validation",
    "odoo.exceptions.MissingError": "not_found",
}
SESSION_EXPIRED = "odoo.http.SessionExpiredException"


class OdooError(Exception):
    """kind: validation | not_found | auth | other"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def to_odoo(value: datetime) -> str:
    """Odoo stores naive UTC datetimes."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime(ODOO_FORMAT)


def from_odoo(value: str) -> datetime:
    return datetime.strptime(value, ODOO_FORMAT).replace(tzinfo=timezone.utc)


def _event(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "start_date": from_odoo(row["start_date"]),
        "state": row["state"],
        "location": row["location"] or None,
        "capacity": row["capacity"],
        "description": row["description"] or None,
    }


def _to_odoo_vals(vals: dict) -> dict:
    return {k: to_odoo(v) if isinstance(v, datetime) else v for k, v in vals.items()}


class OdooClient:
    """Thin JSON-RPC client; the only place that knows Odoo's wire format."""

    def __init__(self, http: httpx.Client, db: str, user: str, password: str):
        self.http = http
        self.db = db
        self.user = user
        self.password = password
        self._authenticated = False

    def _rpc(self, path: str, params: dict):
        payload = {"jsonrpc": "2.0", "method": "call", "params": params}
        try:
            body = self.http.post(path, json=payload).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OdooError("other", f"Odoo no está disponible: {exc}") from exc
        error = body.get("error")
        if error:
            data = error.get("data", {})
            name = data.get("name", "")
            raise OdooError(
                "session" if name == SESSION_EXPIRED else ERROR_KINDS.get(name, "other"),
                data.get("message") or error.get("message", "Error de Odoo"),
            )
        return body.get("result")

    def _authenticate(self):
        result = self._rpc(
            "/web/session/authenticate",
            {"db": self.db, "login": self.user, "password": self.password},
        )
        if not result.get("uid"):
            raise OdooError("auth", "Odoo rechazó las credenciales configuradas")
        self._authenticated = True

    def call(self, model: str, method: str, args: list, kwargs: dict):
        params = {"model": model, "method": method, "args": args, "kwargs": kwargs}
        for attempt in (1, 2):
            if not self._authenticated:
                self._authenticate()
            try:
                return self._rpc("/web/dataset/call_kw", params)
            except OdooError as exc:
                if exc.kind != "session" or attempt == 2:
                    raise
                self._authenticated = False

    def list_events(self) -> list[dict]:
        rows = self.call("tourism.event", "search_read", [[]], {"fields": EVENT_FIELDS})
        return [_event(row) for row in rows]

    def get_event(self, event_id: int) -> dict:
        rows = self.call(
            "tourism.event",
            "search_read",
            [[("id", "=", event_id)]],
            {"fields": EVENT_FIELDS},
        )
        if not rows:
            raise OdooError("not_found", f"El evento {event_id} no existe")
        return _event(rows[0])

    def create_event(self, vals: dict) -> dict:
        event_id = self.call("tourism.event", "create", [_to_odoo_vals(vals)], {})
        return self.get_event(event_id)

    def update_event(self, event_id: int, vals: dict) -> dict:
        self.call("tourism.event", "write", [[event_id], _to_odoo_vals(vals)], {})
        return self.get_event(event_id)

    def delete_event(self, event_id: int) -> None:
        self.call("tourism.event", "unlink", [[event_id]], {})

    def start_event(self, event_id: int) -> dict:
        self.call("tourism.event", "action_start", [[event_id]], {})
        return self.get_event(event_id)

    def finish_event(self, event_id: int) -> dict:
        self.call("tourism.event", "action_finish", [[event_id]], {})
        return self.get_event(event_id)

    def available_resources(self, start: datetime, end: datetime) -> list[dict]:
        busy = self.call(
            "tourism.allocation",
            "search_read",
            [],
            {
                "domain": [
                    ["status", "!=", "released"],
                    ["date_start", "<", to_odoo(end)],
                    ["date_end", ">", to_odoo(start)],
                ],
                "fields": ["resource_id"],
            },
        )
        busy_ids = sorted({row["resource_id"][0] for row in busy})
        return self.call(
            "tourism.resource",
            "search_read",
            [],
            {"domain": [["id", "not in", busy_ids]], "fields": ["name", "kind"]},
        )
