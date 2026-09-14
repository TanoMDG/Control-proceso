import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Person(Base, Timestamped):
    __tablename__ = "persona"
    id: Mapped[uuid.UUID] = uuid_pk()
    legajo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    apellido_nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    abreviatura: Mapped[str | None] = mapped_column(String(15))
    id_linea_habitual: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalogo.id", ondelete="RESTRICT"))
    es_cuenta_tecnica_dev: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_baja: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("(activo = true AND fecha_baja IS NULL) OR (activo = false AND fecha_baja IS NOT NULL)", name="ck_persona_baja_logica"),)


class Role(Base, Timestamped):
    __tablename__ = "rol"
    id: Mapped[uuid.UUID] = uuid_pk()
    nombre: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base, Timestamped):
    __tablename__ = "usuario"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_persona: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persona.id", ondelete="RESTRICT"), unique=True, nullable=False)
    nombre_usuario: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    id_rol: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rol.id", ondelete="RESTRICT"), nullable=False)
    sector: Mapped[str] = mapped_column(String(40), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consulta_remota: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Permission(Base, Timestamped):
    __tablename__ = "permiso"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_rol: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rol.id", ondelete="CASCADE"), nullable=False)
    modulo: Mapped[str] = mapped_column(String(30), nullable=False)
    accion: Mapped[str] = mapped_column(String(20), nullable=False)
    alcance: Mapped[str] = mapped_column(String(30), nullable=False)
    __table_args__ = (UniqueConstraint("id_rol", "modulo", "accion", "alcance", name="uq_permiso_rol_modulo_accion_alcance"),)


class PersonPosition(Base, Timestamped):
    __tablename__ = "persona_puesto"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_persona: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False)
    puesto: Mapped[str] = mapped_column(String(40), nullable=False)
    id_linea: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalogo.id", ondelete="RESTRICT"))
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("vigente_hasta IS NULL OR vigente_hasta > vigente_desde", name="ck_persona_puesto_vigencia"),)


class DeviceSession(Base, Timestamped):
    __tablename__ = "sesion_dispositivo"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_usuario: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    dispositivo_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("id_usuario", "dispositivo_uuid", name="uq_sesion_dispositivo_usuario"),)


class Catalog(Base, Timestamped):
    __tablename__ = "catalogo"
    id: Mapped[uuid.UUID] = uuid_pk()
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(120), nullable=False)
    atributos: Mapped[dict | None] = mapped_column(JSONB)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_baja: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (UniqueConstraint("tipo", "codigo", name="uq_catalogo_tipo_codigo"), CheckConstraint("(activo = true AND fecha_baja IS NULL) OR (activo = false AND fecha_baja IS NOT NULL)", name="ck_catalogo_baja_logica"))


class Limit(Base, Timestamped):
    __tablename__ = "limite"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    variable: Mapped[str] = mapped_column(String(120), nullable=False)
    etapa: Mapped[str] = mapped_column(String(80), nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    tipo_dato: Mapped[str] = mapped_column(String(50), nullable=False)
    modulo_destino: Mapped[str | None] = mapped_column(String(30))
    campo_destino: Mapped[str | None] = mapped_column(String(80))
    referencia_fuente: Mapped[str | None] = mapped_column(Text)
    nota_fuente: Mapped[str | None] = mapped_column(Text)


class LimitVersion(Base, Timestamped):
    __tablename__ = "limite_version"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_limite: Mapped[str] = mapped_column(String(10), ForeignKey("limite.id", ondelete="RESTRICT"), nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta_exclusiva: Mapped[date | None] = mapped_column(Date)
    valor_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    valor_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    operador_min: Mapped[str | None] = mapped_column(String(3))
    operador_max: Mapped[str | None] = mapped_column(String(3))
    nivel: Mapped[str] = mapped_column(String(20), nullable=False)
    id_desvio: Mapped[str | None] = mapped_column(String(10))
    motivo_cambio: Mapped[str] = mapped_column(String(200), nullable=False)
    id_usuario_alta: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="PROGRAMADA", nullable=False)
    cancelada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("vigente_hasta_exclusiva IS NULL OR vigente_hasta_exclusiva > vigente_desde", name="ck_limite_version_intervalo"), CheckConstraint("operador_min IS NULL OR operador_min IN ('>', '>=')", name="ck_limite_operador_min"), CheckConstraint("operador_max IS NULL OR operador_max IN ('<', '<=')", name="ck_limite_operador_max"), Index("ix_limite_version_vigencia", "id_limite", "vigente_desde"))


