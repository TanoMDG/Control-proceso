"""Install the v1.0.1 source-backed configuration baseline.

Revision ID: 0013_v101_baseline
Revises: 0012_cp_acceptance_guards
Create Date: 2026-09-13
"""
from datetime import date, datetime, timezone
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert


revision = "0013_v101_baseline"
down_revision = "0012_cp_acceptance_guards"
branch_labels = None
depends_on = None

NAMESPACE = UUID("7c3d53e8-78cd-4a5a-8bb9-ef0cdd42aaf1")
BASELINE = "v1.0.1"
EFFECTIVE_FROM = date(2026, 9, 1)  # Source edition: September 2026.
DOCX_SHA256 = "06959ef39a5dcb47f51020acf11e45a2a09890c3193a6bb1d1a93f5a052dd4cb"
XLSX_SHA256 = "43b7fcde9f8fdabe1241f30715b66edb1fb84662bd4ad1678964b0366dac98e0"


def uid(key: str):
    return uuid5(NAMESPACE, key)


# Values are transcribed from the two versioned sources named in the migration
# provenance. They deliberately exclude source items explicitly marked pending.
LIMITS = [
    ("L01", "Humedad de MUA de entrada", "2. Acopios exteriores", "%", "6", "8", "Rango historico", "M17", "humedad", "ADVERTENCIA", None),
    ("L02", "Humedad de salida del Verdes", "6. Molienda", "%", "2", "3.5", "Especificacion", "M1", "humedad_verdes", "ADVERTENCIA", None),
    ("L03", "Residuo", "6. Molienda", "%", "1.5", "2", "Especificacion", "M1", "residuo", "ADVERTENCIA", "D03"),
    ("L04", "% de aeroseparador", "7. Molienda", "%", "78", "85", "Rango operativo", "M1", "aeroseparador", "ADVERTENCIA", None),
    ("L05", "Hierro de salida del Verdes", "6. Molienda", "g/100 g", None, "0.06", "Especificacion", "M17", "hierro", "ADVERTENCIA", None),
    ("L06", "Hierro del rechazo del desferritizador", "10. Desferritizacion", "g/100 g", "0.5", None, "Provisional", "M17", "hierro", "INFORMATIVO", None),
    ("L07", "Caudal de pasta del Madirex", "11. Madirex", "t/h", None, None, "Referencia", "M2", "caudal_pasta", "INFORMATIVO", None),
    ("L08", "Caudal de agua del Madirex", "11. Madirex", "L/h", None, None, "Referencia", "M2", "caudal_agua", "INFORMATIVO", None),
    ("L09", "Dosificacion especifica de agua", "11. Madirex", "L/t", None, None, "Referencia", "M2", "dosificacion_calc", "INFORMATIVO", None),
    ("L10", "Humedad de salida del Madirex", "11. Madirex", "%", "12.5", "13.5", "Especificacion", "M2", "humedad_salida", "ADVERTENCIA", "D07"),
    ("L11", "Separacion rascador-fondo", "12. Madirex", "cm", "1", "1.5", "Pendiente de confirmar", "M7", "separacion_rascador_fondo", "INFORMATIVO", None),
    ("L12", "Humedad de salida del lecho fluido", "14. Lecho fluido", "%", "7.6", "7.9", "Especificacion", "M3", "humedad", "ADVERTENCIA", "D09"),
    ("L13", "Temperatura del lecho fluido", "14. Lecho fluido", "C", "220", "315", "Rango operativo", "M3", "temperatura", "ADVERTENCIA", None),
    ("L14", "Retenido en malla #12", "14. Lecho fluido", "%", None, "12", "Especificacion", "M17", "granulometria_12", "ADVERTENCIA", None),
    ("L15", "Retenido en malla #30", "14. Lecho fluido", "%", "45", "55", "Especificacion", "M17", "granulometria_30", "ADVERTENCIA", None),
    ("L16", "Retenido en malla #60", "14. Lecho fluido", "%", "25", "35", "Especificacion", "M17", "granulometria_60", "ADVERTENCIA", None),
    ("L17", "Retenido en malla #80", "14. Lecho fluido", "%", "3", "9", "Especificacion", "M17", "granulometria_80", "ADVERTENCIA", None),
    ("L18", "Retenido en malla #120", "14. Lecho fluido", "%", None, "3", "Especificacion", "M17", "granulometria_120", "ADVERTENCIA", None),
    ("L19", "Retenido en malla #230", "14. Lecho fluido", "%", None, "2", "Especificacion", "M17", "granulometria_230", "ADVERTENCIA", None),
    ("L20", "Pasa malla #230", "14. Lecho fluido", "%", None, "1", "Especificacion", "M17", "granulometria_pasa_230", "ADVERTENCIA", None),
    ("L21", "Densidad", "14. Lecho fluido", "-", "0.82", "0.89", "Rango historico", "M17", "densidad", "ADVERTENCIA", None),
    ("L22", "Fluidez", "14. Lecho fluido", "s", "10", "14.5", "Especificacion", "M17", "fluidez", "ADVERTENCIA", None),
    ("L23", "Hierro del lecho fluido", "14. Lecho fluido", "g/100 g", None, "0.06", "Especificacion", "M17", "hierro", "ADVERTENCIA", None),
    ("L24", "% de rechazo del K-Sider", "15. K-Sider", "%", "5", "10", "Rango operativo", "M3", "humedad_ksider", "ADVERTENCIA", None),
    ("L25", "Presion de aire de vibradores", "15. K-Sider", "kg/cm2", None, None, "Referencia", "M7", "presion_vibradores", "INFORMATIVO", None),
    ("L26", "Stock minimo de silo", "16. Silos", "t", "20", None, "Regla operativa", "M3", "toneladas_calculadas", "ADVERTENCIA", "D16"),
    ("L27", "Humedad de silo", "16. Silos", "%", "7.6", "8.2", "Especificacion", "M17", "humedad", "ADVERTENCIA", None),
    ("L28", "Residuo de silo", "16. Silos", "%", "1.5", "2", "Especificacion", "M17", "residuo", "ADVERTENCIA", None),
    ("L29", "Hierro de silo", "16. Silos", "g/100 g", None, "0.06", "Especificacion", "M17", "hierro", "ADVERTENCIA", None),
    ("L30", "% de rechazo del tamiz de prensa", "19. Tamices de prensa", "%", "6", "8", "Rango historico", "M17", "rechazo_tamiz_prensa", "INFORMATIVO", None),
    ("L31", "Humedad de pasta en prensa", "21. Prensado", "%", "7.6", "8.2", "Especificacion", "M9", "humedad_pasta", "ADVERTENCIA", "D18"),
    ("L32", "Presion de prensado", "21. Prensado", "kg/cm2", "210", "270", "Especificacion", "M9", "presion", "ADVERTENCIA", "D19"),
    ("L33", "Espesor formato 64x64", "21. Prensado", "mm", "6.95", "7.25", "Especificacion", "M10", "espesor_mm", "ADVERTENCIA", "D20"),
    ("L34", "Espesor formatos 64x122, 82x82, 45x181 y 21x122", "21. Prensado", "mm", "7.35", "7.65", "Especificacion", "M10", "espesor_mm", "ADVERTENCIA", "D20"),
    ("L35", "Resistencia en verde", "21. Prensado - Producto", "kg/cm2", "8", None, "Especificacion", "M17", "resistencia_verde", "ADVERTENCIA", None),
    ("L36", "Resistencia en seco", "21. Prensado - Producto", "kg/cm2", "25", None, "Especificacion", "M17", "resistencia_seco", "ADVERTENCIA", None),
    ("L37", "Humedad residual tras el secadero", "21. Prensado - Producto", "%", None, "0.75", "Especificacion", "M9", "humedad_residual", "ADVERTENCIA", "D22"),
    ("L38", "Temperatura del quemador del Verdes", "9. Molienda", "C", None, None, "Pendiente de confirmar", "M1", "temperatura_quemador", "INFORMATIVO", None),
    ("L39", "Tiempo de limpieza interna del Madirex", "13. Madirex", "min", None, None, "Referencia", "M7", "duracion_min", "INFORMATIVO", None),
    ("L40", "Tamano nominal de MUA", "4. Preparacion MUA", "t", None, None, "Referencia", "M4", "toneladas_totales", "INFORMATIVO", None),
    ("L41", "% de recuperado sobre MUA", "3. Recuperado", "%", None, None, "Provisional", "M4", "pct_recuperado", "INFORMATIVO", None),
    ("L42", "Dispersion de espesor entre sectores de la placa", "21. Prensado", "mm", None, "0.3", "Especificacion", "M10", "dispersion_sectores", "ADVERTENCIA", None),
    ("L43", "Dispersion de espesor entre cavidades de la misma prensa", "21. Prensado", "mm", None, "0.3", "Especificacion", "M10", "dispersion_cavidades", "ADVERTENCIA", None),
    ("L44", "Dispersion de espesor entre prensas de la misma linea", "21. Prensado", "mm", None, "0.3", "Especificacion", "M10", "dispersion_prensas", "ADVERTENCIA", None),
]

