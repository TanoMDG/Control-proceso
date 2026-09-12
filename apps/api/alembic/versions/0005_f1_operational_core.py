"""F1 operational records and deviation lifecycle."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_f1_operational_core"
down_revision = "0004_ft_operational_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("registro_operativo")}
    tables = set(inspector.get_table_names())

    def create_table_if_missing(name: str, *args: object) -> None:
        # Earlier revisions may have created current-model tables; avoid relying
        # on the inspector snapshot while this migration is in progress.
        if not sa.inspect(bind).has_table(name):
            op.create_table(name, *args)

    if "sector" not in columns:
        op.add_column("registro_operativo", sa.Column("sector", sa.String(length=40), nullable=True))
        op.execute("UPDATE registro_operativo SET sector = 'Molienda' WHERE modulo IN ('M1', 'M2', 'M3', 'M6')")
        op.execute("UPDATE registro_operativo SET sector = 'Sin asignar' WHERE sector IS NULL")
        op.alter_column("registro_operativo", "sector", nullable=False)
    create_table_if_missing("evento_desvio", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("id_registro", postgresql.UUID(as_uuid=True), sa.ForeignKey("registro_operativo.id", ondelete="RESTRICT"), nullable=False), sa.Column("campo", sa.String(80), nullable=False), sa.Column("id_limite", sa.String(10), sa.ForeignKey("limite.id", ondelete="RESTRICT"), nullable=False), sa.Column("id_limite_version", postgresql.UUID(as_uuid=True), sa.ForeignKey("limite_version.id", ondelete="RESTRICT"), nullable=False), sa.Column("id_desvio", sa.String(10), sa.ForeignKey("plan_reaccion.id_desvio", ondelete="RESTRICT"), nullable=False), sa.Column("clave_idempotencia", sa.String(180), unique=True, nullable=False), sa.Column("secuencia_clave", sa.String(180), nullable=False), sa.Column("estado", sa.String(20), nullable=False, server_default="ABIERTO"), sa.Column("valor_actual", sa.Numeric(12, 4)), sa.Column("vence_en", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.CheckConstraint("estado IN ('ABIERTO', 'EN_TRATAMIENTO', 'VERIFICADO', 'VENCIDO', 'ESCALADO', 'CERRADO', 'INVALIDADO')", name="ck_evento_desvio_estado"))
    if "evento_desvio" not in tables:
        op.create_index("ix_evento_desvio_estado", "evento_desvio", ["estado", "id_desvio"])
    create_table_if_missing("evento_desvio_historial", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("id_evento", postgresql.UUID(as_uuid=True), sa.ForeignKey("evento_desvio.id", ondelete="CASCADE"), nullable=False), sa.Column("estado_anterior", sa.String(20)), sa.Column("estado_nuevo", sa.String(20), nullable=False), sa.Column("comentario", sa.Text()), sa.Column("id_usuario", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False), sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_table("evento_desvio_historial")
    op.drop_index("ix_evento_desvio_estado", table_name="evento_desvio")
    op.drop_table("evento_desvio")
    op.drop_column("registro_operativo", "sector")