class AppliedLimit(Base):
    __tablename__ = "registro_limite_aplicado"
    id: Mapped[uuid.UUID] = uuid_pk()
    tabla_origen: Mapped[str] = mapped_column(String(80), nullable=False)
    id_registro: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    campo: Mapped[str] = mapped_column(String(80), nullable=False)
    id_limite: Mapped[str] = mapped_column(String(10), ForeignKey("limite.id", ondelete="RESTRICT"), nullable=False)
    id_limite_version: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("limite_version.id", ondelete="RESTRICT"), nullable=False)
    valor_medido: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    resultado: Mapped[str] = mapped_column(String(30), nullable=False)
    evaluado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tabla_origen", "id_registro", "campo", name="uq_registro_limite_aplicado"), Index("ix_registro_limite_aplicado_origen_campo", "tabla_origen", "campo", "id_registro"))


class SystemParameterVersion(Base, Timestamped):
    __tablename__ = "parametro_sistema_version"
    id: Mapped[uuid.UUID] = uuid_pk()
    clave: Mapped[str] = mapped_column(String(80), nullable=False)
    valor: Mapped[str] = mapped_column(String(120), nullable=False)
    unidad: Mapped[str | None] = mapped_column(String(20))
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta_exclusiva: Mapped[date | None] = mapped_column(Date)
    motivo: Mapped[str] = mapped_column(String(200), nullable=False)
    id_usuario: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (CheckConstraint("vigente_hasta_exclusiva IS NULL OR vigente_hasta_exclusiva > vigente_desde", name="ck_parametro_intervalo"), Index("ix_parametro_vigencia", "clave", "vigente_desde"))


class ProductionCalendar(Base, Timestamped):
    __tablename__ = "calendario_produccion"
    id: Mapped[uuid.UUID] = uuid_pk()
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    programado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    horas_programadas: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    motivo: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("fecha_operativa", "turno_codigo", name="uq_calendario_fecha_turno"), CheckConstraint("horas_programadas IS NULL OR horas_programadas >= 0", name="ck_calendario_horas"))


class ShiftReceipt(Base):
    __tablename__ = "recepcion_turno"
    id: Mapped[uuid.UUID] = uuid_pk()
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    sector: Mapped[str] = mapped_column(String(40), nullable=False)
    id_usuario: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    observacion: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (UniqueConstraint("fecha_operativa", "turno_codigo", "sector", "id_usuario", name="uq_recepcion_turno_usuario"),)


class ShiftClose(Base):
    __tablename__ = "turno_cierre"
    id: Mapped[uuid.UUID] = uuid_pk()
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    id_linea: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cerrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    id_usuario_cierre: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    registros_faltantes: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (UniqueConstraint("fecha_operativa", "turno_codigo", "id_linea", name="uq_turno_cierre"),)


class MUA(Base, Timestamped):
    __tablename__ = "mua"
    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    fecha_generacion: Mapped[date] = mapped_column(Date, nullable=False)
    id_preparador: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False)
    composicion: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    creado_por: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)


