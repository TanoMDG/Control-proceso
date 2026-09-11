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
    __table_args__ = (UniqueConstraint("tabla_origen", "id_registro", "campo", name="uq_registro_limite_aplicado"),)


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
