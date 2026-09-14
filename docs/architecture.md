# Arquitectura F0-F7

F0 usa PostgreSQL como fuente transaccional, FastAPI para reglas y autorizacion, y una PWA React para el puesto de planta. El backend es el unico componente autorizado a validar permisos y reglas de negocio.

## Tiempo y versionado

Los timestamps se almacenan con zona horaria UTC. La fecha operativa se conservara como dato propio de los registros operativos en las fases siguientes. Los intervalos de vigencia se implementan como `[vigente_desde, vigente_hasta_exclusiva)`: el limite superior no pertenece a la version. Esta convencion tecnica elimina solapamientos en el limite entre dos versiones consecutivas.

## Datos maestros y baseline

`0013_v101_baseline` es la excepcion controlada: materializa la configuracion aprobada de v1.0.1 y conserva los nombres y SHA-256 del DOCX/XLSX de origen en `configuracion_baseline`. El reporte asociado se genera durante la misma transaccion y, por entidad, conserva conteos reales de `expected`, `inserted`, `already_existing`, `updated`, `omitted`, `pending` y `conflicts`.

La migracion inserta solo claves de negocio ausentes con `ON CONFLICT DO NOTHING`; no tiene rutas `UPDATE`. Una fila preexistente igual se informa como `already_existing`, una distinta como `conflicts`, y una version de limite o parametro existente se informa como `omitted`. Por ello una configuracion posterior a v1.0.0 no se reemplaza al actualizar.

`system.baseline.v101` es un usuario ADMIN tecnico, inactivo y sin credenciales utilizables, creado solo para atribuir las versiones iniciales. No es un usuario operativo. El primer ADMIN humano sigue creandose mediante el comando explicito con datos autorizados por el despliegue.

La baseline no convierte en datos inventados los pendientes productivos: responsables de mantenimiento, molinillo de rechazo, productos/formato y calendario, PLC/tags y politicas reales quedan con estado `pending`. Las altas y modificaciones posteriores se realizan mediante servicios ADMIN y escriben `auditoria`; no mutan la procedencia ni el reporte historico de la baseline.

## Auditoria e integridad

`auditoria` tiene un trigger PostgreSQL que rechaza `UPDATE` y `DELETE`. Las bajas de personas y catalogos son logicas. Las versiones de limites y parametros usan intervalos no solapados; PostgreSQL aplica la invariante para limites y el servicio la aplica para parametros.

## Offline y analitica

`revision_sincronizacion` y `conflicto_sincronizacion` preservan las revisiones de cliente y servidor. Las operaciones aceptadas y los cambios de estado incrementan su revision; una reintento obsoleto conserva ambas versiones en un unico conflicto abierto y nunca sobreescribe el registro. La cola PWA usa IndexedDB, conserva `client_uuid`, metodo y ruta original, y no reintenta conflictos ni errores de validacion.

La PWA registra `/sw.js` en produccion. El worker cachea solo el shell estatico y nunca respuestas `/api/`, que siguen siendo fuente de verdad del backend. Las tablas `hecho_medicion_temporal` y `hecho_turno` son proyecciones reconstruibles y no fuentes de verdad.

## Autorizacion

Toda ruta de API se autoriza en backend contra `permiso(modulo, accion, alcance)`, y el alcance completa las reglas de sector y estado del registro. Los permisos base se crean al bootstrap y `0011_authorization_permissions` completa los roles existentes. Un usuario de consulta remota solo puede invocar `GET /api/v1/kpi`; no puede consultar catalogos ni acceder a formularios, administracion o mutaciones.

## Migraciones de estabilizacion

`0001_f0_foundation` conserva exactamente el contenido publicado en `v0.1.0-f0`. Como esa migracion inicial usa el metadata actual, las migraciones historicas posteriores detectan las tablas ya presentes al instalar desde base vacia, manteniendo su DDL original cuando se actualiza una instalacion historica. `0010_stabilization` agrega indices de revision y secuencia; `0011_authorization_permissions` agrega permisos base faltantes sin eliminar permisos existentes. El rollback es soportado para la estructura; el downgrade de `0011` no revoca grants que puedan haber sido administrados antes de la migracion.

## F6: adquisicion PLC preparatoria

`plc_lectura_fuente` y `plc_lectura_tag` son configuracion ADMIN auditable. Una fuente F6 solo admite `TEST_SIMULATOR`; no se almacenan ni usan IP, endpoint, protocolo o credenciales de planta. Los tags no tienen valores industriales por defecto y requieren unidad, escala, muestreo, agregacion, retencion, turno y sector suministrados por el despliegue.

La interfaz `ReadOnlyPlcAdapter` define exclusivamente `read(tags)` y no ofrece escritura. El simulador devuelve solo los valores de prueba configurados de forma explicita. Las lecturas se almacenan en `plc_lectura_cruda` con instante de fuente, instante de adquisicion, valor crudo/escalado, unidad, calidad y adaptador. `plc_lectura_agregada` conserva min/max/promedio/ultimo valor por ventana; las muestras de calidad distinta de `GOOD` no intervienen en las medidas numericas. La retencion configurada elimina crudo, hechos asociados y agregados vencidos durante una ejecucion del simulador.

Cada lectura buena genera un `hecho_medicion_temporal` de origen `plc_lectura_cruda`, con identificadores de fuente/tag y calidad en el contexto. El recalculo operativo elimina solo sus propios hechos para no borrar esta proyeccion F6. `plc_estado_adquisicion` expone intentos, ultima muestra y error a SUPERVISION, sin activar planificador ni conexion externa.

## F7: laboratorio configurable

`laboratorio_punto_muestreo`, `laboratorio_determinacion`, `laboratorio_unidad`, `laboratorio_punto_determinacion` y `laboratorio_frecuencia_control` son maestros versionados. La baseline v1.0.1 materializa las filas aprobadas por fuente; sus vigencias, no valores por defecto de la aplicacion, definen que puede registrar P21 y que espera P22. Una determinacion es numerica o granulometrica; `laboratorio_configuracion_tamiz` hace explicita la torre permitida por punto/determinacion.

`analisis_laboratorio` conserva UUID de idempotencia, revision/estado, instante de muestra y vinculos declarados opcionales a MUA, stock M3, proceso, silo y producto activo. Cada resultado numerico retiene la version de limite aplicada en `registro_limite_aplicado`; `evento_desvio_laboratorio` existe solo si ese limite tiene un plan de reaccion configurado. Las ocurrencias faltantes de agenda no crean ninguno de los dos. El recalculo proyecta las mediciones y conteos F7 sin convertir los hechos analiticos en fuente de verdad.