class MuaBoxPresence(Base):
    __tablename__ = "mua_box_presencia"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_mua: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mua.id", ondelete="RESTRICT"), nullable=False)
    box: Mapped[str] = mapped_column(String(30), nullable=False)
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certeza: Mapped[str] = mapped_column(String(15), default="CONFIRMADA", nullable=False)
    id_usuario_inicio: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    id_usuario_fin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    __table_args__ = (CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_mua_box_intervalo"), CheckConstraint("certeza IN ('CONFIRMADA', 'POTENCIAL', 'INFERIDA')", name="ck_mua_box_certeza"), Index("ix_mua_box_presencia_activa", "box", "hasta"))


class BoxVerdesPeriod(Base):
    __tablename__ = "box_verdes_periodo"
    id: Mapped[uuid.UUID] = uuid_pk()
    box: Mapped[str] = mapped_column(String(30), nullable=False)
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_usuario_inicio: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    id_usuario_fin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    __table_args__ = (CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_box_verdes_intervalo"), Index("ix_box_verdes_activa", "hasta"))


class KsiderSiloPeriod(Base):
    __tablename__ = "ksider_silo_periodo"
    id: Mapped[uuid.UUID] = uuid_pk()
    receptor: Mapped[str] = mapped_column(String(30), default="K-SIDER", nullable=False)
    silo: Mapped[int] = mapped_column(Integer, nullable=False)
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_usuario_inicio: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    id_usuario_fin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    __table_args__ = (CheckConstraint("silo BETWEEN 1 AND 16", name="ck_ksider_silo_numero"), CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_ksider_silo_intervalo"), Index("ix_ksider_silo_activa", "receptor", "hasta"))


class SiloLinePeriod(Base):
    __tablename__ = "silo_linea_periodo"
    id: Mapped[uuid.UUID] = uuid_pk()
    silo: Mapped[int] = mapped_column(Integer, nullable=False)
    linea: Mapped[str] = mapped_column(String(10), nullable=False)
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_usuario_inicio: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    id_usuario_fin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    __table_args__ = (CheckConstraint("silo BETWEEN 1 AND 16", name="ck_silo_linea_numero"), CheckConstraint("linea IN ('L6', 'L7')", name="ck_silo_linea_fisica"), CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_silo_linea_intervalo"), Index("ix_silo_linea_activa", "silo", "hasta"))


class LineProductFormatPeriod(Base):
    __tablename__ = "linea_producto_formato_periodo"
    id: Mapped[uuid.UUID] = uuid_pk()
    linea: Mapped[str] = mapped_column(String(10), nullable=False)
    producto: Mapped[str] = mapped_column(String(80), nullable=False)
    formato: Mapped[str] = mapped_column(String(80), nullable=False)
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_usuario_inicio: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    id_usuario_fin: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    __table_args__ = (CheckConstraint("linea IN ('L6', 'L7')", name="ck_linea_producto_linea"), CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_linea_producto_intervalo"), Index("ix_linea_producto_activa", "linea", "hasta"))


class MaintenanceEquipment(Base, Timestamped):
    __tablename__ = "equipo_mantenimiento"
    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(160), nullable=False)
    sector: Mapped[str] = mapped_column(String(40), nullable=False)
    atributos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_baja: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("(activo = true AND fecha_baja IS NULL) OR (activo = false AND fecha_baja IS NOT NULL)", name="ck_equipo_mantenimiento_baja_logica"),)


class MaintenanceProduct(Base, Timestamped):
    __tablename__ = "producto_mantenimiento"
    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(160), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_baja: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("(activo = true AND fecha_baja IS NULL) OR (activo = false AND fecha_baja IS NOT NULL)", name="ck_producto_mantenimiento_baja_logica"),)


class MaintenanceProductFormatVersion(Base, Timestamped):
    __tablename__ = "producto_formato_mantenimiento_version"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_producto: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("producto_mantenimiento.id", ondelete="RESTRICT"), nullable=False)
    id_formato: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalogo.id", ondelete="RESTRICT"), nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta_exclusiva: Mapped[date | None] = mapped_column(Date)
    motivo_cambio: Mapped[str] = mapped_column(String(200), nullable=False)
    id_usuario_alta: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (CheckConstraint("vigente_hasta_exclusiva IS NULL OR vigente_hasta_exclusiva > vigente_desde", name="ck_producto_formato_mantenimiento_intervalo"), Index("ix_producto_formato_mantenimiento_vigencia", "id_producto", "id_formato", "vigente_desde"))


class MaintenanceRecord(Base, Timestamped):
    __tablename__ = "registro_mantenimiento"
    id: Mapped[uuid.UUID] = uuid_pk()
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_equipo: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("equipo_mantenimiento.id", ondelete="RESTRICT"), nullable=False)
    id_producto_formato_version: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("producto_formato_mantenimiento_version.id", ondelete="RESTRICT"))
    id_responsable: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    campos_madirex: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    creado_por: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (CheckConstraint("fin IS NULL OR fin >= inicio", name="ck_registro_mantenimiento_intervalo"),)


