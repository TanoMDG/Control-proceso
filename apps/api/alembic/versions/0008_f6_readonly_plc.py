"""F6 test-only read-only PLC acquisition infrastructure."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_f6_readonly_plc"
down_revision = "0007_f5_maintenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "plc_lectura_fuente",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("nombre", sa.String(120), unique=True, nullable=False),
        sa.Column("adaptador", sa.String(30), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("adaptador = 'TEST_SIMULATOR'", name="ck_plc_fuente_adaptador_test"),
    )
    op.create_table(
        "plc_lectura_tag",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("id_fuente", uuid, sa.ForeignKey("plc_lectura_fuente.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("metrica", sa.String(100), nullable=False),
        sa.Column("referencia_tag", sa.String(200), nullable=False),
        sa.Column("unidad", sa.String(20), nullable=False),
        sa.Column("escala_factor", sa.Numeric(18, 8), nullable=False),
        sa.Column("escala_offset", sa.Numeric(18, 8), nullable=False),
        sa.Column("muestreo_segundos", sa.Integer(), nullable=False),
        sa.Column("agregacion_segundos", sa.Integer(), nullable=False),
        sa.Column("retencion_crudo_dias", sa.Integer(), nullable=False),
        sa.Column("retencion_agregado_dias", sa.Integer(), nullable=False),
        sa.Column("turno_codigo", sa.String(30), nullable=False),
        sa.Column("sector", sa.String(40), nullable=False),
        sa.Column("valor_simulado_crudo", sa.Numeric(18, 8)),
        sa.Column("calidad_simulada", sa.String(20)),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("id_fuente", "metrica", name="uq_plc_tag_fuente_metrica"),
        sa.UniqueConstraint("id_fuente", "referencia_tag", name="uq_plc_tag_fuente_referencia"),
        sa.CheckConstraint("escala_factor <> 0", name="ck_plc_tag_escala_factor"),
        sa.CheckConstraint("muestreo_segundos > 0 AND agregacion_segundos > 0", name="ck_plc_tag_intervalos"),
        sa.CheckConstraint("retencion_crudo_dias > 0 AND retencion_agregado_dias > 0", name="ck_plc_tag_retencion"),
        sa.CheckConstraint("calidad_simulada IS NULL OR calidad_simulada IN ('GOOD', 'UNCERTAIN', 'BAD')", name="ck_plc_tag_calidad_simulada"),
    )
    op.create_table(
        "plc_lectura_cruda",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("id_tag", uuid, sa.ForeignKey("plc_lectura_tag.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("instante_fuente", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adquirido_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("valor_crudo", sa.Numeric(18, 8), nullable=False),
        sa.Column("valor_escalado", sa.Numeric(18, 8), nullable=False),
        sa.Column("unidad", sa.String(20), nullable=False),
        sa.Column("calidad", sa.String(20), nullable=False),
        sa.Column("adaptador", sa.String(30), nullable=False),
        sa.CheckConstraint("calidad IN ('GOOD', 'UNCERTAIN', 'BAD')", name="ck_plc_lectura_cruda_calidad"),
    )
    op.create_index("ix_plc_lectura_cruda_tag_instante", "plc_lectura_cruda", ["id_tag", "instante_fuente"])
    op.create_table(
        "plc_lectura_agregada",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("id_tag", uuid, sa.ForeignKey("plc_lectura_tag.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hasta_exclusiva", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cantidad_muestras", sa.Integer(), nullable=False),
        sa.Column("valor_minimo", sa.Numeric(18, 8)),
        sa.Column("valor_maximo", sa.Numeric(18, 8)),
        sa.Column("valor_promedio", sa.Numeric(18, 8)),
        sa.Column("ultimo_valor", sa.Numeric(18, 8)),
        sa.Column("calidad", sa.String(20), nullable=False),
        sa.Column("calculado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id_tag", "desde", name="uq_plc_agregado_tag_desde"),
        sa.CheckConstraint("hasta_exclusiva > desde", name="ck_plc_agregado_intervalo"),
        sa.CheckConstraint("cantidad_muestras > 0", name="ck_plc_agregado_muestras"),
        sa.CheckConstraint("calidad IN ('GOOD', 'UNCERTAIN', 'BAD')", name="ck_plc_agregado_calidad"),
    )
    op.create_index("ix_plc_lectura_agregada_tag_desde", "plc_lectura_agregada", ["id_tag", "desde"])
    op.create_table(
        "plc_estado_adquisicion",
        sa.Column("id_fuente", uuid, sa.ForeignKey("plc_lectura_fuente.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("estado", sa.String(30), nullable=False),
        sa.Column("ultimo_intento_en", sa.DateTime(timezone=True)),
        sa.Column("ultima_muestra_en", sa.DateTime(timezone=True)),
        sa.Column("ultimo_error", sa.Text()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("plc_estado_adquisicion")
    op.drop_index("ix_plc_lectura_agregada_tag_desde", table_name="plc_lectura_agregada")
    op.drop_table("plc_lectura_agregada")
    op.drop_index("ix_plc_lectura_cruda_tag_instante", table_name="plc_lectura_cruda")
    op.drop_table("plc_lectura_cruda")
    op.drop_table("plc_lectura_tag")
    op.drop_table("plc_lectura_fuente")
