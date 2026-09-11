# Importacion Del Libro Fuente

La carga productiva no se ejecuta sin el Excel fuente autorizado. No hay valores industriales en migraciones ni en el frontend.

## Validacion sin escritura

Desde el contenedor API:

```sh
docker compose exec api python -m app.cli import-preview /ruta/al/libro.xlsx
```

El comando calcula SHA-256, verifica las hojas `17_Limites`, `18_Listas`, `19_Personas`, `10_Cod_Paradas`, `15_Plan_Reaccion` y `Tabla conversion altura-tn`, comprueba que no esten vacias y no escribe en PostgreSQL.

Un ADMIN autenticado puede ejecutar el mismo dry-run desde `POST /api/v1/importaciones/preview`. La ejecucion se registra en `importacion_datos`, sus errores en `importacion_resultado` y en la auditoria, pero no aplica valores maestros.

La carga de desarrollo usa una cuenta tecnica identificada como `admin.dev` y legajo `99999`, creada sólo mediante el comando de desarrollo autorizado. La persona queda marcada como cuenta técnica DEV y no forma parte del catálogo productivo importado desde `19_Personas`.

La importación se ejecuta transaccionalmente desde el contenedor API. Las 44 versiones iniciales quedan vigentes desde la fecha de importación; no se atribuye retrospectivamente una vigencia que el Excel no provee.

Cuando una celda de `15_Plan_Reaccion` contradice la v1.4 FINAL, el texto normativo se aplica desde el archivo declarativo `app/config/v1_4_final_reaction_overrides.json`. La importación conserva texto Excel, texto normativo y motivo en `importacion_resultado`; esta corrección no se implementa en el motor de reglas.

Los fixtures de prueba se identifican con `TEST-` y solo viven en `apps/api/tests/`.

La aplicacion efectiva de datos quedara habilitada al recibir y validar el libro fuente. No se reemplazara una validacion fallida con valores supuestos.
