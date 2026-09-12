from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    device_uuid: UUID | None = None


class TokenOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class PersonInput(BaseModel):
    legajo: str = Field(min_length=1, max_length=20)
    apellido_nombre: str = Field(min_length=1, max_length=120)
    abreviatura: str | None = Field(default=None, max_length=15)


class PersonPatch(BaseModel):
    legajo: str | None = Field(default=None, min_length=1, max_length=20)
    apellido_nombre: str | None = Field(default=None, min_length=1, max_length=120)
    abreviatura: str | None = Field(default=None, max_length=15)
    activo: bool | None = None
    fecha_baja: date | None = None


class PersonOutput(ORMModel):
    id: UUID
    legajo: str
    apellido_nombre: str
    abreviatura: str | None
    activo: bool
    fecha_baja: date | None


class PositionInput(BaseModel):
    puesto: str = Field(min_length=1, max_length=40)
    id_linea: UUID | None = None
    vigente_desde: date
    vigente_hasta: date | None = None


class UserInput(BaseModel):
    id_persona: UUID
    nombre_usuario: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    id_rol: UUID
    sector: str = Field(min_length=1, max_length=40)
    consulta_remota: bool = False


class UserPatch(BaseModel):
    id_rol: UUID | None = None
    sector: str | None = Field(default=None, min_length=1, max_length=40)
    activo: bool | None = None
    consulta_remota: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)


class UserOutput(ORMModel):
    id: UUID
    id_persona: UUID
    nombre_usuario: str
    id_rol: UUID
    sector: str
    activo: bool
    consulta_remota: bool


class RoleOutput(ORMModel):
    id: UUID
    nombre: str
    descripcion: str | None
    activo: bool


class PermissionInput(BaseModel):
    modulo: str = Field(min_length=1, max_length=30)
    accion: str = Field(min_length=1, max_length=20)
    alcance: str = Field(min_length=1, max_length=30)


class CatalogInput(BaseModel):
    tipo: str = Field(min_length=1, max_length=40)
    codigo: str = Field(min_length=1, max_length=30)
    descripcion: str = Field(min_length=1, max_length=120)
    atributos: dict | None = None


class CatalogPatch(BaseModel):
    descripcion: str | None = Field(default=None, min_length=1, max_length=120)
    atributos: dict | None = None
    activo: bool | None = None
    fecha_baja: date | None = None


class CatalogOutput(ORMModel):
    id: UUID
    tipo: str
    codigo: str
    descripcion: str
    atributos: dict | None
    activo: bool
    fecha_baja: date | None


class LimitInput(BaseModel):
    id: str = Field(min_length=1, max_length=10)
    variable: str = Field(min_length=1, max_length=120)
    etapa: str = Field(min_length=1, max_length=80)
    unidad: str = Field(min_length=1, max_length=20)
    tipo_dato: str = Field(min_length=1, max_length=50)
    modulo_destino: str | None = None
    campo_destino: str | None = None


class LimitVersionInput(BaseModel):
    vigente_desde: date
    vigente_hasta_exclusiva: date | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    operador_min: str | None = None
    operador_max: str | None = None
    nivel: str = Field(pattern="^(ADVERTENCIA|INFORMATIVO)$")
    id_desvio: str | None = None
    motivo_cambio: str = Field(min_length=1, max_length=200)


class LimitOutput(ORMModel):
    id: str
    variable: str
    etapa: str
    unidad: str
    tipo_dato: str
    modulo_destino: str | None
    campo_destino: str | None


class LimitVersionOutput(ORMModel):
    id: UUID
    id_limite: str
    vigente_desde: date
    vigente_hasta_exclusiva: date | None
    valor_min: Decimal | None
    valor_max: Decimal | None
    operador_min: str | None
    operador_max: str | None
    nivel: str
    id_desvio: str | None
    motivo_cambio: str
    estado: str


class ParameterInput(BaseModel):
    clave: str = Field(min_length=1, max_length=80)
    valor: str = Field(min_length=1, max_length=120)
    unidad: str | None = Field(default=None, max_length=20)
    vigente_desde: date
    vigente_hasta_exclusiva: date | None = None
    motivo: str = Field(min_length=1, max_length=200)


