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
