# Sistema de Control de Proceso de Preparacion de Pasta

Implementacion en curso de la especificacion `Especificacion_Tecnica_Consolidada_v1_4_FINAL.docx`. F0, FT, F1, F2, F3, F4 y F5 estan disponibles.

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

## Operacion De Molienda (F1)

Los modulos `M1`, `M2`, `M3` y `M6` se registran en `POST /api/v1/registros/{modulo}`. La API valida campos industriales y estructurales, conserva la version de limite aplicada, crea desvíos idempotentes y permite cerrar, validar, anular o corregir mediante comandos explícitos. CARGA solo opera su sector y sus borradores; SUPERVISION/ADMIN corrigen y cierran desvíos verificados.

## Dashboard (F2)

Ejecute `docker compose exec api python -m app.cli recalculate-analytics` de forma programada, o `POST /api/v1/analitica/recalcular` como SUPERVISION/ADMIN. `GET /api/v1/kpi` y `GET /api/v1/kpi/pareto-paradas` leen exclusivamente los hechos analíticos reconstruidos y devuelven la hora del último recálculo.

## Operacion De Prensas (F3)

Los modulos `M8`, `M9` y `M10` se cargan en `POST /api/v1/registros/{modulo}` para el sector Prensas. M8 valida la relacion fisica linea-prensa y conserva el recordatorio operativo de descarte de 10 minutos. M9 aplica los limites configurados, incluida la presion L32/D19. M10 exige la grilla completa de 3x3 sectores para cada una de las dos cavidades y todas las prensas de la linea, toma nominal y tolerancia del catalogo de formato activo, y conserva min/max/dispersion.

Las advertencias de dispersion usan exclusivamente las versiones configuradas de L42-L44. Una regla sin `id_desvio` deja una advertencia visible y un limite aplicado, pero no crea un Dxx ni un evento ficticio. El recalculo analitico incorpora vaciados, presion y controles/espesores por linea.

## Operacion Offline

Los formularios F1, F3, F4 y F5 guardan cargas sin conexion en IndexedDB y conservan su `client_uuid`. Al volver la conectividad, la aplicacion reintenta la sincronizacion sin duplicar registros; expone cada cola como `pendiente`, `error` o `conflicto`. Los rechazos 4xx se muestran al operador y no se encolan como si fueran recuperables. Las validaciones industriales y los conflictos de revision siguen resolviendose exclusivamente en backend.

## Trazabilidad MUA (F4)

M4 registra la identidad `MUA-AAAA-MMDD-NN`, el preparador y los componentes declarados. Solo SUPERVISION/ADMIN puede crear una MUA. M5 registra la presencia temporal de una MUA existente en un box; varias MUA pueden coexistir sin calcular proporciones o toneladas.

`POST/PATCH /api/v1/trazabilidad/{mua-box,box-verdes,ksider-silo,silo-linea}` y `POST/PATCH /api/v1/lineas/{linea}/producto-formato` retienen inicio, fin y usuario. Los cambios de box a Verdes, receptor K-Sider y producto/formato cierran el periodo activo anterior. `GET /api/v1/mua/{id}/trazabilidad` devuelve la secuencia cronologica con certeza `CONFIRMADA`, `POTENCIAL` o `INFERIDA`.

La web expone M4/M5 y conserva en IndexedDB las presencias MUA-box que no puedan sincronizarse, con el endpoint y payload originales.

## Mantenimiento (F5)

M7 registra intervenciones de mantenimiento con equipo, responsable, tipo, intervalo, producto/formato vigente opcional y correlaciones explicitas a M6 y desvíos mediante `POST /api/v1/registros/m7` (tambien disponible como `/api/v1/mantenimiento/registros`). Los equipos y productos se administran mediante `/api/v1/mantenimiento/equipos` y `/api/v1/mantenimiento/productos`; los formatos son relaciones versionadas por producto y fecha. Los campos Madirex se retienen como informacion y no generan limites ni desvíos automaticos.

`Pendiente de configuracion: no hay responsables de mantenimiento configurados.`

La interfaz muestra esa sentencia y deshabilita el alta M7 hasta que ADMIN configure una persona activa con el puesto vigente `Mantenimiento`. El backend aplica el mismo filtro para impedir responsables no configurados.

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