class MaintenanceCorrelation(Base):
    __tablename__ = "correlacion_mantenimiento"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_registro_mantenimiento: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("registro_mantenimiento.id", ondelete="CASCADE"), nullable=False)
    tipo_referencia: Mapped[str] = mapped_column(String(20), nullable=False)
    id_referencia: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    __table_args__ = (CheckConstraint("tipo_referencia IN ('PARADA', 'DESVIO')", name="ck_correlacion_mantenimiento_tipo"), UniqueConstraint("id_registro_mantenimiento", "tipo_referencia", "id_referencia", name="uq_correlacion_mantenimiento"))


class LaboratoryUnit(Base, Timestamped):
    __tablename__ = "laboratorio_unidad"
    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LaboratorySamplePoint(Base, Timestamped):
    __tablename__ = "laboratorio_punto_muestreo"
    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(160), nullable=False)
    sector: Mapped[str] = mapped_column(String(40), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LaboratoryDetermination(Base, Timestamped):
    __tablename__ = "laboratorio_determinacion"
    id: Mapped[uuid.UUID] = uuid_pk()
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(160), nullable=False)
    tipo_resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (CheckConstraint("tipo_resultado IN ('NUMERICO', 'GRANULOMETRIA')", name="ck_lab_determinacion_tipo"),)


class LaboratoryPointDetermination(Base, Timestamped):
    __tablename__ = "laboratorio_punto_determinacion"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_punto: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_punto_muestreo.id", ondelete="RESTRICT"), nullable=False)
    id_determinacion: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_determinacion.id", ondelete="RESTRICT"), nullable=False)
    id_unidad: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_unidad.id", ondelete="RESTRICT"), nullable=False)
    id_limite: Mapped[str | None] = mapped_column(String(10), ForeignKey("limite.id", ondelete="RESTRICT"))
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta_exclusiva: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (CheckConstraint("vigente_hasta_exclusiva IS NULL OR vigente_hasta_exclusiva > vigente_desde", name="ck_lab_punto_determinacion_intervalo"), Index("ix_lab_punto_determinacion_vigencia", "id_punto", "vigente_desde"))


class LaboratoryFrequency(Base, Timestamped):
    __tablename__ = "laboratorio_frecuencia_control"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_configuracion: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_punto_determinacion.id", ondelete="RESTRICT"), nullable=False)
    vigente_desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vigente_hasta_exclusiva: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intervalo_horas: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (CheckConstraint("intervalo_horas > 0", name="ck_lab_frecuencia_intervalo"), CheckConstraint("vigente_hasta_exclusiva IS NULL OR vigente_hasta_exclusiva > vigente_desde", name="ck_lab_frecuencia_vigencia"), Index("ix_lab_frecuencia_vigencia", "id_configuracion", "vigente_desde"))


