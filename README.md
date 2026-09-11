# Sistema de Control de Proceso de Preparacion de Pasta

Implementacion en curso de la especificacion `Especificacion_Tecnica_Consolidada_v1_4_FINAL.docx`. F0 y la transicion FT estan disponibles.

## Requisitos

- Docker Desktop con Docker Compose v2.
- Puertos locales `5432`, `8000` y `5173` disponibles.

## Inicio local

```sh
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

La API queda en `http://localhost:8000/api/v1/health` y la web en `http://localhost:5173`.

Las migraciones Alembic se aplican al iniciar el contenedor API. No se insertan personas, catalogos, limites ni otros datos productivos.

## Primer administrador

Provea los datos reales autorizados para el primer administrador. No use valores de ejemplo como datos productivos.

```sh
docker compose exec api python -m app.cli bootstrap-admin --legajo "LEGAJO_REAL" --nombre "APELLIDO, Nombre" --usuario "usuario.admin" --password "Una-clave-segura-de-12-caracteres" --sector "Administracion"
```

El comando crea los roles CARGA, SUPERVISION y ADMIN con permisos base de F0/FT y crea la persona/usuario ADMIN solicitados.

## Transicion Desde Papel (FT)

Tras iniciar sesion, la web permite imprimir formularios M1, M2, M3, M6 y M10. Cada hoja se completa con fecha operativa, turno, hora y responsable originales. La digitacion se realiza mediante `POST /api/v1/registros/{modulo}` y conserva el momento de medicion, la fecha operativa, el responsable, el usuario digitador y el momento de carga. Para el turno `20-04`, una medicion entre `00:00` y `03:59` pertenece a la fecha operativa anterior.

## Pruebas

```sh
docker compose --profile test run --rm tests
```

## Validar El Excel Fuente

```sh
docker compose exec api python -m app.cli import-preview /ruta/al/libro.xlsx
```

La validacion es dry-run: no importa ni modifica datos. Consulte `docs/data-import.md`.

## Entornos Y Seguridad

Use archivos `.env` diferentes para desarrollo, prueba y produccion. Nunca suba secretos al repositorio. Produccion debe configurar HTTPS, respaldos, RPO/RTO, expiracion de sesion/PIN y MFA de ADMIN conforme a la politica de Soporte, que la especificacion deja pendiente.
