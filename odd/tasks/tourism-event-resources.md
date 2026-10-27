# Feature: tourism-event-resources
Objective: local Odoo + FastAPI container stack modelling tourism events (antes|durante|despues) with resource allocation per phase.
Branch: feat/tourism-event-resources | Delivery strategy: ask-on-risk | Test runner: TBD (Odoo tests + pytest for FastAPI)

## Specs
- S1: "despliega en tu estacion de trabajo de manera local un container con odoo+fast api" — one `docker compose` stack: Odoo, PostgreSQL, FastAPI.
- S2: Tourism events with "estado:antes|durante|despues", "fecha de inicio", "nombre" and other attributes (assumption: other attributes = location, capacity, description).
- S3: (assumption) The event state drives resource allocation: `antes` reserves, `durante` marks in use, `despues` releases.
- S4: (assumption) Resources (guide, bus, lodging) have allocations by date range; double-booking is rejected.
- S5: FastAPI exposes events CRUD, state transitions and `GET /resources/available?from=&to=`, talking to Odoo via JSON-RPC.
- S6: README documents how to run it and lists S2-S4 as assumptions from the interview, to be validated.

## Tasks
- [x] T1 (S1) inline — docker compose Odoo 17 + PostgreSQL + FastAPI, healthchecks, `.env.example` — suggested model: sonnet — commit: 1ffa6bd
- [x] T2 (S2) inline — Odoo addon `tourism_event`: event model — suggested model: opus — commit: 0c0d0fc
- [x] T3 (S4) inline — resource model + date-range allocations + overlap constraint — suggested model: opus — commit: 611d117
- [ ] T4 (S3) inline — state transitions that drive allocation status — suggested model: opus — commit: pending
- [ ] T5 (S5) inline — FastAPI Odoo client + endpoints — suggested model: sonnet — commit: pending
- [ ] T6 (S2-S5) inline — tests: RED then GREEN, overlap conflicts, invalid transitions — suggested model: sonnet — commit: pending
- [ ] T7 (S6) inline — README with run instructions and assumptions — suggested model: sonnet — commit: pending

## Log
- L1 (2026-10-27, user, verbatim): "Hoy participle en una entrevista de trabajo y todo fue bien entonces tenog que hacer una prueba tecnica y me han pasado lo siguiente : "La prueba es sencilla despliega en tu estacion de trabajo de manera local un container con odoo+fast api" Quiero usar los conceptos del negocio propio que eme contaron hoy en la entrevista. Resulta que ellos tiene entre tantas cosas una herramienta que crea eventos turisticos y ellos tienen estado:antes|durate|despues(de lo que entendi estos estados son para la asignacion de recursos), fecha de inicio, nombre y otros atributos. Bueno vamos a trabajar esta idea para con esto hacer la prueba presentame al menos tres escenarios. La idea no es ahacer una prueba mas es que se note que soy proactivo y mezclo conocimeintos del modelo de negocio con mis habilidades."
- L2 (2026-10-27, user): chose scenario 2 (resource allocation per phase); authorized `git init` and creating this document.
- Progress: git repo initialized on branch feat/tourism-event-resources.
- T1 done (2026-10-27): `docker compose config` OK; `up --build --wait` brought db, odoo, api to healthy; `GET :8001/health` -> `{"status":"ok"}`; Odoo `/web/login` -> 303 (no database yet, expected). Host ports 5432 and 8000 were already taken, so Postgres is not published and the API uses 8001. RED exception: infra task, no runnable test; checked structurally and at runtime. Risk: none.
- T2 done (2026-10-27): created db `tourism` (`-i base`); RED observed (model missing, tests error); GREEN: 4 tests pass via `odoo -d tourism -i tourism_event --test-tags /tourism_event --stop-after-init`. Tightened the required-fields test to `IntegrityError` because `assertRaises(Exception)` passed vacuously in RED. State keys: `antes|durante|despues`. Risk: none.
- Test runner (Odoo): `docker compose exec -T odoo odoo -d tourism -i tourism_event --test-tags /tourism_event --stop-after-init --db_host=db --db_user=odoo --db_password=odoo`
- T3 done (2026-10-27): RED observed (`setUpClass` errored, models missing); GREEN: 12 tests pass (4 event + 8 allocation: kinds, default `reserved`, overlap rejected, back-to-back allowed, other resource allowed, `released` does not block, end after start, moving onto a busy slot rejected). Allocation `status`: `reserved|in_use|released` (T4 drives it). Risk: item 4 (concurrency): the overlap check is a Python `@api.constrains` search, so two concurrent transactions can both pass it and double-book. Not mitigated yet; option: PostgreSQL exclusion constraint (`btree_gist`) as a database-level guard. Decision pending with the user.
- L3 (2026-10-27, user): "agrégala antes de T4" (add the database exclusion constraint before T4).
- T3 hardening done (commit d2cba55): `EXCLUDE USING gist (resource_id WITH =, tsrange(date_start, date_end) WITH &&) WHERE (status <> 'released')`, created in `init()`. RED: raw-SQL overlapping insert was accepted. GREEN: 14 tests pass. Regression found and fixed on the way: the DB constraint fired before the Python `@api.constrains` and surfaced `IntegrityError`/`DataError` instead of `ValidationError`, so the readable validation moved into `create`/`write` (before the INSERT) and the database stays as the race-safe backstop. Limit: no two-connection concurrency test; the guarantee comes from PostgreSQL's constraint, proven by the raw-SQL test. Risk: item 5 (needs the `btree_gist` extension; works with the `postgres:16` image where the DB user is a superuser, and `init()` fails loudly otherwise). Item 4 is mitigated.
- Next: T4 (transitions drive allocation status).