REACTIONS = [
    ("D01", "Humedad de salida del Verdes > 3,5 %", "6. Molienda - Molino Verdes", "2,0-3,5 %", "MUA humeda; quemador insuficiente; caudal alto", "Verificar MUA, elevar quemador y reducir caudal si persiste", "Nueva medicion de humedad a los 30 min", "30 min", "R1; si persiste 2 turnos -> Control de Proceso", "0.5", "Duracion"),
    ("D02", "Humedad de salida del Verdes < 2,0 %", "6. Molienda - Molino Verdes", "2,0-3,5 %", "Sobrecalentamiento; MUA muy seca", "Bajar quemador y verificar MUA", "Nueva medicion de humedad a los 30 min", "30 min", "R1: temperatura anterior, nueva y motivo", "0.5", "Duracion"),
    ("D03", "Residuo fuera de 1,5-2,0 %", "6. Molienda - Molino Verdes", "1,5-2,0 %", "Aeroseparador, rodillos, pista o caudal", "Ajustar aeroseparador y solicitar inspeccion si no corrige", "Nueva medicion de residuo", "30 min", "R1 + aviso a Mantenimiento", "0.5", "Duracion"),
    ("D04", "Hierro > 0,06 g/100 g", "10. Desferritizacion", "<= 0,06 g/100 g", "Desferritizador saturado, sucio o fuera de servicio", "Detener alimentacion; limpiar y verificar", "Nueva muestra de laboratorio", "Turno siguiente", "R6 + informe a Calidad", "8", "Duracion"),
    ("D05", "Hierro del rechazo < 0,5 g/100 g", "10. Desferritizacion", ">= 0,5 g/100 g provisional", "Iman debil, mal posicionado o sucio", "Verificar iman, posicion y limpieza", "Muestra del material de rechazo", "Turno siguiente", "Mantenimiento + Pendientes", "8", "Duracion"),
    ("D06", "Humedad de MUA >= 9 %", "2. Acopios exteriores", "6-8 %", "Lluvia, permanencia exterior o recuperado humedo", "Priorizar MUA interna y compensar con quemador", "Humedad de salida del Verdes", "30 min", "R1/R5 + Laboratorio", "0.5", "Duracion"),
    ("D07", "Humedad de salida del Madirex fuera de 12,5-13,5 %", "11. Madirex", "12,5-13,5 %", "Caudal, rascadores o empaste", "Ajustar agua, verificar pasta y evaluar limpieza", "Medicion a los 30 min", "30 min", "R2; si requiere limpieza -> R7", "0.5", "Duracion"),
    ("D08", "Dosificacion alejada de referencia 237 L/t", "11. Madirex", "Referencia sin tolerancia", "Deriva de caudalimetro o humedad de entrada", "Recalcular agua/pasta y verificar instrumentos", "Calculo automatico", "Cierre del turno", "R2 + Control de Proceso; revision manual", None, "Fin del turno de deteccion"),
    ("D09", "Humedad de salida del lecho fuera de 7,6-7,9 %", "14. Lecho fluido", "7,6-7,9 %", "Temperatura, humedad de entrada o caudal", "Ajustar temperatura dentro de 220-315 C", "Medicion a los 30 min", "30 min", "R3", "0.5", "Duracion"),
    ("D10", "Temperatura del lecho > 315 C", "14. Lecho fluido", "220-315 C", "Ajuste manual excesivo", "Reducir de inmediato al rango", "Lectura de temperatura", "15 min", "R3 + aviso a Produccion", "0.25", "Duracion"),
    ("D11", "Retenido #12 >= 12 %", "14. Lecho fluido / 11. Madirex", "< 12 %", "Discos, aspas o rascadores desgastados", "Inspeccionar Madirex y medir separacion", "Nueva granulometria", "Turno siguiente", "R3 + ficha Madirex", "8", "Duracion"),
    ("D12", "Fluidez > 14,5 s", "14. Lecho fluido", "<= 14,5 s", "Exceso de finos o humedad alta", "Revisar #12/#30 y humedad", "Nuevo ensayo de fluidez", "Turno siguiente", "R3 + Laboratorio", "8", "Duracion"),
    ("D13", "Densidad fuera de 0,82-0,89", "14. Lecho fluido", "0,82-0,89", "Granulometria o humedad", "Revisar curva granulometrica y humedad", "Nueva medicion", "Turno siguiente", "R3", "8", "Duracion"),
    ("D14", "Rechazo K-Sider > 10 %", "15. K-Sider", "5-10 %", "Mallas cegadas, vibracion insuficiente o material grueso", "Verificar aire/vibradores y limpiar mallas", "Nuevo ensayo estandarizado", "Maximo 4 h", "R7 + R3", "4", "Duracion"),
    ("D15", "Rechazo K-Sider < 5 %", "15. K-Sider", "5-10 %", "Malla rota", "Inspeccionar las cuatro mallas y reemplazar", "Inspeccion visual + nuevo ensayo", "15 min", "R7 + Mantenimiento", "0.25", "Duracion"),
    ("D16", "Silo por debajo de 20 t", "16. Silos", ">= 20 t", "Consumo superior o molienda parada", "Cambiar silo en servicio", "Medicion altura -> toneladas", "30 min", "R1-3 + aviso a Prensas", "0.5", "Duracion"),
    ("D17", "Vaciado completo de tolva", "20. Tolvas de prensa", "Sin vaciado", "Falta de alimentacion, parada o silo agotado", "Parada controlada y descarte de 10 min", "Inspeccion de escallas", "Maximo 4 h", "R8 + R6", "4", "Duracion"),
    ("D18", "Humedad de pasta en prensa fuera de 7,6-8,2 %", "21. Prensado", "7,6-8,2 %", "Silo, segregacion o reposo", "Verificar silo y ultima humedad", "Nueva medicion", "30 min", "R9", "0.5", "Duracion"),
    ("D19", "Presion de prensado fuera de 240 +/-30", "21. Prensado", "240 +/-30 kg/cm2", "Ajuste de prensa o humedad", "Corregir ajuste y verificar humedad", "Nueva lectura", "30 min", "R9", "0.5", "Duracion"),
    ("D20", "Espesor fuera de tolerancia", "21. Prensado", "L33/L34", "Presion, humedad o llenado", "Ajustar presion y verificar llenado", "Nueva medicion del formato", "30 min", "R9", "0.5", "Duracion"),
    ("D21", "Resistencia en verde/seco baja", "21. Prensado - Producto", ">= 8 / >= 25", "Humedad, granulometria o presion", "Revisar humedad y presion", "Nuevo ensayo", "Turno siguiente", "Laboratorio + Calidad", "8", "Duracion"),
    ("D22", "Humedad residual >= 0,75 %", "21. Prensado - Producto", "< 0,75 %", "Ciclo de secado o humedad elevada", "Revisar curva del secadero", "Nuevo ensayo", "Turno siguiente", "Laboratorio + Control de Proceso", "8", "Duracion"),
    ("D23", "Paradas repetidas del mismo codigo", "22. Sistema", "Pareto sin causa dominante", "Causa raiz no resuelta", "Escalar a Mantenimiento o Automatizacion", "Pareto de causas", "Cierre del turno", "R6 + reunion diaria", None, "Fin del turno de deteccion"),
]