class LaboratorySieve(Base, Timestamped):
    __tablename__ = "laboratorio_tamiz"
    id: Mapped[uuid.UUID] = uuid_pk()
    torre: Mapped[str] = mapped_column(String(80), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(160), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LaboratoryConfigurationSieve(Base):
    __tablename__ = "laboratorio_configuracion_tamiz"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_configuracion: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_punto_determinacion.id", ondelete="CASCADE"), nullable=False)
    id_tamiz: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_tamiz.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (UniqueConstraint("id_configuracion", "id_tamiz", name="uq_lab_configuracion_tamiz"),)


class LaboratoryAnalysis(Base, Timestamped):
    __tablename__ = "analisis_laboratorio"
    id: Mapped[uuid.UUID] = uuid_pk()
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    id_punto: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_punto_muestreo.id", ondelete="RESTRICT"), nullable=False)
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    instante_muestreo: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    id_mua: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("mua.id", ondelete="RESTRICT"))
    id_registro_stock: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("registro_operativo.id", ondelete="RESTRICT"))
    id_registro_proceso: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("registro_operativo.id", ondelete="RESTRICT"))
    silo: Mapped[int | None] = mapped_column(Integer)
    id_producto: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("catalogo.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    creado_por: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    motivo_correccion: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (CheckConstraint("silo IS NULL OR silo BETWEEN 1 AND 16", name="ck_analisis_laboratorio_silo"), CheckConstraint("estado IN ('BORRADOR', 'CERRADO', 'VALIDADO', 'ANULADO')", name="ck_analisis_laboratorio_estado"), CheckConstraint("revision > 0", name="ck_analisis_laboratorio_revision"), Index("ix_analisis_laboratorio_consulta", "id_punto", "fecha_operativa"))


class LaboratoryAnalysisResult(Base):
    __tablename__ = "analisis_laboratorio_resultado"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_analisis: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analisis_laboratorio.id", ondelete="CASCADE"), nullable=False)
    id_configuracion: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_punto_determinacion.id", ondelete="RESTRICT"), nullable=False)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(16, 5))
    unidad: Mapped[str] = mapped_column(String(30), nullable=False)
    __table_args__ = (UniqueConstraint("id_analisis", "id_configuracion", name="uq_analisis_laboratorio_resultado"),)


class LaboratoryGranulometryResult(Base):
    __tablename__ = "analisis_granulometria"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_analisis: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analisis_laboratorio.id", ondelete="CASCADE"), nullable=False)
    id_configuracion: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_punto_determinacion.id", ondelete="RESTRICT"), nullable=False)
    id_tamiz: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratorio_tamiz.id", ondelete="RESTRICT"), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(16, 5), nullable=False)
    __table_args__ = (UniqueConstraint("id_analisis", "id_configuracion", "id_tamiz", name="uq_analisis_granulometria"),)


class LaboratoryDeviationEvent(Base, Timestamped):
    __tablename__ = "evento_desvio_laboratorio"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_resultado: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analisis_laboratorio_resultado.id", ondelete="RESTRICT"), nullable=False)
    id_limite: Mapped[str] = mapped_column(String(10), ForeignKey("limite.id", ondelete="RESTRICT"), nullable=False)
    id_limite_version: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("limite_version.id", ondelete="RESTRICT"), nullable=False)
    id_desvio: Mapped[str] = mapped_column(String(10), ForeignKey("plan_reaccion.id_desvio", ondelete="RESTRICT"), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTO", nullable=False)
    valor_actual: Mapped[Decimal] = mapped_column(Numeric(16, 5), nullable=False)
    __table_args__ = (UniqueConstraint("id_resultado", "id_limite_version", name="uq_desvio_laboratorio_resultado_version"), CheckConstraint("estado IN ('ABIERTO', 'EN_TRATAMIENTO', 'VERIFICADO', 'VENCIDO', 'ESCALADO', 'CERRADO', 'INVALIDADO')", name="ck_evento_desvio_laboratorio_estado"))


class OperationalRecord(Base, Timestamped):
    __tablename__ = "registro_operativo"
    id: Mapped[uuid.UUID] = uuid_pk()
    modulo: Mapped[str] = mapped_column(String(10), nullable=False)
    sector: Mapped[str] = mapped_column(String(40), nullable=False)
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", nullable=False)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(300))
    origen_dato: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    instante_medicion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    id_responsable: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False)
    id_usuario_digitador: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    creado_por: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    cerrado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    datos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    motivo_correccion: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (
        UniqueConstraint("modulo", "client_uuid", name="uq_registro_operativo_cliente"),
        CheckConstraint("estado IN ('BORRADOR', 'CERRADO', 'VALIDADO', 'ANULADO')", name="ck_registro_operativo_estado"),
        CheckConstraint("estado <> 'ANULADO' OR motivo_anulacion IS NOT NULL", name="ck_registro_operativo_anulacion_motivo"),
        CheckConstraint("origen_dato IN ('digital_directo', 'papel_digitado')", name="ck_registro_operativo_origen"),
        CheckConstraint("revision > 0", name="ck_registro_operativo_revision"),
        Index("ix_registro_operativo_consulta", "modulo", "fecha_operativa", "turno_codigo"),
    )


