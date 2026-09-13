"""F5 maintenance records and versioned maintenance masters."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_f5_maintenance"
down_revision = "0006_f4_traceability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    def create_table_if_missing(name: str, *args: object) -> None:
        if name not in tables:
            op.create_table(name, *args)

    create_table_if_missing(
        "equipo_mantenimiento",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("codigo", sa.String(40), unique=True, nullable=False),
        sa.Column("descripcion", sa.String(160), nullable=False),
        sa.Column("sector", sa.String(40), nullable=False),
        sa.Column("atributos", postgresql.JSONB(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fecha_baja", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(activo = true AND fecha_baja IS NULL) OR (activo = false AND fecha_baja IS NOT NULL)", name="ck_equipo_mantenimiento_baja_logica"),
    )
    create_table_if_missing(
        "producto_mantenimiento",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("codigo", sa.String(40), unique=True, nullable=False),
        sa.Column("descripcion", sa.String(160), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fecha_baja", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(activo = true AND fecha_baja IS NULL) OR (activo = false AND fecha_baja IS NOT NULL)", name="ck_producto_mantenimiento_baja_logica"),
    )
    create_table_if_missing(
        "producto_formato_mantenimiento_version",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("id_producto", uuid, sa.ForeignKey("producto_mantenimiento.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("id_formato", uuid, sa.ForeignKey("catalogo.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        sa.Column("vigente_hasta_exclusiva", sa.Date()),
        sa.Column("motivo_cambio", sa.String(200), nullable=False),
        sa.Column("id_usuario_alta", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("vigente_hasta_exclusiva IS NULL OR vigente_hasta_exclusiva > vigente_desde", name="ck_producto_formato_mantenimiento_intervalo"),
    )
    if "producto_formato_mantenimiento_version" not in tables:
        op.create_index("ix_producto_formato_mantenimiento_vigencia", "producto_formato_mantenimiento_version", ["id_producto", "id_formato", "vigente_desde"])
    create_table_if_missing(
        "registro_mantenimiento",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("client_uuid", uuid, unique=True, nullable=False),
        sa.Column("fecha_operativa", sa.Date(), nullable=False),
        sa.Column("turno_codigo", sa.String(30), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True)),
        sa.Column("id_equipo", uuid, sa.ForeignKey("equipo_mantenimiento.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("id_producto_formato_version", uuid, sa.ForeignKey("producto_formato_mantenimiento_version.id", ondelete="RESTRICT")),
        sa.Column("id_responsable", uuid, sa.ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("campos_madirex", postgresql.JSONB(), nullable=False),
        sa.Column("creado_por", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("fin IS NULL OR fin >= inicio", name="ck_registro_mantenimiento_intervalo"),
    )
    create_table_if_missing(
        "correlacion_mantenimiento",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("id_registro_mantenimiento", uuid, sa.ForeignKey("registro_mantenimiento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo_referencia", sa.String(20), nullable=False),
        sa.Column("id_referencia", uuid, nullable=False),
        sa.CheckConstraint("tipo_referencia IN ('PARADA', 'DESVIO')", name="ck_correlacion_mantenimiento_tipo"),
        sa.UniqueConstraint("id_registro_mantenimiento", "tipo_referencia", "id_referencia", name="uq_correlacion_mantenimiento"),
    )


def downgrade() -> None:
    op.drop_table("correlacion_mantenimiento")
    op.drop_table("registro_mantenimiento")
    op.drop_index("ix_producto_formato_mantenimiento_vigencia", table_name="producto_formato_mantenimiento_version")
    op.drop_table("producto_formato_mantenimiento_version")
    op.drop_table("producto_mantenimiento")
    op.drop_table("equipo_mantenimiento")
