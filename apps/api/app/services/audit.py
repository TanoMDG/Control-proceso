from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.core import AuditLog


def write_audit(
    db: Session,
    *,
    user_id: UUID | None,
    table: str,
    record_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    db.add(AuditLog(id_usuario=user_id, tabla=table, id_registro=record_id, accion=action, valor_anterior=before, valor_nuevo=after, motivo=reason))