class DeviationEvent(Base, Timestamped):
    __tablename__ = "evento_desvio"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_registro: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("registro_operativo.id", ondelete="RESTRICT"), nullable=False)
    campo: Mapped[str] = mapped_column(String(80), nullable=False)
    id_limite: Mapped[str] = mapped_column(String(10), ForeignKey("limite.id", ondelete="RESTRICT"), nullable=False)
    id_limite_version: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("limite_version.id", ondelete="RESTRICT"), nullable=False)
    id_desvio: Mapped[str] = mapped_column(String(10), ForeignKey("plan_reaccion.id_desvio", ondelete="RESTRICT"), nullable=False)
    clave_idempotencia: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    secuencia_clave: Mapped[str] = mapped_column(String(180), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTO", nullable=False)
    valor_actual: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("estado IN ('ABIERTO', 'EN_TRATAMIENTO', 'VERIFICADO', 'VENCIDO', 'ESCALADO', 'CERRADO', 'INVALIDADO')", name="ck_evento_desvio_estado"), Index("ix_evento_desvio_estado", "estado", "id_desvio"))


class DeviationHistory(Base):
    __tablename__ = "evento_desvio_historial"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_evento: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evento_desvio.id", ondelete="CASCADE"), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(20))
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    id_usuario: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "auditoria"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_usuario: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    tabla: Mapped[str] = mapped_column(String(80), nullable=False)
    id_registro: Mapped[str] = mapped_column(String(80), nullable=False)
    accion: Mapped[str] = mapped_column(String(30), nullable=False)
    valor_anterior: Mapped[dict | None] = mapped_column(JSONB)
    valor_nuevo: Mapped[dict | None] = mapped_column(JSONB)
    motivo: Mapped[str | None] = mapped_column(String(200))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BaselineConfiguration(Base):
    __tablename__ = "configuracion_baseline"
    id: Mapped[uuid.UUID] = uuid_pk()
    version: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    fuente_docx: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256_docx: Mapped[str] = mapped_column(String(64), nullable=False)
    fuente_xlsx: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256_xlsx: Mapped[str] = mapped_column(String(64), nullable=False)
    resumen: Mapped[dict] = mapped_column(JSONB, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BaselineReconciliation(Base):
    __tablename__ = "reconciliacion_baseline"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_baseline: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuracion_baseline.id", ondelete="RESTRICT"), unique=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    reporte: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SyncRevision(Base):
    __tablename__ = "revision_sincronizacion"
    id: Mapped[uuid.UUID] = uuid_pk()
    tabla: Mapped[str] = mapped_column(String(80), nullable=False)
    id_registro: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    version_cliente: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tabla", "client_uuid", "revision", name="uq_sync_revision_cliente"), Index("ix_sync_revision_registro", "tabla", "id_registro"))


class SyncConflict(Base):
    __tablename__ = "conflicto_sincronizacion"
    id: Mapped[uuid.UUID] = uuid_pk()
    tabla: Mapped[str] = mapped_column(String(80), nullable=False)
    id_registro: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_cliente: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version_servidor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    detectado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="ABIERTO", nullable=False)
    resuelto_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    resolucion: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (Index("ix_sync_conflict_open", "tabla", "client_uuid", "estado"),)


