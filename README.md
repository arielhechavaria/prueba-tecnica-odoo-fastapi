# Tourism events: Odoo + FastAPI

A local `docker compose` stack that models tourism events and the resources
(guides, buses, lodging) they need. Each event moves through `antes` → `durante` →
`despues`, and its state drives the status of its resource allocations.

| Service | What it is | Host port |
| --- | --- | --- |
| `odoo` | Odoo 17 with the `tourism_event` addon (`addons/`) | 8069 |
| `api` | FastAPI app that talks to Odoo over JSON-RPC (`api/`) | 8001 |
| `db` | PostgreSQL 16 (not published) | - |

## Run it

Requires Docker with the Compose plugin.

```bash
cp .env.example .env            # optional: defaults already work
docker compose up -d --build --wait

# One-time: create the database and install the addon
docker compose run --rm --no-deps odoo odoo -d tourism -i tourism_event \
  --without-demo=all --stop-after-init \
  --db_host=db --db_user=odoo --db_password=odoo
docker compose restart odoo
```

- Odoo UI: <http://localhost:8069> (database `tourism`, user `admin`, password `admin`), menu **Tourism**.
- API docs: <http://localhost:8001/docs>.
- Change ports or credentials in `.env`. Stop with `docker compose down` (add `-v` to wipe the data).

### Spanish UI and initial data

The addon ships Spanish translations (`i18n/es.po`) and an initial data file
(`data/seed_data.xml`, `noupdate="1"`, not demo data). A fresh database gets the data on
install; to switch an existing one to Spanish:

```bash
# Load es_ES and refresh the addon translations
docker compose exec -T odoo odoo -d tourism -u tourism_event --load-language=es_ES \
  --stop-after-init --db_host=db --db_user=odoo --db_password=odoo
# Make admin use Spanish (Odoo UI and the messages the API relays from Odoo)
docker compose exec -T db psql -U odoo -d tourism -c \
  "update res_partner set lang='es_ES' where id=(select partner_id from res_users where login='admin')"
docker compose restart odoo
```

The data holds 3 events (one per state, with their guide, bus and lodging allocations):
**Senderismo en la Sierra de Gredos** (`antes`, `reserved`), **Escapada cultural a Toledo**
(`durante`, `in_use`) and **Ruta del vino en la Ribera del Duero** (`despues`, `released`).
Records are created through the normal model `create`, so `tourism.allocation` validation runs on
them. State keys (`antes|durante|despues`, `reserved|in_use|released`, `guide|bus|lodging`) stay
untranslated: they are the API and database contract. `noupdate="1"` means `-u` never overwrites
edits; to reload it, delete the records or recreate the database.

## Try it

Resources and allocations are managed in the Odoo UI (**Tourism → Resources / Allocations**);
the API manages events and reads availability.

```bash
# Create an event (starts in "antes")
curl -s -XPOST localhost:8001/events -H 'content-type: application/json' \
  -d '{"name":"City tour","start_date":"2026-12-01T09:00:00Z","location":"Madrid"}'

# Which resources are free in a time range?
curl -s 'localhost:8001/resources/available?from=2026-12-01T10:00:00Z&to=2026-12-01T12:00:00Z'

# Move the event forward: antes -> durante -> despues
curl -s -XPOST localhost:8001/events/1/start
curl -s -XPOST localhost:8001/events/1/finish
```

| Endpoint | Purpose |
| --- | --- |
| `GET /events`, `GET /events/{id}` | List / read events |
| `POST /events` | Create (`name`, `start_date` required; `location`, `capacity`, `description` optional) |
| `PATCH /events/{id}`, `DELETE /events/{id}` | Update / delete (state cannot be set directly) |
| `POST /events/{id}/start`, `POST /events/{id}/finish` | State transitions |
| `GET /resources/available?from=&to=` | Resources with no active allocation overlapping the range |

Errors: invalid transition or Odoo validation → `409`, unknown event → `404`,
`to` not after `from` → `422`, other Odoo or connection failure → `502`.

## Rules

- Transitions are strictly sequential: `antes → durante → despues`. No going back, no skipping.
- `antes → durante`: the event's `reserved` allocations become `in_use`.
- `durante → despues`: its `in_use` allocations become `released`, freeing the resources.
- A resource cannot have two overlapping non-released allocations. This is validated in
  Odoo with a readable error and also enforced by a PostgreSQL exclusion constraint
  (`btree_gist`) so concurrent transactions cannot double-book.

## Tests

```bash
# Odoo addon (restart Odoo afterwards: running the tests with -u leaves its registry stale)
docker compose exec -T odoo odoo -d tourism -u tourism_event --test-tags /tourism_event \
  --stop-after-init --db_host=db --db_user=odoo --db_password=odoo
docker compose restart odoo

# API unit tests
docker compose run --rm --no-deps api python -m pytest -q

# API -> Odoo integration tests (opt-in: they write to the live database and clean up after)
docker compose run --rm --no-deps -v "$PWD/api/tests:/srv/tests" -e RUN_INTEGRATION=1 \
  api python -m pytest -q
```

## Assumptions to validate

This was built from a conversation about the company's tourism-events tool, not from a
written spec. These points are my interpretation and should be confirmed:

1. **Event attributes**: besides the state, start date and name that were mentioned, I
   assumed `location`, `capacity` and `description`.
2. **State drives allocation**: I understood the `antes | durante | despues` states are
   used for resource allocation, and modelled `antes` = reserve, `durante` = in use,
   `despues` = release.
3. **Resources and double booking**: resources (guide, bus, lodging) are allocated by date
   range and double booking is rejected.

Known limits: allocations are created in Odoo only (the API does not expose them yet),
transitions do not check dates against the event's `start_date`, and there is no authentication
on the API.
