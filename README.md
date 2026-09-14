# Sistema de Control de Proceso de Preparacion de Pasta

Implementacion en curso de la especificacion `Especificacion_Tecnica_Consolidada_v1_4_FINAL.docx`. F0, FT, F1, F2, F3, F4, F5, la infraestructura preparatoria F6 y F7 M17 Laboratorio estan disponibles.

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

Las migraciones Alembic se aplican al iniciar el contenedor API. `0013_v101_baseline` instala la configuracion fuente de v1.0.1; no crea usuarios operativos ni sustituye configuracion que ya exista.

## Baseline v1.0.1

La baseline es una carga tecnica trazable de los documentos fuente versionados: guarda nombre y SHA-256 del DOCX/XLSX, catalogos, personas, limites, planes, configuracion de laboratorio y su reporte de reconciliacion en `GET /api/v1/configuracion/baseline` (ADMIN). Cada entidad informa `expected`, `inserted`, `already_existing`, `updated`, `omitted`, `pending` y `conflicts` con los resultados reales de la migracion.

La cuenta tecnica inactiva `system.baseline.v101` solo atribuye las versiones tecnicas iniciales; no permite iniciar sesion ni representa una persona operativa. La migracion solo inserta claves ausentes y nunca ejecuta `UPDATE`: una configuracion creada o modificada despues de v1.0.0 se conserva, se refleja como conflicto u omision y sus cambios posteriores se auditan normalmente.

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

Las cargas que la web soporta offline se guardan en IndexedDB con su `client_uuid`, endpoint, metodo y payload originales. Al volver la conectividad solo se reintentan filas `pendiente`; un 409 queda en `conflicto` para SUPERVISION/ADMIN y un 4xx queda en `error`, sin reintentos ciegos. El service worker precachea el shell, conserva los recursos propios obtenidos durante el uso y nunca cachea rutas `/api/`.

## Trazabilidad MUA (F4)

M4 registra la identidad `MUA-AAAA-MMDD-NN`, el preparador y los componentes declarados. Solo SUPERVISION/ADMIN puede crear una MUA. M5 registra la presencia temporal de una MUA existente en un box; varias MUA pueden coexistir sin calcular proporciones o toneladas.

`POST/PATCH /api/v1/trazabilidad/{mua-box,box-verdes,ksider-silo,silo-linea}` y `POST/PATCH /api/v1/lineas/{linea}/producto-formato` retienen inicio, fin y usuario. Los cambios de box a Verdes, receptor K-Sider y producto/formato cierran el periodo activo anterior. `GET /api/v1/mua/{id}/trazabilidad` devuelve la secuencia cronologica con certeza `CONFIRMADA`, `POTENCIAL` o `INFERIDA`.

La web expone M4/M5 y conserva en IndexedDB las presencias MUA-box que no puedan sincronizarse, con el endpoint y payload originales.

## Mantenimiento (F5)

M7 registra intervenciones de mantenimiento con equipo, responsable, tipo, intervalo, producto/formato vigente opcional y correlaciones explicitas a M6 y desvíos mediante `POST /api/v1/registros/m7` (tambien disponible como `/api/v1/mantenimiento/registros`). Los equipos y productos se administran mediante `/api/v1/mantenimiento/equipos` y `/api/v1/mantenimiento/productos`; los formatos son relaciones versionadas por producto y fecha. Los campos Madirex se retienen como informacion y no generan limites ni desvíos automaticos.

`Pendiente de configuracion: no hay responsables de mantenimiento configurados.`

La interfaz muestra esa sentencia y deshabilita el alta M7 hasta que ADMIN configure una persona activa con el puesto vigente `Mantenimiento`. El backend aplica el mismo filtro para impedir responsables no configurados.

## Infraestructura PLC De Solo Lectura (F6)

F6 no abre conexiones de planta ni implementa protocolos industriales. La unica implementacion disponible es el adaptador `TEST_SIMULATOR`, detras de la interfaz de solo lectura `ReadOnlyPlcAdapter`; no existe ninguna operacion de escritura de PLC.

ADMIN configura explicitamente una fuente y sus tags en `/plc/configuracion`. Cada tag exige metrica, referencia, unidad, factor y offset de escala, intervalo de muestreo y agregacion, retencion de crudo y agregado, turno, sector, estado y, para el simulador, valor/calidad de prueba. No hay IP, protocolo, tag, unidad, escala, frecuencia ni valor de planta precargados.