class ImportRun(Base, Timestamped):
    __tablename__ = "importacion_datos"
    id: Mapped[uuid.UUID] = uuid_pk()
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    id_usuario: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"))
    resumen: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ImportResult(Base):
    __tablename__ = "importacion_resultado"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_importacion: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("importacion_datos.id", ondelete="CASCADE"), nullable=False)
    hoja: Mapped[str] = mapped_column(String(100), nullable=False)
    fila: Mapped[int | None] = mapped_column(Integer)
    nivel: Mapped[str] = mapped_column(String(20), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    valor_original: Mapped[str | None] = mapped_column(Text)
    valor_normativo: Mapped[str | None] = mapped_column(Text)


class ReactionPlan(Base, Timestamped):
    __tablename__ = "plan_reaccion"
    id_desvio: Mapped[str] = mapped_column(String(10), primary_key=True)
    senal: Mapped[str] = mapped_column(Text, nullable=False)
    etapa: Mapped[str] = mapped_column(String(120), nullable=False)
    limite_referencia: Mapped[str] = mapped_column(Text, nullable=False)
    causas_probables: Mapped[str] = mapped_column(Text, nullable=False)
    accion_inmediata: Mapped[str] = mapped_column(Text, nullable=False)
    verificacion: Mapped[str] = mapped_column(Text, nullable=False)
    plazo_texto: Mapped[str] = mapped_column(String(120), nullable=False)
    registro_escalamiento: Mapped[str] = mapped_column(Text, nullable=False)
    plazo_horas: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    tipo_plazo: Mapped[str] = mapped_column(String(50), nullable=False)
    texto_excel_original: Mapped[str | None] = mapped_column(Text)
    motivo_prevalencia: Mapped[str | None] = mapped_column(String(200))


class SiloScale(Base, Timestamped):
    __tablename__ = "escala_silo"
    id: Mapped[uuid.UUID] = uuid_pk()
    grupo_silos: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta_exclusiva: Mapped[date | None] = mapped_column(Date)
    aprobada_por: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (UniqueConstraint("grupo_silos", "version", name="uq_escala_silo_grupo_version"),)


class SiloScalePoint(Base):
    __tablename__ = "escala_silo_punto"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_escala: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("escala_silo.id", ondelete="CASCADE"), nullable=False)
    altura_m: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    toneladas: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    __table_args__ = (UniqueConstraint("id_escala", "altura_m", name="uq_escala_silo_punto_altura"),)


class TemporalMeasurementFact(Base):
    __tablename__ = "hecho_medicion_temporal"
    id: Mapped[uuid.UUID] = uuid_pk()
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    instante_operativo: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tabla_origen: Mapped[str] = mapped_column(String(80), nullable=False)
    id_registro_origen: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    metrica: Mapped[str] = mapped_column(String(100), nullable=False)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(16, 5))
    unidad: Mapped[str | None] = mapped_column(String(20))
    origen_dato: Mapped[str] = mapped_column(String(20), nullable=False)
    contexto: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    calculado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("ix_hecho_temporal_contexto", "fecha_operativa", "turno_codigo", "metrica"),)


