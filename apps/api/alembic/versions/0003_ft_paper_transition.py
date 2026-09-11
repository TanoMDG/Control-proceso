"""FT paper transition operational record.

Revision ID: 0003_ft_paper_transition
Revises: 0002_f0_master_import
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_ft_paper_transition"
down_revision = "0002_f0_master_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "registro_operativo" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "registro_operativo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("modulo", sa.String(length=10), nullable=False),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="BORRADOR"),
        sa.Column("motivo_anulacion", sa.String(length=300), nullable=True),
        sa.Column("origen_dato", sa.String(length=20), nullable=False),
        sa.Column("fecha_operativa", sa.Date(), nullable=False),
        sa.Column("turno_codigo", sa.String(length=30), nullable=False),
        sa.Column("instante_medicion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cargado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id_responsable", postgresql.UUID(as_uuid=True), sa.ForeignKey("persona.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("id_usuario_digitador", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cerrado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("cerrado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("datos", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("motivo_correccion", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("modulo", "client_uuid", name="uq_registro_operativo_cliente"),
        sa.CheckConstraint("estado IN ('BORRADOR', 'CERRADO', 'VALIDADO', 'ANULADO')", name="ck_registro_operativo_estado"),
        sa.CheckConstraint("origen_dato IN ('digital_directo', 'papel_digitado')", name="ck_registro_operativo_origen"),
        sa.CheckConstraint("revision > 0", name="ck_registro_operativo_revision"),
    )
    op.create_index("ix_registro_operativo_consulta", "registro_operativo", ["modulo", "fecha_operativa", "turno_codigo"])


def downgrade() -> None:
    op.drop_index("ix_registro_operativo_consulta", table_name="registro_operativo")
    op.drop_table("registro_operativo")
