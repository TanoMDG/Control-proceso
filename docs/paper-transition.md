# Transicion Desde Formularios En Papel

FT mantiene una unica fuente de registros operativos. El papel no se replica en un sistema paralelo: se imprime desde `GET /api/v1/exportar?modulo=m1|m2|m3|m6|m10` y se digitaliza en el mismo registro que usara la operacion.

1. Imprima el formulario A4 horizontal y complete identificador, fecha operativa, turno, hora de medicion y responsable.
2. Para el turno `20-04`, asigne a la fecha de inicio las mediciones realizadas entre `00:00` y `03:59`.
3. Al digitar, use el mismo `client_uuid` si debe reintentar una carga offline. La API no duplica el registro.
4. La API fija `origen_dato=papel_digitado`, el usuario digitador y `cargado_en`; no reemplaza el momento original de medicion.

El formulario M10 genera tres paginas, una por prensa. Los datos especificos de cada modulo se validan en el nucleo operativo F1.
