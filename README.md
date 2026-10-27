# Eventos turísticos: Odoo + FastAPI

Prueba técnica. Se me ocurrió usar el escenario de los eventos turísticos
(estados `antes`, `durante`, `despues`, con recursos asignados) para probar la
integración de FastAPI con Odoo: la API en FastAPI habla con el addon `tourism_event` de Odoo por JSON-RPC.

## Cómo levantarlo

Requiere Docker con Compose.

```bash
docker compose up -d --build --wait

# Solo la primera vez: crear la base e instalar el addon (incluye datos iniciales)
docker compose run --rm --no-deps odoo odoo -d tourism -i tourism_event \
  --without-demo=all --stop-after-init \
  --db_host=db --db_user=odoo --db_password=odoo
docker compose restart odoo
```

- Odoo: <http://localhost:8069> (base `tourism`, usuario `admin`, clave `admin`)
- API: <http://localhost:8001/docs>