class CalendarInput(BaseModel):
    fecha_operativa: date
    turno_codigo: str = Field(min_length=1, max_length=30)
    programado: bool
    horas_programadas: Decimal | None = Field(default=None, ge=0)
    motivo: str | None = Field(default=None, max_length=200)


class CalendarOutput(ORMModel):
    id: UUID
    fecha_operativa: date
    turno_codigo: str
    programado: bool
    horas_programadas: Decimal | None
    motivo: str | None


class AuditOutput(ORMModel):
    id: UUID
    id_usuario: UUID | None
    tabla: str
    id_registro: str
    accion: str
    valor_anterior: dict | None
    valor_nuevo: dict | None
    motivo: str | None
    creado_en: datetime


class SyncConflictOutput(ORMModel):
    id: UUID
    tabla: str
    id_registro: UUID
    client_uuid: UUID
    revision_cliente: dict
    version_servidor: dict
    detectado_en: datetime
    estado: str
    resuelto_por: UUID | None
    resolucion: str | None


class SyncConflictResolution(BaseModel):
    resolucion: str = Field(min_length=1, max_length=500)


class ImportPreview(BaseModel):
    filename: str
    sha256: str
    valid: bool
    sheets_found: list[str]
    missing_sheets: list[str]
    rows_by_sheet: dict[str, int]
    errors: list[str]


class DeferredRecordInput(BaseModel):
    client_uuid: UUID = Field(default_factory=uuid4)
    fecha_operativa: date
    turno_codigo: str = Field(min_length=1, max_length=30)
    instante_medicion: datetime
    id_responsable: UUID | None = None
    datos: dict = Field(default_factory=dict)
    origen_dato: str = Field(default="papel_digitado", pattern="^(digital_directo|papel_digitado)$")


class RecordUpdateInput(BaseModel):
    revision: int = Field(ge=1)
    datos: dict
    motivo_correccion: str | None = Field(default=None, max_length=300)


class RecordActionInput(BaseModel):
    comentario: str = Field(min_length=1, max_length=500)


class ShiftReceiptInput(BaseModel):
    observacion: str | None = Field(default=None, max_length=500)


class MuaComponentInput(BaseModel):
    componente: str = Field(min_length=1, max_length=120)
    referencia: str | None = Field(default=None, max_length=120)
    observacion: str | None = Field(default=None, max_length=300)


class MuaCreateInput(BaseModel):
    fecha_generacion: date = Field(default_factory=date.today)
    id_preparador: UUID
    composicion: list[MuaComponentInput] = Field(min_length=1)


class MuaOutput(ORMModel):
    id: UUID
    codigo: str
    fecha_generacion: date
    id_preparador: UUID
    composicion: list[dict]
    creado_por: UUID


class TemporalStartInput(BaseModel):
    desde: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TemporalCloseInput(BaseModel):
    hasta: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MuaBoxStartInput(TemporalStartInput):
    id_mua: UUID
    box: str = Field(min_length=1, max_length=30)
    certeza: str = Field(default="CONFIRMADA", pattern="^(CONFIRMADA|POTENCIAL|INFERIDA)$")


class BoxVerdesStartInput(TemporalStartInput):
    box: str = Field(min_length=1, max_length=30)


class KsiderSiloStartInput(TemporalStartInput):
    receptor: str = Field(default="K-SIDER", min_length=1, max_length=30)
    silo: int = Field(ge=1, le=16)


class SiloLineStartInput(TemporalStartInput):
    silo: int = Field(ge=1, le=16)
    linea: str = Field(pattern="^(L6|L7)$")


class LineProductFormatStartInput(TemporalStartInput):
    linea: str = Field(pattern="^(L6|L7)$")
    producto: str = Field(min_length=1, max_length=80)
    formato: str = Field(min_length=1, max_length=80)


class TemporalPeriodOutput(ORMModel):
    id: UUID
    desde: datetime
    hasta: datetime | None
    id_usuario_inicio: UUID
    id_usuario_fin: UUID | None


class MuaBoxPeriodOutput(TemporalPeriodOutput):
    id_mua: UUID
    box: str
    certeza: str


class MuaListOutput(MuaOutput):
    presencias_activas: list[MuaBoxPeriodOutput] = Field(default_factory=list)
    orden_fifo: int | None = None