PEOPLE = [
    ("00001", "Rueda, Martin", "Rueda", None, ("palero",)), ("00002", "Di Leo, Marcelo", "Di Leo", None, ("palero",)),
    ("00003", "Llanos, Daniel", "Llanos", None, ("palero",)), ("00004", "Marquetti, Marcelo", "Marquetti", None, ("palero",)),
    ("00005", "Mogica, Jorge", "Mogica", None, ("operador_molienda", "palero")), ("00006", "Troche, Mario", "Troche", None, ("operador_molienda", "palero")),
    ("00007", "Fernandez, Maximiliano", "FM", None, ("operador_molienda", "palero")), ("00008", "Fernandez, Flavio", "FF", "L7", ("prensero",)),
    ("00009", "Ibarra, Enzo", "Ibarra", "L6", ("prensero",)), ("00010", "Farias, Nicolas", "Farias", "L6", ("prensero",)),
    ("00011", "Prensero 1", "Prensero 1", "L6", ("prensero",)), ("00012", "Prensero 2", "Prensero 2", "L6", ("prensero",)),
    ("00013", "Moreno, Roque", "Moreno", "L7", ("prensero",)), ("00014", "Cuello, Mariano", "Cuello", "L7", ("prensero",)),
    ("00015", "Sos, Hector", "Sos", "L7", ("prensero",)), ("00016", "Pagano, Miguel", "Pag M", None, ("operador_molienda",)),
    ("00017", "Pagano, Gerardo", "Pag G", None, ("operador_molienda",)), ("00018", "Crusse, Maximiliano", "Cru", None, ("operador_molienda",)),
    ("00019", "Gonzalez, Miguel", "Gon", None, ("operador_molienda",)), ("00020", "Villanueva, Federico", "Vill", None, ("operador_molienda",)),
    ("00021", "Ostertag, Mauro", "Ost", None, ("operador_molienda",)), ("00022", "Olivera, Mauricio", "Oli", None, ("operador_molienda",)),
    ("00023", "Masillo, Alejandro", "Mas", None, ("operador_molienda",)),
    *[(f"{number:05d}", name, abbreviation, None, ("supervisor",)) for number, name, abbreviation in [(24, "Guarda, Daniel", "GD"), (25, "Paniagua, Hernan", "PH"), (26, "Damico, Ruben", "DR"), (27, "Marinoni, Gabriel", "Mgab"), (28, "Depetrini, Marcial", "DM"), (29, "Pietrasanta, Julio", "Pju"), (30, "Ostertag, Norberto", "ON"), (31, "Alonso, Marcelo", "AM"), (32, "Palavecino, Jose", "Pjo")]],
    ("00033", "Orden, Leandro", "OL", None, ("laboratorio",)), ("00034", "Cuniolo, Sergio", "CS", None, ("supervisor",)), ("00035", "Gallo, Marcos", "MG", None, ("administracion",)),
]


