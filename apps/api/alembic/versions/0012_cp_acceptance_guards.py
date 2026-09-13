"""Guard accepted CP rules at the database boundary.

Revision ID: 0012_cp_acceptance_guards
Revises: 0011_authorization_permissions
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_cp_acceptance_guards"
down_revision = "0011_authorization_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    constraints = {item["name"] for item in inspector.get_check_constraints("registro_operativo")}
    if "ck_registro_operativo_anulacion_motivo" not in constraints:
        op.create_check_constraint(
            "ck_registro_operativo_anulacion_motivo",
            "registro_operativo",
            "estado <> 'ANULADO' OR motivo_anulacion IS NOT NULL",
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION impedir_borrado_registro_operativo() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Los registros operativos no se eliminan fisicamente';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER registro_operativo_sin_borrado
        BEFORE DELETE ON registro_operativo
        FOR EACH ROW EXECUTE FUNCTION impedir_borrado_registro_operativo();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS registro_operativo_sin_borrado ON registro_operativo")
    op.execute("DROP FUNCTION IF EXISTS impedir_borrado_registro_operativo()")
    op.drop_constraint("ck_registro_operativo_anulacion_motivo", "registro_operativo", type_="check")