class BoxVerdesPeriodOutput(TemporalPeriodOutput):
    box: str


class KsiderSiloPeriodOutput(TemporalPeriodOutput):
    receptor: str
    silo: int


class SiloLinePeriodOutput(TemporalPeriodOutput):
    silo: int
    linea: str


class LineProductFormatPeriodOutput(TemporalPeriodOutput):
    linea: str
    producto: str
    formato: str


class MaintenanceEquipmentInput(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    descripcion: str = Field(min_length=1, max_length=160)
    sector: str = Field(min_length=1, max_length=40)
    atributos: dict = Field(default_factory=dict)


class MaintenanceEquipmentPatch(BaseModel):
    descripcion: str | None = Field(default=None, min_length=1, max_length=160)
    sector: str | None = Field(default=None, min_length=1, max_length=40)
    atributos: dict | None = None
    activo: bool | None = None
    fecha_baja: date | None = None


class MaintenanceEquipmentOutput(ORMModel):
    id: UUID
    codigo: str
    descripcion: str
    sector: str
    atributos: dict
    activo: bool
    fecha_baja: date | None


class MaintenanceProductInput(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    descripcion: str = Field(min_length=1, max_length=160)


class MaintenanceProductPatch(BaseModel):
    descripcion: str | None = Field(default=None, min_length=1, max_length=160)
    activo: bool | None = None
    fecha_baja: date | None = None


class MaintenanceProductOutput(ORMModel):
    id: UUID
    codigo: str
    descripcion: str
    activo: bool
    fecha_baja: date | None


class MaintenanceProductFormatVersionInput(BaseModel):
    id_formato: UUID
    vigente_desde: date
    vigente_hasta_exclusiva: date | None = None
    motivo_cambio: str = Field(min_length=1, max_length=200)


class MaintenanceProductFormatVersionOutput(ORMModel):
    id: UUID
    id_producto: UUID
    id_formato: UUID
    vigente_desde: date
    vigente_hasta_exclusiva: date | None
    motivo_cambio: str
    id_usuario_alta: UUID


class MaintenanceRecordInput(BaseModel):
    client_uuid: UUID = Field(default_factory=uuid4)
    fecha_operativa: date
    turno_codigo: str = Field(min_length=1, max_length=30)
    inicio: datetime
    fin: datetime | None = None
    id_equipo: UUID
    id_responsable: UUID
    tipo: str = Field(min_length=1, max_length=30)
    descripcion: str = Field(min_length=1, max_length=2000)
    id_producto_formato_version: UUID | None = None
    id_producto: UUID | None = None
    id_formato: UUID | None = None
    campos_madirex: dict = Field(default_factory=dict)
    ids_paradas: list[UUID] = Field(default_factory=list)
    ids_desvios: list[UUID] = Field(default_factory=list)


class MaintenanceCorrelationOutput(ORMModel):
    tipo_referencia: str
    id_referencia: UUID


class MaintenanceRecordOutput(ORMModel):
    id: UUID
    client_uuid: UUID
    fecha_operativa: date
    turno_codigo: str
    inicio: datetime
    fin: datetime | None
    id_equipo: UUID
    id_producto_formato_version: UUID | None
    id_responsable: UUID
    tipo: str
    descripcion: str
    campos_madirex: dict
    creado_por: UUID
    correlaciones: list[MaintenanceCorrelationOutput]


class OperationalRecordOutput(ORMModel):
    id: UUID
    modulo: str
    sector: str
    client_uuid: UUID
    estado: str
    origen_dato: str
    fecha_operativa: date
    turno_codigo: str
    instante_medicion: datetime
    cargado_en: datetime
    id_responsable: UUID
    id_usuario_digitador: UUID | None
    creado_por: UUID
    revision: int
    datos: dict


class DeviationOutput(ORMModel):
    id: UUID
    id_registro: UUID
    campo: str
    id_limite: str
    id_desvio: str
    estado: str
    valor_actual: Decimal | None
    vence_en: datetime | None


class AnalyticsRebuildOutput(ORMModel):
    id: UUID
    estado: str
    solicitado_en: datetime
    completado_en: datetime | None