OUTCOME_FIELDS = ("expected", "inserted", "already_existing", "updated", "omitted", "pending", "conflicts")


def outcome(expected=0, *, omitted=0, pending=0):
    return {field: expected if field == "expected" else omitted if field == "omitted" else pending if field == "pending" else 0 for field in OUTCOME_FIELDS}


def add_if_missing(bind, table, rows, index_elements, outcomes, entity):
    """Insert only absent source rows and record the result of each business key."""
    result = outcomes.setdefault(entity, outcome())
    result["expected"] += len(rows)
    for row in rows:
        criteria = [table.c[column] == row[column] for column in index_elements]
        existing = bind.execute(sa.select(table).where(*criteria)).mappings().first()
        if existing is not None:
            # The migration is never authoritative over a pre-existing row.
            same = all(existing[column] == value for column, value in row.items() if column != "id")
            result["already_existing" if same else "conflicts"] += 1
            continue
        inserted = bind.execute(insert(table).values(row).on_conflict_do_nothing(index_elements=index_elements)).rowcount
        if inserted:
            result["inserted"] += 1
            continue
        # A concurrent install may have inserted the same business key. It is
        # still preserved and reported rather than overwritten.
        existing = bind.execute(sa.select(table).where(*criteria)).mappings().first()
        same = existing is not None and all(existing[column] == value for column, value in row.items() if column != "id")
        result["already_existing" if same else "conflicts"] += 1


