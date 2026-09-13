"""Seed concrete permissions required by the authorization policy.

Revision ID: 0011_authorization_permissions
Revises: 0010_stabilization
Create Date: 2026-09-12
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0011_authorization_permissions"
down_revision = "0010_stabilization"
branch_labels = None
depends_on = None


PERMISSIONS = {
    "CARGA": {
        "M0": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"),
        "M2": ("ver",), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"),
        "M11": ("ver",), "M12": ("ver",), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"),
    },
    "SUPERVISION": {
        "M0": ("ver", "crear", "editar", "cerrar", "validar", "anular", "tratar", "verificar"),
        "M2": ("ver", "recalcular"), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"),
        "M11": ("ver",), "M12": ("ver",), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"),
        "M14": ("ver",), "M15": ("ver",),
    },
    "ADMIN": {
        "M0": ("ver", "crear", "editar", "cerrar", "validar", "anular", "tratar", "verificar"),
        "M2": ("ver", "recalcular"), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"),
        "M11": ("ver", "crear", "editar"), "M12": ("ver", "crear", "editar"),
        "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"), "M14": ("ver", "crear", "editar"),
        "M15": ("ver", "crear", "editar", "administrar"),
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    roles = dict(bind.execute(sa.text("SELECT nombre, id FROM rol WHERE nombre IN ('CARGA', 'SUPERVISION', 'ADMIN')")).all())
    permission = sa.table(
        "permiso",
        sa.column("id", sa.Uuid()),
        sa.column("id_rol", sa.Uuid()),
        sa.column("modulo", sa.String()),
        sa.column("accion", sa.String()),
        sa.column("alcance", sa.String()),
    )
    existing = set(bind.execute(sa.select(permission.c.id_rol, permission.c.modulo, permission.c.accion, permission.c.alcance)))
    rows = [
        {"id": uuid4(), "id_rol": roles[role_name], "modulo": module, "accion": action, "alcance": "propio_sector" if role_name == "CARGA" else "todo"}
        for role_name, modules in PERMISSIONS.items()
        if role_name in roles
        for module, actions in modules.items()
        for action in actions
        if (roles[role_name], module, action, "propio_sector" if role_name == "CARGA" else "todo") not in existing
    ]
    if rows:
        op.bulk_insert(permission, rows)


def downgrade() -> None:
    # Permissions may have existed before this migration; do not remove grants on downgrade.
    pass