`POST /api/v1/plc/configuracion/{fuente_id}/simular-lectura` ejecuta manualmente solo el simulador configurado, respeta el intervalo de muestreo, conserva valor crudo, valor escalado, timestamps de fuente/adquisicion y calidad, actualiza agregados por ventana y proyecta lecturas buenas en `hecho_medicion_temporal`. La retencion se aplica en cada muestra. Cada cambio de configuracion y ejecucion del simulador deja auditoria.

SUPERVISION/ADMIN consulta `/api/v1/plc/estado`. El recalculo de KPI preserva los hechos de origen PLC; F6 no programa adquisicion, no conecta a un PLC y no debe habilitarse para operacion hasta una fase posterior aprobada.

F6 software implementado. Puesta en marcha PLC pendiente de datos reales de planta y prueba de lectura autorizada.

## Laboratorio (F7 M17)

P21 registra analisis de laboratorio mediante `POST /api/v1/laboratorio/analisis`; P22 consulta agenda y cumplimiento mediante `GET /api/v1/laboratorio/agenda`. La baseline v1.0.1 carga la configuracion fuente aprobada; ADMIN administra sus unidades, puntos de muestreo, determinaciones numericas o granulometricas, limites existentes, frecuencias versionadas y tamices por torre. Las determinaciones como humedad, residuo, hierro, densidad, fluidez y resistencias solo aparecen cuando esa configuracion existe.

Cada analisis conserva los vinculos opcionales declarados a MUA, registro de stock M3, proceso, silo y producto. Los resultados numericos conservan la version de limite aplicada y crean un desvio solo si la regla/plan de reaccion configurado lo indica. La granulometria exige exactamente los tamices configurados para esa determinacion y punto; no hay mallas implicitas.

`Pendiente de configuracion: faltan puntos, determinaciones, unidades o frecuencias de laboratorio.`

La agenda genera exclusivamente las ocurrencias de las frecuencias configuradas. Una medicion faltante baja cumplimiento y nunca crea un analisis, limite o desvio ficticio. CARGA solo puede operar el sector `Laboratorio` y consultar sus ultimos siete dias; SUPERVISION/ADMIN disponen de historial. P21 se encola offline con su `client_uuid` original.

## Pruebas

```sh
docker compose --profile test run --rm tests
```

## E2E Con Datos Sinteticos

Los E2E no interceptan rutas de negocio ni fabrican tokens. Levantan PostgreSQL, API y frontend reales en el perfil aislado `e2e`; la semilla `app.e2e_seed` solo se permite con `APP_ENV=test`, vacia exclusivamente la base de prueba y crea cuentas y maestros sinteticos `e2e-*`.

```sh
docker compose --profile e2e rm -sf e2e_seed api_e2e web_e2e
docker compose --profile e2e run --build --rm e2e_tests
```

El primer comando fuerza la ejecucion de la semilla en cada corrida sin tocar `db`, sus credenciales ni datos productivos. El perfil publica temporalmente API en `8001` y frontend en `5174`; el ejecutor Playwright consume los servicios por la red Compose.

## Validar El Excel Fuente

```sh
docker compose exec api python -m app.cli import-preview /ruta/al/libro.xlsx
```

La validacion es dry-run: no importa ni modifica datos. Consulte `docs/data-import.md`.

## Entornos Y Seguridad

Use archivos `.env` diferentes para desarrollo, prueba y produccion. `POSTGRES_PASSWORD`, `POSTGRES_TEST_PASSWORD`, `DATABASE_URL`, `JWT_SECRET` y `TEST_JWT_SECRET` son obligatorios en Compose; `.env.example` contiene solo marcadores que deben reemplazarse. La API y la web se ejecutan sin privilegios, con filesystem de solo lectura, sin capacidades Linux adicionales y sin secretos por defecto. Produccion debe configurar HTTPS, respaldos, RPO/RTO, expiracion de sesion/PIN y MFA de ADMIN conforme a la politica de Soporte, que la especificacion deja pendiente.

## Configuracion Productiva Pendiente

La baseline v1.0.1 deja pendientes los responsables reales de mantenimiento, la identificacion definitiva del molinillo de rechazo, productos y relaciones producto-formato, y el calendario/PLC/politicas reales. Antes del despliegue productivo deben configurarse por los flujos ADMIN auditados, sin modificar la baseline.

El commissioning PLC de solo lectura tambien permanece pendiente: red, protocolo, tags, escalas, unidades, frecuencias, calidad y autorizacion de lectura. Las politicas corporativas de despliegue, respaldo, continuidad y seguridad son responsabilidades organizacionales de produccion. Ninguno de estos puntos invalida los flujos manuales de v1.0.0.