def upgrade() -> None:
    bind = op.get_bind()
    outcomes = {}
    tables = set(sa.inspect(bind).get_table_names())
    # 0001 uses Base.metadata.create_all(), so a fresh install sees models added
    # after v1.0.0 before Alembic reaches this revision. Upgrades from 0012 do not.
    if "configuracion_baseline" not in tables:
        op.create_table("configuracion_baseline", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("version", sa.String(20), unique=True, nullable=False), sa.Column("fuente_docx", sa.String(255), nullable=False), sa.Column("sha256_docx", sa.String(64), nullable=False), sa.Column("fuente_xlsx", sa.String(255), nullable=False), sa.Column("sha256_xlsx", sa.String(64), nullable=False), sa.Column("resumen", JSONB, nullable=False), sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    if "reconciliacion_baseline" not in tables:
        op.create_table("reconciliacion_baseline", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("id_baseline", sa.Uuid(), sa.ForeignKey("configuracion_baseline.id", ondelete="RESTRICT"), unique=True, nullable=False), sa.Column("estado", sa.String(20), nullable=False), sa.Column("reporte", JSONB, nullable=False), sa.Column("generado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

    role = sa.table("rol", sa.column("id", sa.Uuid()), sa.column("nombre", sa.String()), sa.column("descripcion", sa.String()), sa.column("activo", sa.Boolean()))
    permission = sa.table("permiso", sa.column("id", sa.Uuid()), sa.column("id_rol", sa.Uuid()), sa.column("modulo", sa.String()), sa.column("accion", sa.String()), sa.column("alcance", sa.String()))
    person = sa.table("persona", sa.column("id", sa.Uuid()), sa.column("legajo", sa.String()), sa.column("apellido_nombre", sa.String()), sa.column("abreviatura", sa.String()), sa.column("id_linea_habitual", sa.Uuid()), sa.column("es_cuenta_tecnica_dev", sa.Boolean()), sa.column("activo", sa.Boolean()), sa.column("fecha_baja", sa.Date()))
    user = sa.table("usuario", sa.column("id", sa.Uuid()), sa.column("id_persona", sa.Uuid()), sa.column("nombre_usuario", sa.String()), sa.column("password_hash", sa.String()), sa.column("id_rol", sa.Uuid()), sa.column("sector", sa.String()), sa.column("activo", sa.Boolean()), sa.column("consulta_remota", sa.Boolean()), sa.column("intentos_fallidos", sa.Integer()), sa.column("bloqueado_hasta", sa.DateTime(timezone=True)))
    catalog = sa.table("catalogo", sa.column("id", sa.Uuid()), sa.column("tipo", sa.String()), sa.column("codigo", sa.String()), sa.column("descripcion", sa.String()), sa.column("atributos", JSONB), sa.column("activo", sa.Boolean()), sa.column("fecha_baja", sa.Date()))
    position = sa.table("persona_puesto", sa.column("id", sa.Uuid()), sa.column("id_persona", sa.Uuid()), sa.column("puesto", sa.String()), sa.column("id_linea", sa.Uuid()), sa.column("vigente_desde", sa.Date()), sa.column("vigente_hasta", sa.Date()))
    limit = sa.table("limite", sa.column("id", sa.String()), sa.column("variable", sa.String()), sa.column("etapa", sa.String()), sa.column("unidad", sa.String()), sa.column("tipo_dato", sa.String()), sa.column("modulo_destino", sa.String()), sa.column("campo_destino", sa.String()), sa.column("referencia_fuente", sa.Text()), sa.column("nota_fuente", sa.Text()))
    limit_version = sa.table("limite_version", sa.column("id", sa.Uuid()), sa.column("id_limite", sa.String()), sa.column("vigente_desde", sa.Date()), sa.column("valor_min", sa.Numeric()), sa.column("valor_max", sa.Numeric()), sa.column("operador_min", sa.String()), sa.column("operador_max", sa.String()), sa.column("nivel", sa.String()), sa.column("id_desvio", sa.String()), sa.column("motivo_cambio", sa.String()), sa.column("id_usuario_alta", sa.Uuid()), sa.column("estado", sa.String()))
    reaction = sa.table("plan_reaccion", sa.column("id_desvio", sa.String()), sa.column("senal", sa.Text()), sa.column("etapa", sa.String()), sa.column("limite_referencia", sa.Text()), sa.column("causas_probables", sa.Text()), sa.column("accion_inmediata", sa.Text()), sa.column("verificacion", sa.Text()), sa.column("plazo_texto", sa.String()), sa.column("registro_escalamiento", sa.Text()), sa.column("plazo_horas", sa.Numeric()), sa.column("tipo_plazo", sa.String()))
    parameter = sa.table("parametro_sistema_version", sa.column("id", sa.Uuid()), sa.column("clave", sa.String()), sa.column("valor", sa.String()), sa.column("unidad", sa.String()), sa.column("vigente_desde", sa.Date()), sa.column("motivo", sa.String()), sa.column("id_usuario", sa.Uuid()))
    equipment = sa.table("equipo_mantenimiento", sa.column("id", sa.Uuid()), sa.column("codigo", sa.String()), sa.column("descripcion", sa.String()), sa.column("sector", sa.String()), sa.column("atributos", JSONB), sa.column("activo", sa.Boolean()), sa.column("fecha_baja", sa.Date()))
    lab_unit = sa.table("laboratorio_unidad", sa.column("id", sa.Uuid()), sa.column("codigo", sa.String()), sa.column("descripcion", sa.String()), sa.column("activo", sa.Boolean()))
    lab_point = sa.table("laboratorio_punto_muestreo", sa.column("id", sa.Uuid()), sa.column("codigo", sa.String()), sa.column("descripcion", sa.String()), sa.column("sector", sa.String()), sa.column("activo", sa.Boolean()))
    lab_determination = sa.table("laboratorio_determinacion", sa.column("id", sa.Uuid()), sa.column("codigo", sa.String()), sa.column("descripcion", sa.String()), sa.column("tipo_resultado", sa.String()), sa.column("activo", sa.Boolean()))
    lab_configuration = sa.table("laboratorio_punto_determinacion", sa.column("id", sa.Uuid()), sa.column("id_punto", sa.Uuid()), sa.column("id_determinacion", sa.Uuid()), sa.column("id_unidad", sa.Uuid()), sa.column("id_limite", sa.String()), sa.column("vigente_desde", sa.Date()), sa.column("activo", sa.Boolean()))
    lab_frequency = sa.table("laboratorio_frecuencia_control", sa.column("id", sa.Uuid()), sa.column("id_configuracion", sa.Uuid()), sa.column("vigente_desde", sa.DateTime(timezone=True)), sa.column("intervalo_horas", sa.Numeric()), sa.column("activo", sa.Boolean()))
    lab_sieve = sa.table("laboratorio_tamiz", sa.column("id", sa.Uuid()), sa.column("torre", sa.String()), sa.column("codigo", sa.String()), sa.column("descripcion", sa.String()), sa.column("activo", sa.Boolean()))
    lab_configuration_sieve = sa.table("laboratorio_configuracion_tamiz", sa.column("id", sa.Uuid()), sa.column("id_configuracion", sa.Uuid()), sa.column("id_tamiz", sa.Uuid()))
    baseline = sa.table("configuracion_baseline", sa.column("id", sa.Uuid()), sa.column("version", sa.String()), sa.column("fuente_docx", sa.String()), sa.column("sha256_docx", sa.String()), sa.column("fuente_xlsx", sa.String()), sa.column("sha256_xlsx", sa.String()), sa.column("resumen", JSONB))
    reconciliation = sa.table("reconciliacion_baseline", sa.column("id", sa.Uuid()), sa.column("id_baseline", sa.Uuid()), sa.column("estado", sa.String()), sa.column("reporte", JSONB))
    audit = sa.table("auditoria", sa.column("id", sa.Uuid()), sa.column("id_usuario", sa.Uuid()), sa.column("tabla", sa.String()), sa.column("id_registro", sa.String()), sa.column("accion", sa.String()), sa.column("valor_nuevo", JSONB), sa.column("motivo", sa.String()))

    roles = {name: uid(f"role:{name}") for name in ("CARGA", "SUPERVISION", "ADMIN")}
    add_if_missing(bind, role, [{"id": value, "nombre": name, "descripcion": f"Rol operativo {name}", "activo": True} for name, value in roles.items()], ["nombre"], outcomes, "roles")
    roles = dict(bind.execute(sa.select(role.c.nombre, role.c.id).where(role.c.nombre.in_(roles))).all())
    permissions = {"CARGA": {"M0": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"), "M2": ("ver",), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"), "M11": ("ver",), "M12": ("ver",), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar")}, "SUPERVISION": {"M0": ("ver", "crear", "editar", "cerrar", "validar", "anular", "tratar", "verificar"), "M2": ("ver", "recalcular"), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"), "M11": ("ver",), "M12": ("ver",), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"), "M14": ("ver",), "M15": ("ver",)}, "ADMIN": {"M0": ("ver", "crear", "editar", "cerrar", "validar", "anular", "tratar", "verificar"), "M2": ("ver", "recalcular"), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"), "M11": ("ver", "crear", "editar"), "M12": ("ver", "crear", "editar"), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"), "M14": ("ver", "crear", "editar"), "M15": ("ver", "crear", "editar", "administrar")}}
    permission_rows = [{"id": uid(f"permission:{role_name}:{module}:{action}"), "id_rol": roles[role_name], "modulo": module, "accion": action, "alcance": "propio_sector" if role_name == "CARGA" else "todo"} for role_name, modules in permissions.items() for module, actions in modules.items() for action in actions]
    add_if_missing(bind, permission, permission_rows, ["id_rol", "modulo", "accion", "alcance"], outcomes, "permisos")

    system_person, system_user = uid("person:system-baseline"), uid("user:system-baseline")
    add_if_missing(bind, person, [{"id": system_person, "legajo": "SISTEMA-BASELINE-1", "apellido_nombre": "Sistema baseline v1.0.1", "es_cuenta_tecnica_dev": False, "activo": False, "fecha_baja": EFFECTIVE_FROM}], ["legajo"], outcomes, "actor_tecnico_persona")
    system_person = bind.scalar(sa.select(person.c.id).where(person.c.legajo == "SISTEMA-BASELINE-1"))
    add_if_missing(bind, user, [{"id": system_user, "id_persona": system_person, "nombre_usuario": "system.baseline.v101", "password_hash": "!disabled-baseline-actor!", "id_rol": roles["ADMIN"], "sector": "Administracion", "activo": False, "consulta_remota": False, "intentos_fallidos": 0}], ["nombre_usuario"], outcomes, "actor_tecnico_usuario")
    system_user = bind.scalar(sa.select(user.c.id).where(user.c.nombre_usuario == "system.baseline.v101"))

    catalog_rows = []
    def catalog_row(kind, code, description=None, attributes=None):
        catalog_rows.append({"id": uid(f"catalog:{kind}:{code}"), "tipo": kind, "codigo": code, "descripcion": description or code, "atributos": attributes, "activo": True, "fecha_baja": None})
    for code in ("4 a 12", "12 a 20", "20 a 4"): catalog_row("turno", code)
    for code in ("1", "2", "3", "6"): catalog_row("box", code)
    catalog_row("linea", "L6", "Linea 6", {"origen_excel": "Linea 6"}); catalog_row("linea", "L7", "Linea 7", {"origen_excel": "Linea 7"})
    catalog_row("prensa", "PH5000-1", "Ph 5000/1", {"linea": "L7"}); catalog_row("prensa", "PH5000-2", "Ph 5000/2", {"linea": "L7"}); catalog_row("prensa", "PH-SITI", "Ph Siti", {"linea": "L6"})
    for code, nominal, limit_id in (("64x64", "7.1", "L33"), ("64x122", "7.5", "L34"), ("82x82", "7.5", "L34"), ("45x181", "7.5", "L34"), ("21x122", "7.5", "L34")): catalog_row("formato", code, code, {"formato_cm": code, "espesor_nominal_mm": nominal, "tolerancia_mm": "0.15", "id_limite_espesor": limit_id})
    for code in ("1", "2"): catalog_row("cavidad", code)
    for number, label in enumerate(("Delantero Izquierdo", "Medio Izquierdo", "Trasero Izquierdo", "Delantero Centro", "Medio Centro", "Trasero Centro", "Delantero Derecho", "Medio Derecho", "Trasero Derecho"), 1): catalog_row("sector", str(number), label, {"origen_lista": label})
    for code in ("VERDES", "MADIREX", "LECHO-FLUIDO", "K-SIDER", "DESFERRITIZADOR", "TAMIZ-PRENSA", "TOLVA-PRENSA", "PRENSA"): catalog_row("equipo", code, code.replace("-", " ").title())
    for silo in range(1, 17): catalog_row("silo", str(silo), f"Silo {silo}", {"linea_fisica": "L7" if silo <= 8 else "L6", "capacidad_t": "72" if silo <= 8 else "84"})
    for code, description, group in (("P01", "Verdes", "Equipo"), ("P02", "Madirex", "Equipo"), ("P03", "Lecho fluido", "Equipo"), ("P04", "K-Sider", "Equipo"), ("P05", "Falta de MUA", "Material"), ("P06", "Silo lleno", "Logistica"), ("P07", "Limpieza", "Programada"), ("P08", "Mantenimiento programado", "Programada"), ("P09", "Mantenimiento correctivo", "No programada"), ("P10", "Electrico / automatizacion", "No programada"), ("P11", "Calidad", "Calidad"), ("P12", "Otro", "Otros")): catalog_row("cod_parada", code, description, {"grupo": group})
    for code in ("Preventiva", "Segun condicion", "Limpieza profunda semanal", "Inspeccion"): catalog_row("tipo_limpieza", code)
    add_if_missing(bind, catalog, catalog_rows, ["tipo", "codigo"], outcomes, "catalogos")

    line_ids = dict(bind.execute(sa.select(catalog.c.codigo, catalog.c.id).where(catalog.c.tipo == "linea", catalog.c.codigo.in_(("L6", "L7")))).all())
    for legajo, name, abbreviation, line, jobs in PEOPLE:
        person_id = uid(f"person:{legajo}")
        add_if_missing(bind, person, [{"id": person_id, "legajo": legajo, "apellido_nombre": name, "abreviatura": abbreviation, "id_linea_habitual": line_ids.get(line), "es_cuenta_tecnica_dev": False, "activo": True, "fecha_baja": None}], ["legajo"], outcomes, "personas")
        person_id = bind.scalar(sa.select(person.c.id).where(person.c.legajo == legajo))
        add_if_missing(bind, position, [{"id": uid(f"position:{legajo}:{job}"), "id_persona": person_id, "puesto": job, "id_linea": line_ids.get(line), "vigente_desde": EFFECTIVE_FROM, "vigente_hasta": None} for job in jobs], ["id"], outcomes, "puestos")

    add_if_missing(bind, limit, [{"id": item[0], "variable": item[1], "etapa": item[2], "unidad": item[3], "tipo_dato": item[6], "modulo_destino": item[7], "campo_destino": item[8], "referencia_fuente": "17_Limites", "nota_fuente": "Baseline v1.0.1; fuente Excel priorizada tras especificacion v1.4 FINAL"} for item in LIMITS], ["id"], outcomes, "limites")
    add_if_missing(bind, reaction, [{"id_desvio": item[0], "senal": item[1], "etapa": item[2], "limite_referencia": item[3], "causas_probables": item[4], "accion_inmediata": item[5], "verificacion": item[6], "plazo_texto": item[7], "registro_escalamiento": item[8], "plazo_horas": item[9], "tipo_plazo": item[10]} for item in REACTIONS], ["id_desvio"], outcomes, "planes_reaccion")
    existing_limit_versions = set(bind.scalars(sa.select(limit_version.c.id_limite)))
    omitted_limit_versions = sum(item[0] in existing_limit_versions for item in LIMITS)
    outcomes["versiones_limites"] = outcome(omitted_limit_versions, omitted=omitted_limit_versions)
    add_if_missing(bind, limit_version, [{"id": uid(f"limit-version:{item[0]}:{EFFECTIVE_FROM}"), "id_limite": item[0], "vigente_desde": EFFECTIVE_FROM, "valor_min": item[4], "valor_max": item[5], "operador_min": ">=" if item[4] is not None else None, "operador_max": "<=" if item[5] is not None else None, "nivel": item[9], "id_desvio": item[10], "motivo_cambio": "Baseline v1.0.1 desde fuente aprobada", "id_usuario_alta": system_user, "estado": "VIGENTE"} for item in LIMITS if item[0] not in existing_limit_versions], ["id"], outcomes, "versiones_limites")
    existing_parameter_keys = set(bind.scalars(sa.select(parameter.c.clave)))
    parameter_rows = [{"id": uid("parameter:ksider-pesada-segundos"), "clave": "ksider_pesada_segundos", "valor": "60", "unidad": "s", "vigente_desde": EFFECTIVE_FROM, "motivo": "Metodo definido en especificacion v1.4 FINAL", "id_usuario": system_user}, {"id": uid("parameter:m8-descarte-minutos"), "clave": "m8_descarte_minutos", "valor": "10", "unidad": "min", "vigente_desde": EFFECTIVE_FROM, "motivo": "Recordatorio definido en especificacion v1.4 FINAL", "id_usuario": system_user}]
    omitted_parameters = sum(item["clave"] in existing_parameter_keys for item in parameter_rows)
    outcomes["parametros_sistema"] = outcome(omitted_parameters, omitted=omitted_parameters)
    add_if_missing(bind, parameter, [item for item in parameter_rows if item["clave"] not in existing_parameter_keys], ["id"], outcomes, "parametros_sistema")
    add_if_missing(bind, equipment, [{"id": uid(f"maintenance-equipment:{code}"), "codigo": code, "descripcion": description, "sector": "Mantenimiento", "atributos": {"origen": "18_Listas"}, "activo": True, "fecha_baja": None} for code, description in (("VERDES", "Verdes"), ("MADIREX", "Madirex"), ("LECHO-FLUIDO", "Lecho fluido"), ("K-SIDER", "K-Sider"), ("DESFERRITIZADOR", "Desferritizador"), ("TAMIZ-PRENSA", "Tamiz de prensa"), ("TOLVA-PRENSA", "Tolva de prensa"), ("PRENSA", "Prensa"))], ["codigo"], outcomes, "equipos_mantenimiento")

    units = {"PCT": ("%", "%"), "HIERRO": ("g-100g", "g/100 g"), "SEG": ("s", "segundos"), "PRESION": ("kg-cm2", "kg/cm2")}
    add_if_missing(bind, lab_unit, [{"id": uid(f"lab-unit:{code}"), "codigo": value[0], "descripcion": value[1], "activo": True} for code, value in units.items()], ["codigo"], outcomes, "unidades_laboratorio")
    unit_ids = dict(bind.execute(sa.select(lab_unit.c.codigo, lab_unit.c.id).where(lab_unit.c.codigo.in_(value[0] for value in units.values()))).all())
    points = {"MUA": "MUA / acopio", "VERDES": "Salida Verdes", "MADIREX": "Salida Madirex", "LECHO": "Salida lecho fluido", "KSIDER": "K-Sider / post tamizado", "SILOS": "Silos", "PRENSA": "Prensa / secadero", "DESFERRITIZADOR": "Desferritizador / filtro"}
    add_if_missing(bind, lab_point, [{"id": uid(f"lab-point:{code}"), "codigo": code, "descripcion": description, "sector": "Laboratorio", "activo": True} for code, description in points.items()], ["codigo"], outcomes, "puntos_laboratorio")
    point_ids = dict(bind.execute(sa.select(lab_point.c.codigo, lab_point.c.id).where(lab_point.c.codigo.in_(points))).all())
    determinations = {"HUMEDAD": ("Humedad", "NUMERICO", "PCT"), "RESIDUO": ("Residuo", "NUMERICO", "PCT"), "HIERRO": ("Hierro", "NUMERICO", "HIERRO"), "GRANULOMETRIA": ("Granulometria", "GRANULOMETRIA", "PCT"), "DENSIDAD": ("Densidad", "NUMERICO", "PCT"), "FLUIDEZ": ("Fluidez", "NUMERICO", "SEG"), "RECHAZO_KSIDER": ("Rechazo K-Sider", "NUMERICO", "PCT"), "RESISTENCIA_VERDE": ("Resistencia en verde", "NUMERICO", "PRESION"), "RESISTENCIA_SECO": ("Resistencia en seco", "NUMERICO", "PRESION"), "HUMEDAD_RESIDUAL": ("Humedad residual", "NUMERICO", "PCT")}
    add_if_missing(bind, lab_determination, [{"id": uid(f"lab-determination:{code}"), "codigo": code, "descripcion": value[0], "tipo_resultado": value[1], "activo": True} for code, value in determinations.items()], ["codigo"], outcomes, "determinaciones_laboratorio")
    determination_ids = dict(bind.execute(sa.select(lab_determination.c.codigo, lab_determination.c.id).where(lab_determination.c.codigo.in_(determinations))).all())
    # The source gives one daily or weekly frequency per point/determination; no
    # schedule is seeded for items it explicitly leaves "segun plan vigente".
    lab_rows = [("MUA", "HUMEDAD", "L01", 24), ("VERDES", "HUMEDAD", "L02", 24), ("VERDES", "RESIDUO", "L03", 24), ("VERDES", "HIERRO", "L05", 24), ("MADIREX", "HUMEDAD", "L10", 24), ("MADIREX", "RESIDUO", None, 24), ("MADIREX", "GRANULOMETRIA", None, 24), ("MADIREX", "HIERRO", None, 24), ("LECHO", "HUMEDAD", "L12", 24), ("LECHO", "GRANULOMETRIA", None, 24), ("LECHO", "HIERRO", "L23", 24), ("LECHO", "DENSIDAD", "L21", 24), ("LECHO", "FLUIDEZ", "L22", 24), ("KSIDER", "HUMEDAD", None, 24), ("KSIDER", "GRANULOMETRIA", None, 24), ("KSIDER", "RESIDUO", None, 24), ("KSIDER", "DENSIDAD", None, 24), ("KSIDER", "HIERRO", None, 24), ("KSIDER", "RECHAZO_KSIDER", "L24", 168), ("SILOS", "HUMEDAD", "L27", 168), ("SILOS", "RESIDUO", "L28", 168), ("SILOS", "GRANULOMETRIA", None, 168), ("SILOS", "DENSIDAD", None, 168), ("SILOS", "HIERRO", "L29", 168), ("PRENSA", "RESISTENCIA_VERDE", "L35", 168), ("PRENSA", "RESISTENCIA_SECO", "L36", 168), ("PRENSA", "HUMEDAD_RESIDUAL", "L37", 168), ("DESFERRITIZADOR", "HIERRO", "L06", 24)]
    configuration_rows = [{"id": uid(f"lab-configuration:{point_code}:{determination_code}"), "id_punto": point_ids[point_code], "id_determinacion": determination_ids[determination_code], "id_unidad": unit_ids[units[determinations[determination_code][2]][0]], "id_limite": limit_id, "vigente_desde": EFFECTIVE_FROM, "activo": True} for point_code, determination_code, limit_id, _ in lab_rows]
    add_if_missing(bind, lab_configuration, configuration_rows, ["id"], outcomes, "configuraciones_laboratorio")
    add_if_missing(bind, lab_frequency, [{"id": uid(f"lab-frequency:{point_code}:{determination_code}"), "id_configuracion": uid(f"lab-configuration:{point_code}:{determination_code}"), "vigente_desde": datetime(2026, 9, 1, tzinfo=timezone.utc), "intervalo_horas": interval, "activo": True} for point_code, determination_code, _, interval in lab_rows], ["id"], outcomes, "frecuencias_laboratorio")
    sieve_codes = ("12", "30", "60", "80", "120", "230", "PASA-230")
    add_if_missing(bind, lab_sieve, [{"id": uid(f"lab-sieve:{code}"), "torre": "Granulometria", "codigo": code, "descripcion": f"Malla {code}" if code != "PASA-230" else "Pasa malla #230", "activo": True} for code in sieve_codes], ["codigo"], outcomes, "tamices_laboratorio")
    sieve_ids = dict(bind.execute(sa.select(lab_sieve.c.codigo, lab_sieve.c.id).where(lab_sieve.c.codigo.in_(sieve_codes))).all())
    granular_configs = [uid(f"lab-configuration:{point_code}:GRANULOMETRIA") for point_code in ("MADIREX", "LECHO", "KSIDER", "SILOS")]
    add_if_missing(bind, lab_configuration_sieve, [{"id": uid(f"lab-configuration-sieve:{configuration_id}:{sieve}"), "id_configuracion": configuration_id, "id_tamiz": sieve_ids[sieve]} for configuration_id in granular_configs for sieve in sieve_codes], ["id"], outcomes, "configuraciones_tamiz")

    baseline_id = uid("baseline:v1.0.1")
    summary = {"catalogos": len(catalog_rows), "personas_fuente": len(PEOPLE), "puestos_fuente": sum(len(item[4]) for item in PEOPLE), "limites": len(LIMITS), "planes_reaccion": len(REACTIONS), "parametros": 2, "equipos_mantenimiento": 8, "puntos_laboratorio": len(points), "determinaciones_laboratorio": len(determinations), "configuraciones_laboratorio": len(lab_rows), "tamices_laboratorio": len(sieve_codes), "sin_usuarios_operativos": True}
    add_if_missing(bind, baseline, [{"id": baseline_id, "version": BASELINE, "fuente_docx": "Especificacion_Tecnica_Consolidada_v1_4_FINAL.docx", "sha256_docx": DOCX_SHA256, "fuente_xlsx": "Especificacion plan control proceso.xlsx", "sha256_xlsx": XLSX_SHA256, "resumen": summary}], ["version"], outcomes, "metadatos_baseline")
    outcomes.update({
        "responsables_mantenimiento": outcome(pending=1),
        "molinillo_rechazo": outcome(pending=1),
        "productos_formato": outcome(pending=1),
        "calendario_plc_politicas": outcome(pending=1),
    })
    report = {"baseline": BASELINE, "estado": "PENDIENTES", "entidades": outcomes, "no_sobrescribe": "Las claves existentes se conservaron; esta migracion no ejecuta UPDATE.", "pendientes_fuente": ["No hay personas con puesto Mantenimiento en 19_Personas.", "Molinillo de rechazo pendiente de identificar/catalogar.", "Productos y relaciones producto-formato pendientes.", "Calendario operativo, PLC/tags y politicas corporativas pendientes."], "limitacion_modelo": "L02 (D01/D02), L24 (D14/D15) y L13 (solo exceso D10) requieren desvio por direccion; limite_version actual admite un unico id_desvio. No se asigno un desvio incorrecto.", "normalizacion_prioridad_docx": "La especificacion normativa usa L6/L7; el Excel muestra Linea 6/Linea 7. Se conservaron como atributo de origen y se uso L6/L7."}
    add_if_missing(bind, reconciliation, [{"id": uid("reconciliation:v1.0.1"), "id_baseline": baseline_id, "estado": "PENDIENTES", "reporte": report}], ["id_baseline"], outcomes, "reconciliacion_baseline")
    add_if_missing(bind, audit, [{"id": uid("audit:v1.0.1"), "id_usuario": system_user, "tabla": "configuracion_baseline", "id_registro": str(baseline_id), "accion": "BASELINE_V101", "valor_nuevo": summary, "motivo": "Carga tecnica idempotente con procedencia y reconciliacion"}], ["id"], outcomes, "auditoria_baseline")


def downgrade() -> None:
    op.drop_table("reconciliacion_baseline")
    op.drop_table("configuracion_baseline")
