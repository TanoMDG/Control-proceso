"""Add operational record timestamps for already upgraded FT databases.

Revision ID: 0004_ft_operational_timestamps
Revises: 0003_ft_paper_transition
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_ft_operational_timestamps"
down_revision = "0003_ft_paper_transition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("registro_operativo")}
    if "created_at" not in columns:
        op.add_column("registro_operativo", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    if "updated_at" not in columns:
        op.add_column("registro_operativo", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("registro_operativo")}
    if "updated_at" in columns:
        op.drop_column("registro_operativo", "updated_at")
    if "created_at" in columns:
        op.drop_column("registro_operativo", "created_at")
