"""Stabilization indexes for sync conflicts and applied-limit sequencing.

Revision ID: 0010_stabilization
Revises: 0009_f7_laboratory
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_stabilization"
down_revision = "0009_f7_laboratory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    applied_indexes = {index["name"] for index in inspector.get_indexes("registro_limite_aplicado")}
    conflict_indexes = {index["name"] for index in inspector.get_indexes("conflicto_sincronizacion")}
    if "ix_registro_limite_aplicado_origen_campo" not in applied_indexes:
        op.create_index("ix_registro_limite_aplicado_origen_campo", "registro_limite_aplicado", ["tabla_origen", "campo", "id_registro"])
    if "ix_sync_conflict_open" not in conflict_indexes:
        op.create_index("ix_sync_conflict_open", "conflicto_sincronizacion", ["tabla", "client_uuid", "estado"])


def downgrade() -> None:
    op.drop_index("ix_sync_conflict_open", table_name="conflicto_sincronizacion")
    op.drop_index("ix_registro_limite_aplicado_origen_campo", table_name="registro_limite_aplicado")