class PlcReadSource(Base, Timestamped):
    __tablename__ = "plc_lectura_fuente"
    id: Mapped[uuid.UUID] = uuid_pk()
    nombre: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    adaptador: Mapped[str] = mapped_column(String(30), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (CheckConstraint("adaptador = 'TEST_SIMULATOR'", name="ck_plc_fuente_adaptador_test"),)


class PlcReadTag(Base):
    __tablename__ = "plc_lectura_tag"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_fuente: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plc_lectura_fuente.id", ondelete="RESTRICT"), nullable=False)
    metrica: Mapped[str] = mapped_column(String(100), nullable=False)
    referencia_tag: Mapped[str] = mapped_column(String(200), nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    escala_factor: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    escala_offset: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    muestreo_segundos: Mapped[int] = mapped_column(Integer, nullable=False)
    agregacion_segundos: Mapped[int] = mapped_column(Integer, nullable=False)
    retencion_crudo_dias: Mapped[int] = mapped_column(Integer, nullable=False)
    retencion_agregado_dias: Mapped[int] = mapped_column(Integer, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    sector: Mapped[str] = mapped_column(String(40), nullable=False)
    valor_simulado_crudo: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    calidad_simulada: Mapped[str | None] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (
        UniqueConstraint("id_fuente", "metrica", name="uq_plc_tag_fuente_metrica"),
        UniqueConstraint("id_fuente", "referencia_tag", name="uq_plc_tag_fuente_referencia"),
        CheckConstraint("escala_factor <> 0", name="ck_plc_tag_escala_factor"),
        CheckConstraint("muestreo_segundos > 0 AND agregacion_segundos > 0", name="ck_plc_tag_intervalos"),
        CheckConstraint("retencion_crudo_dias > 0 AND retencion_agregado_dias > 0", name="ck_plc_tag_retencion"),
        CheckConstraint("calidad_simulada IS NULL OR calidad_simulada IN ('GOOD', 'UNCERTAIN', 'BAD')", name="ck_plc_tag_calidad_simulada"),
    )


class PlcRawReading(Base):
    __tablename__ = "plc_lectura_cruda"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_tag: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plc_lectura_tag.id", ondelete="RESTRICT"), nullable=False)
    instante_fuente: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    adquirido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valor_crudo: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    valor_escalado: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    calidad: Mapped[str] = mapped_column(String(20), nullable=False)
    adaptador: Mapped[str] = mapped_column(String(30), nullable=False)
    __table_args__ = (
        CheckConstraint("calidad IN ('GOOD', 'UNCERTAIN', 'BAD')", name="ck_plc_lectura_cruda_calidad"),
        Index("ix_plc_lectura_cruda_tag_instante", "id_tag", "instante_fuente"),
    )


class PlcReadingAggregate(Base):
    __tablename__ = "plc_lectura_agregada"
    id: Mapped[uuid.UUID] = uuid_pk()
    id_tag: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plc_lectura_tag.id", ondelete="RESTRICT"), nullable=False)
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta_exclusiva: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cantidad_muestras: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_minimo: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    valor_maximo: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    valor_promedio: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    ultimo_valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    calidad: Mapped[str] = mapped_column(String(20), nullable=False)
    calculado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("id_tag", "desde", name="uq_plc_agregado_tag_desde"),
        CheckConstraint("hasta_exclusiva > desde", name="ck_plc_agregado_intervalo"),
        CheckConstraint("cantidad_muestras > 0", name="ck_plc_agregado_muestras"),
        CheckConstraint("calidad IN ('GOOD', 'UNCERTAIN', 'BAD')", name="ck_plc_agregado_calidad"),
        Index("ix_plc_lectura_agregada_tag_desde", "id_tag", "desde"),
    )


class PlcAcquisitionStatus(Base):
    __tablename__ = "plc_estado_adquisicion"
    id_fuente: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plc_lectura_fuente.id", ondelete="CASCADE"), primary_key=True)
    estado: Mapped[str] = mapped_column(String(30), nullable=False)
    ultimo_intento_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_muestra_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ShiftFact(Base):
    __tablename__ = "hecho_turno"
    id: Mapped[uuid.UUID] = uuid_pk()
    fecha_operativa: Mapped[date] = mapped_column(Date, nullable=False)
    turno_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    linea_clave: Mapped[str] = mapped_column(String(40), default="PLANTA", nullable=False)
    contexto_clave: Mapped[str] = mapped_column(String(80), default="PLANTA", nullable=False)
    metricas: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    calculado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("fecha_operativa", "turno_codigo", "linea_clave", "contexto_clave", name="uq_hecho_turno_grano"),)


class AnalyticsRun(Base):
    __tablename__ = "recalculo_analitico"
    id: Mapped[uuid.UUID] = uuid_pk()
    solicitado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", nullable=False)
    alcance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
