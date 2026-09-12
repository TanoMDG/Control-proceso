# Arquitectura F0

F0 usa PostgreSQL como fuente transaccional, FastAPI para reglas y autorizacion, y una PWA React para el puesto de planta. El backend es el unico componente autorizado a validar permisos y reglas de negocio.

## Tiempo y versionado

Los timestamps se almacenan con zona horaria UTC. La fecha operativa se conservara como dato propio de los registros operativos en las fases siguientes. Los intervalos de vigencia se implementan como `[vigente_desde, vigente_hasta_exclusiva)`: el limite superior no pertenece a la version. Esta convencion tecnica elimina solapamientos en el limite entre dos versiones consecutivas.

## Datos maestros

Las migraciones no contienen datos maestros productivos. El primer ADMIN se crea mediante comando explicito con legajo, nombre, usuario y contrasena provistos por el despliegue. Los roles operativos y sus permisos base se crean con ese comando porque son configuracion funcional definida por la especificacion, no datos industriales del Excel.

## Auditoria e integridad

`auditoria` tiene un trigger PostgreSQL que rechaza `UPDATE` y `DELETE`. Las bajas de personas y catalogos son logicas. Las versiones de limites y parametros usan intervalos no solapados; PostgreSQL aplica la invariante para limites y el servicio la aplica para parametros.

## Offline y analitica

`revision_sincronizacion` y `conflicto_sincronizacion` preservan las revisiones de cliente y servidor. Las tablas `hecho_medicion_temporal` y `hecho_turno` son proyecciones reconstruibles y no fuentes de verdad. F0 no calcula KPI ni incorpora registros operativos.

## F6: adquisicion PLC preparatoria

`plc_lectura_fuente` y `plc_lectura_tag` son configuracion ADMIN auditable. Una fuente F6 solo admite `TEST_SIMULATOR`; no se almacenan ni usan IP, endpoint, protocolo o credenciales de planta. Los tags no tienen valores industriales por defecto y requieren unidad, escala, muestreo, agregacion, retencion, turno y sector suministrados por el despliegue.

La interfaz `ReadOnlyPlcAdapter` define exclusivamente `read(tags)` y no ofrece escritura. El simulador devuelve solo los valores de prueba configurados de forma explicita. Las lecturas se almacenan en `plc_lectura_cruda` con instante de fuente, instante de adquisicion, valor crudo/escalado, unidad, calidad y adaptador. `plc_lectura_agregada` conserva min/max/promedio/ultimo valor por ventana; las muestras de calidad distinta de `GOOD` no intervienen en las medidas numericas. La retencion configurada elimina crudo, hechos asociados y agregados vencidos durante una ejecucion del simulador.

Cada lectura buena genera un `hecho_medicion_temporal` de origen `plc_lectura_cruda`, con identificadores de fuente/tag y calidad en el contexto. El recalculo operativo elimina solo sus propios hechos para no borrar esta proyeccion F6. `plc_estado_adquisicion` expone intentos, ultima muestra y error a SUPERVISION, sin activar planificador ni conexion externa.
