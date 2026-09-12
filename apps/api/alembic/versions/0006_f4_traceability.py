"""F4 MUA identity and temporal traceability."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_f4_traceability"
down_revision = "0005_f1_operational_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "mua",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("codigo", sa.String(20), unique=True, nullable=False),
        sa.Column("fecha_generacion", sa.Date(), nullable=False),
        sa.Column("id_preparador", uuid, sa.ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("composicion", postgresql.JSONB(), nullable=False),
        sa.Column("creado_por", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    temporal_columns = lambda: [
        sa.Column("id", uuid, primary_key=True),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hasta", sa.DateTime(timezone=True)),
        sa.Column("id_usuario_inicio", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("id_usuario_fin", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT")),
        sa.CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_intervalo"),
    ]
    op.create_table(
        "mua_box_presencia",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("id_mua", uuid, sa.ForeignKey("mua.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("box", sa.String(30), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hasta", sa.DateTime(timezone=True)),
        sa.Column("certeza", sa.String(15), server_default="CONFIRMADA", nullable=False),
        sa.Column("id_usuario_inicio", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("id_usuario_fin", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT")),
        sa.CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_mua_box_intervalo"),
        sa.CheckConstraint("certeza IN ('CONFIRMADA', 'POTENCIAL', 'INFERIDA')", name="ck_mua_box_certeza"),
    )
    op.create_index("ix_mua_box_presencia_activa", "mua_box_presencia", ["box", "hasta"])
    op.create_table(
        "box_verdes_periodo",
        sa.Column("id", uuid, primary_key=True), sa.Column("box", sa.String(30), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False), sa.Column("hasta", sa.DateTime(timezone=True)),
        sa.Column("id_usuario_inicio", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False), sa.Column("id_usuario_fin", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT")),
        sa.CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_box_verdes_intervalo"),
    )
    op.create_index("ix_box_verdes_activa", "box_verdes_periodo", ["hasta"])
    op.create_table(
        "ksider_silo_periodo",
        sa.Column("id", uuid, primary_key=True), sa.Column("receptor", sa.String(30), server_default="K-SIDER", nullable=False), sa.Column("silo", sa.Integer(), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False), sa.Column("hasta", sa.DateTime(timezone=True)),
        sa.Column("id_usuario_inicio", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False), sa.Column("id_usuario_fin", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT")),
        sa.CheckConstraint("silo BETWEEN 1 AND 16", name="ck_ksider_silo_numero"), sa.CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_ksider_silo_intervalo"),
    )
    op.create_index("ix_ksider_silo_activa", "ksider_silo_periodo", ["receptor", "hasta"])
    op.create_table(
        "silo_linea_periodo",
        sa.Column("id", uuid, primary_key=True), sa.Column("silo", sa.Integer(), nullable=False), sa.Column("linea", sa.String(10), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False), sa.Column("hasta", sa.DateTime(timezone=True)),
        sa.Column("id_usuario_inicio", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False), sa.Column("id_usuario_fin", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT")),
        sa.CheckConstraint("silo BETWEEN 1 AND 16", name="ck_silo_linea_numero"), sa.CheckConstraint("linea IN ('L6', 'L7')", name="ck_silo_linea_fisica"), sa.CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_silo_linea_intervalo"),
    )
    op.create_index("ix_silo_linea_activa", "silo_linea_periodo", ["silo", "hasta"])
    op.create_table(
        "linea_producto_formato_periodo",
        sa.Column("id", uuid, primary_key=True), sa.Column("linea", sa.String(10), nullable=False), sa.Column("producto", sa.String(80), nullable=False), sa.Column("formato", sa.String(80), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False), sa.Column("hasta", sa.DateTime(timezone=True)),
        sa.Column("id_usuario_inicio", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False), sa.Column("id_usuario_fin", uuid, sa.ForeignKey("usuario.id", ondelete="RESTRICT")),
        sa.CheckConstraint("linea IN ('L6', 'L7')", name="ck_linea_producto_linea"), sa.CheckConstraint("hasta IS NULL OR hasta > desde", name="ck_linea_producto_intervalo"),
    )
    op.create_index("ix_linea_producto_activa", "linea_producto_formato_periodo", ["linea", "hasta"])


def downgrade() -> None:
    for table, index in (("linea_producto_formato_periodo", "ix_linea_producto_activa"), ("silo_linea_periodo", "ix_silo_linea_activa"), ("ksider_silo_periodo", "ix_ksider_silo_activa"), ("box_verdes_periodo", "ix_box_verdes_activa"), ("mua_box_presencia", "ix_mua_box_presencia_activa")):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
    op.drop_table("mua")
