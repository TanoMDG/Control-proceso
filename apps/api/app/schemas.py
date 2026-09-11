from datetime import date, datetime
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
    id_responsable: UUID
    datos: dict = Field(default_factory=dict)


class OperationalRecordOutput(ORMModel):
    id: UUID
    modulo: str
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
