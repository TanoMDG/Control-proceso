"""F0 foundation schema.

Revision ID: 0001_f0_foundation
Revises:
Create Date: 2026-09-11
"""
from alembic import op

from app.db.base import Base
import app.models.core  # noqa: F401

revision = "0001_f0_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # F0 is the initial schema; migrations, not application startup, own DDL.
    Base.metadata.create_all(bind=op.get_bind())
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS btree_gist;
        ALTER TABLE limite_version ADD CONSTRAINT ex_limite_version_no_solapada
          EXCLUDE USING gist (
            id_limite WITH =,
            daterange(vigente_desde, COALESCE(vigente_hasta_exclusiva, 'infinity'::date), '[)') WITH &&
          ) WHERE (estado <> 'CANCELADA');
        ALTER TABLE parametro_sistema_version ADD CONSTRAINT ex_parametro_version_no_solapada
          EXCLUDE USING gist (
            clave WITH =,
            daterange(vigente_desde, COALESCE(vigente_hasta_exclusiva, 'infinity'::date), '[)') WITH &&
          );
        CREATE OR REPLACE FUNCTION impedir_mutacion_auditoria() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'La auditoria es inmutable';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER auditoria_solo_insercion
        BEFORE UPDATE OR DELETE ON auditoria
        FOR EACH ROW EXECUTE FUNCTION impedir_mutacion_auditoria();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS auditoria_solo_insercion ON auditoria")
    op.execute("DROP FUNCTION IF EXISTS impedir_mutacion_auditoria()")
    Base.metadata.drop_all(bind=op.get_bind())
