from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import SyncConflict, SyncRevision


def record_conflict(
    db: Session,
    *,
    table: str,
    record_id: UUID,
    client_uuid: UUID,
    client_version: dict,
    server_version: dict,
) -> SyncConflict:
    """Keeps one open conflict for an identical stale client revision."""
    conflict = db.scalar(
        select(SyncConflict).where(
            SyncConflict.tabla == table,
            SyncConflict.id_registro == record_id,
            SyncConflict.client_uuid == client_uuid,
            SyncConflict.revision_cliente == client_version,
            SyncConflict.estado == "ABIERTO",
        )
    )
    if conflict is None:
        conflict = SyncConflict(tabla=table, id_registro=record_id, client_uuid=client_uuid, revision_cliente=client_version, version_servidor=server_version)
        db.add(conflict)
    return conflict


def record_revision(
    db: Session,
    *,
    table: str,
    record_id: UUID,
    client_uuid: UUID,
    revision: int,
    client_version: dict,
    server_version: dict,
    record_closed: bool,
) -> tuple[SyncRevision | None, SyncConflict | None]:
    """Stores idempotent client revisions and surfaces stale/closed writes as conflicts."""
    duplicate = db.scalar(select(SyncRevision).where(SyncRevision.tabla == table, SyncRevision.client_uuid == client_uuid, SyncRevision.revision == revision))
    if duplicate is not None:
        return duplicate, None
    latest = db.scalar(select(SyncRevision).where(SyncRevision.tabla == table, SyncRevision.id_registro == record_id).order_by(SyncRevision.revision.desc()))
    if record_closed or (latest is not None and revision <= latest.revision):
        return None, record_conflict(db, table=table, record_id=record_id, client_uuid=client_uuid, client_version=client_version, server_version=server_version)
    revision_row = SyncRevision(tabla=table, id_registro=record_id, client_uuid=client_uuid, revision=revision, version_cliente=client_version)
    db.add(revision_row)
    return revision_row, None
