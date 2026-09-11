from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import LimitVersion, SyncConflict, SyncRevision
from app.services.limits import evaluate_limit
from app.services.states import can_edit_record, can_transition_record
from app.services.synchronization import record_revision


def test_limit_operator_inclusivity_is_explicit():
    version = LimitVersion(id_limite="TEST", vigente_desde=date.today(), valor_min=Decimal("2"), operador_min=">", nivel="ADVERTENCIA", motivo_cambio="TEST", id_usuario_alta=uuid4())
    assert evaluate_limit(version, Decimal("2")) == "FUERA_DE_RANGO"
    version.operador_min = ">="
    assert evaluate_limit(version, Decimal("2")) == "EN_RANGO"


def test_record_state_machine_blocks_carga_closed_edits():
    assert can_edit_record("CERRADO", actor_role="CARGA", is_creator=True, shift_closed=False) is False
    assert can_edit_record("BORRADOR", actor_role="CARGA", is_creator=True, shift_closed=False) is True
    assert can_transition_record("BORRADOR", "CERRADO", actor_role="CARGA", is_creator=True) is True
    assert can_transition_record("CERRADO", "VALIDADO", actor_role="CARGA", is_creator=True) is False


def test_stale_or_closed_sync_creates_conflict_and_retry_is_idempotent():
    record_id, client_id = uuid4(), uuid4()
    with SessionLocal.begin() as db:
        revision, conflict = record_revision(db, table="reg_prueba", record_id=record_id, client_uuid=client_id, revision=1, client_version={"revision": 1}, server_version={}, record_closed=False)
        assert revision is not None and conflict is None
    with SessionLocal.begin() as db:
        revision, conflict = record_revision(db, table="reg_prueba", record_id=record_id, client_uuid=client_id, revision=1, client_version={"revision": 1}, server_version={}, record_closed=False)
        assert revision is not None and conflict is None
    with SessionLocal.begin() as db:
        revision, conflict = record_revision(db, table="reg_prueba", record_id=record_id, client_uuid=uuid4(), revision=1, client_version={"revision": 1}, server_version={"revision": 1}, record_closed=True)
        assert revision is None and conflict is not None
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SyncRevision)))) == 1
        assert len(list(db.scalars(select(SyncConflict)))) == 1
