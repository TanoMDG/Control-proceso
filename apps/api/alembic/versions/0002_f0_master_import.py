"""F0 master-data import structures.

Revision ID: 0002_f0_master_import
Revises: 0001_f0_foundation
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_f0_master_import"
down_revision = "0001_f0_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = lambda table: {column["name"] for column in inspector.get_columns(table)}
    tables = set(inspector.get_table_names())
    if "id_linea_habitual" not in columns("persona"):
        op.add_column("persona", sa.Column("id_linea_habitual", postgresql.UUID(as_uuid=True), nullable=True))
    if "es_cuenta_tecnica_dev" not in columns("persona"):
        op.add_column("persona", sa.Column("es_cuenta_tecnica_dev", sa.Boolean(), nullable=False, server_default=sa.false()))
    persona_foreign_keys = {tuple(fk["constrained_columns"]) for fk in inspector.get_foreign_keys("persona")}
    position_foreign_keys = {tuple(fk["constrained_columns"]) for fk in inspector.get_foreign_keys("persona_puesto")}
    if ("id_linea_habitual",) not in persona_foreign_keys:
        op.create_foreign_key("fk_persona_linea_habitual", "persona", "catalogo", ["id_linea_habitual"], ["id"], ondelete="RESTRICT")
    if ("id_linea",) not in position_foreign_keys:
        op.create_foreign_key("fk_persona_puesto_linea", "persona_puesto", "catalogo", ["id_linea"], ["id"], ondelete="RESTRICT")
    if "referencia_fuente" not in columns("limite"):
        op.add_column("limite", sa.Column("referencia_fuente", sa.Text(), nullable=True))
    if "nota_fuente" not in columns("limite"):
        op.add_column("limite", sa.Column("nota_fuente", sa.Text(), nullable=True))
    if "valor_original" not in columns("importacion_resultado"):
        op.add_column("importacion_resultado", sa.Column("valor_original", sa.Text(), nullable=True))
    if "valor_normativo" not in columns("importacion_resultado"):
        op.add_column("importacion_resultado", sa.Column("valor_normativo", sa.Text(), nullable=True))
    if "plan_reaccion" not in tables:
        op.create_table(
        "plan_reaccion",
        sa.Column("id_desvio", sa.String(length=10), primary_key=True),
        sa.Column("senal", sa.Text(), nullable=False),
        sa.Column("etapa", sa.String(length=120), nullable=False),
        sa.Column("limite_referencia", sa.Text(), nullable=False),
        sa.Column("causas_probables", sa.Text(), nullable=False),
        sa.Column("accion_inmediata", sa.Text(), nullable=False),
        sa.Column("verificacion", sa.Text(), nullable=False),
        sa.Column("plazo_texto", sa.String(length=120), nullable=False),
        sa.Column("registro_escalamiento", sa.Text(), nullable=False),
        sa.Column("plazo_horas", sa.Numeric(8, 2), nullable=True),
        sa.Column("tipo_plazo", sa.String(length=50), nullable=False),
        sa.Column("texto_excel_original", sa.Text(), nullable=True),
        sa.Column("motivo_prevalencia", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if "escala_silo" not in tables:
        op.create_table(
        "escala_silo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grupo_silos", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        sa.Column("vigente_hasta_exclusiva", sa.Date(), nullable=True),
        sa.Column("aprobada_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("grupo_silos", "version", name="uq_escala_silo_grupo_version"),
        )
    if "escala_silo_punto" not in tables:
        op.create_table(
        "escala_silo_punto",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_escala", postgresql.UUID(as_uuid=True), sa.ForeignKey("escala_silo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("altura_m", sa.Numeric(5, 2), nullable=False),
        sa.Column("toneladas", sa.Numeric(8, 2), nullable=False),
        sa.UniqueConstraint("id_escala", "altura_m", name="uq_escala_silo_punto_altura"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    for table in ("escala_silo_punto", "escala_silo", "plan_reaccion"):
        if table in tables:
            op.drop_table(table)

    for table, column in (
        ("importacion_resultado", "valor_normativo"),
        ("importacion_resultado", "valor_original"),
        ("limite", "nota_fuente"),
        ("limite", "referencia_fuente"),
    ):
        if table in tables and column in {item["name"] for item in inspector.get_columns(table)}:
            op.drop_column(table, column)

    for table, column in (("persona_puesto", "id_linea"), ("persona", "id_linea_habitual")):
        if table not in tables:
            continue
        for foreign_key in inspector.get_foreign_keys(table):
            if foreign_key["constrained_columns"] == [column] and foreign_key["name"]:
                op.drop_constraint(foreign_key["name"], table, type_="foreignkey")
        if column in {item["name"] for item in inspector.get_columns(table)}:
            op.drop_column(table, column)

    if "persona" in tables and "es_cuenta_tecnica_dev" in {item["name"] for item in inspector.get_columns("persona")}:
        op.drop_column("persona", "es_cuenta_tecnica_dev")
