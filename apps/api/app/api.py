from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.core import AnalyticsRun, AuditLog, Catalog, DeviationEvent, DeviationHistory, ImportResult, ImportRun, Limit, LimitVersion, OperationalRecord, Permission, Person, PersonPosition, ProductionCalendar, Role, ShiftFact, ShiftReceipt, SyncConflict, SystemParameterVersion, TemporalMeasurementFact, User
from app.schemas import (AnalyticsRebuildOutput, AuditOutput, CalendarInput, CalendarOutput, CatalogInput, CatalogOutput, CatalogPatch, DeferredRecordInput, DeviationOutput, ImportPreview, LimitInput, LimitOutput, LimitVersionInput, LimitVersionOutput, LoginInput, OperationalRecordOutput, ParameterInput, PermissionInput, PersonInput, PersonOutput, PersonPatch, PositionInput, RecordActionInput, RecordUpdateInput, RoleOutput, ShiftReceiptInput, SyncConflictOutput, SyncConflictResolution, TokenOutput, UserInput, UserOutput, UserPatch)
from app.services.audit import write_audit
from app.services.importer import validate_excel_source
from app.services.operations import MODULE_SECTOR, evaluate_record, normalized_data
from app.services.analytics import rebuild_analytics
from app.services.security import current_user, hash_password, make_token, require_admin, require_permission, verify_password

router = APIRouter(prefix="/api/v1")


def get_role(db: Session, user: User) -> Role:
    role = db.get(Role, user.id_rol)
    if role is None:
        raise HTTPException(status_code=403, detail="Rol no disponible")
    return role


def require_supervision(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    role = get_role(db, user)
    if role.nombre not in {"SUPERVISION", "ADMIN"} or user.consulta_remota:
        raise HTTPException(status_code=403, detail="Requiere SUPERVISION o ADMIN")
    return user


def audit_payload(model) -> dict:
    return {column.name: str(value) if value is not None else None for column, value in ((column, getattr(model, column.name)) for column in model.__table__.columns) if column.name not in {"password_hash"}}


def expected_operational_date(turno_codigo: str, instante_medicion: datetime) -> date:
    if instante_medicion.tzinfo is None:
        raise HTTPException(status_code=422, detail="instante_medicion debe incluir zona horaria")
    normalized_shift = turno_codigo.replace("_", "-").upper()
    measurement_date = instante_medicion.date()
    if normalized_shift in {"20-04", "20 A 04", "NOCHE"} and instante_medicion.hour < 4:
        return measurement_date - timedelta(days=1)
    return measurement_date


def printable_form(modulo: str) -> str:
    labels = {
        "m1": "M1 Molienda", "m2": "M2 Madirex", "m3": "M3 Lecho fluido / K-Sider / Silos",
        "m6": "M6 Paradas", "m10": "M10 Espesores",
    }
    title = labels.get(modulo.lower())
    if title is None:
        raise HTTPException(status_code=404, detail="Formulario inexistente")
    pages = ["Prensa 1", "Prensa 2", "Prensa 3"] if modulo.lower() == "m10" else [""]
    page_html = "".join(
        f"<section class='page'><header><strong>Control de Proceso</strong><span>{title}</span><span>{page}</span></header>"
        "<p>Fecha operativa: __________ Turno: __________ Responsable: __________ Formulario: __________</p>"
        "<table><thead><tr><th>Hora</th><th>Variable / medicion</th><th>Valor</th><th>Observaciones</th><th>Firma</th></tr></thead>"
        "<tbody>" + "<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td></tr>" * 12 + "</tbody></table>"
        "<footer>Conserve fecha, hora, turno y responsable originales. Digitacion: usuario y fecha/hora.</footer></section>"
        for page in pages
    )
    return "<html><head><style>@page{size:A4 landscape;margin:12mm}.page{page-break-after:always;font-family:Arial}header{display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:8px}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{border:1px solid #333;height:26px;text-align:left;padding:3px}footer{margin-top:10px;font-size:11px}</style></head><body>" + page_html + "</body></html>"


def assert_record_access(db: Session, actor: User, sector: str, *, write: bool = False) -> None:
    role = get_role(db, actor).nombre
    if actor.consulta_remota or role not in {"CARGA", "SUPERVISION", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Permiso operativo insuficiente")
    if role == "CARGA" and actor.sector != sector:
        raise HTTPException(status_code=403, detail="CARGA solo opera su sector")
    if write and role == "CARGA" and sector != actor.sector:
        raise HTTPException(status_code=403, detail="CARGA solo escribe su sector")


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "F2"}


@router.get("/exportar", response_class=HTMLResponse)
def export_blank_form(modulo: str, _: User = Depends(require_permission("M0", "ver"))) -> str:
    return printable_form(modulo)


@router.post("/registros/{modulo}", response_model=OperationalRecordOutput, status_code=201)
def create_deferred_record(modulo: str, payload: DeferredRecordInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    module = modulo.upper()
    if module not in MODULE_SECTOR:
        raise HTTPException(status_code=404, detail="Modulo operativo inexistente")
    sector = MODULE_SECTOR[module]
    assert_record_access(db, actor, sector, write=True)
    responsible_id = payload.id_responsable or actor.id_persona
    if payload.origen_dato == "papel_digitado" and payload.id_responsable is None:
        raise HTTPException(status_code=422, detail="Responsable original obligatorio para formulario en papel")
    if db.get(Person, responsible_id) is None:
        raise HTTPException(status_code=422, detail="Responsable inexistente")
    if payload.fecha_operativa != expected_operational_date(payload.turno_codigo, payload.instante_medicion):
        raise HTTPException(status_code=422, detail="La fecha operativa no corresponde al turno y momento de medicion originales")
    existing = db.scalar(select(OperationalRecord).where(OperationalRecord.modulo == module, OperationalRecord.client_uuid == payload.client_uuid))
    if existing is not None:
        return existing
    data = normalized_data(db, module, payload.datos, payload.fecha_operativa)
    if module == "M1" and data.get("tipo_registro") == "resumen_turno":
        summaries = db.scalars(select(OperationalRecord).where(OperationalRecord.modulo == "M1", OperationalRecord.fecha_operativa == payload.fecha_operativa, OperationalRecord.turno_codigo == payload.turno_codigo, OperationalRecord.sector == sector))
        if any(row.datos.get("tipo_registro") == "resumen_turno" for row in summaries):
            raise HTTPException(status_code=422, detail="Solo se admite un resumen de produccion por turno")
    record = OperationalRecord(
        modulo=module,
        sector=sector,
        client_uuid=payload.client_uuid,
        estado="BORRADOR", origen_dato=payload.origen_dato,
        fecha_operativa=payload.fecha_operativa,
        turno_codigo=payload.turno_codigo,
        instante_medicion=payload.instante_medicion,
        id_responsable=responsible_id,
        id_usuario_digitador=actor.id if payload.origen_dato == "papel_digitado" else None,
        creado_por=actor.id,
        datos=data,
    )
    db.add(record)
    db.flush()
    evaluate_record(db, record, actor.id)
    write_audit(db, user_id=actor.id, table="registro_operativo", record_id=str(record.id), action="DIGITACION_PAPEL" if payload.origen_dato == "papel_digitado" else "ALTA", after=audit_payload(record), reason="Carga diferida desde formulario en papel" if payload.origen_dato == "papel_digitado" else None)
    db.commit()
    db.refresh(record)
    return record


@router.get("/registros/{modulo}", response_model=list[OperationalRecordOutput])
def list_records(modulo: str, desde: date | None = None, hasta: date | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    module, sector = modulo.upper(), MODULE_SECTOR.get(modulo.upper())
    if sector is None:
        raise HTTPException(status_code=404, detail="Modulo operativo inexistente")
    assert_record_access(db, actor, sector)
    role = get_role(db, actor).nombre
    statement = select(OperationalRecord).where(OperationalRecord.modulo == module)
    if role == "CARGA":
        lower = date.today() - timedelta(days=6)
        if desde and desde < lower:
            raise HTTPException(status_code=403, detail="CARGA solo consulta los ultimos siete dias")
        statement = statement.where(OperationalRecord.sector == actor.sector, OperationalRecord.fecha_operativa >= lower)
    if desde: statement = statement.where(OperationalRecord.fecha_operativa >= desde)
    if hasta: statement = statement.where(OperationalRecord.fecha_operativa <= hasta)
    return list(db.scalars(statement.order_by(OperationalRecord.instante_medicion.desc())))


@router.put("/registros/{modulo}/{record_id}", response_model=OperationalRecordOutput)
def correct_record(modulo: str, record_id: UUID, payload: RecordUpdateInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    record = db.get(OperationalRecord, record_id)
    if record is None or record.modulo != modulo.upper(): raise HTTPException(status_code=404, detail="Registro inexistente")
    assert_record_access(db, actor, record.sector, write=True)
    role = get_role(db, actor).nombre
    if record.revision != payload.revision:
        conflict = SyncConflict(tabla="registro_operativo", id_registro=record.id, client_uuid=record.client_uuid, revision_cliente={"revision": payload.revision, "datos": payload.datos}, version_servidor={"revision": record.revision, "datos": record.datos})
        db.add(conflict); db.commit()
        raise HTTPException(status_code=409, detail="Revision desactualizada; conflicto creado")
    if role == "CARGA" and (record.estado != "BORRADOR" or record.creado_por != actor.id): raise HTTPException(status_code=403, detail="CARGA solo edita sus borradores")
    if record.estado != "BORRADOR" and (role not in {"SUPERVISION", "ADMIN"} or not payload.motivo_correccion): raise HTTPException(status_code=422, detail="La correccion requiere SUPERVISION/ADMIN y motivo")
    before = audit_payload(record)
    previous_burner = record.datos.get("temperatura_quemador")
    requested_burner = payload.datos.get("temperatura_quemador")
    if previous_burner is not None and requested_burner is not None and str(previous_burner) != str(requested_burner):
        if payload.datos.get("temperatura_quemador_previa") != previous_burner or not payload.datos.get("motivo_cambio_quemador"):
            raise HTTPException(status_code=422, detail="El cambio de quemador requiere valor previo y motivo")
    record.datos, record.motivo_correccion, record.revision = normalized_data(db, record.modulo, payload.datos, record.fecha_operativa), payload.motivo_correccion, record.revision + 1
    evaluate_record(db, record, actor.id)
    write_audit(db, user_id=actor.id, table="registro_operativo", record_id=str(record.id), action="CORRECCION", before=before, after=audit_payload(record), reason=payload.motivo_correccion)
    db.commit(); db.refresh(record); return record


@router.post("/registros/{modulo}/{record_id}/cerrar", response_model=OperationalRecordOutput)
def close_record(modulo: str, record_id: UUID, payload: RecordActionInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    record = db.get(OperationalRecord, record_id)
    if record is None or record.modulo != modulo.upper(): raise HTTPException(status_code=404, detail="Registro inexistente")
    assert_record_access(db, actor, record.sector, write=True)
    if record.estado != "BORRADOR": raise HTTPException(status_code=422, detail="Solo se cierran borradores")
    role = get_role(db, actor).nombre
    if role == "CARGA" and record.creado_por != actor.id: raise HTTPException(status_code=403, detail="CARGA solo cierra sus registros")
    record.estado, record.cerrado_por, record.cerrado_en = "CERRADO", actor.id, datetime.now(timezone.utc)
    write_audit(db, user_id=actor.id, table="registro_operativo", record_id=str(record.id), action="CIERRE", after=audit_payload(record), reason=payload.comentario)
    db.commit(); db.refresh(record); return record


@router.post("/registros/{modulo}/{record_id}/validar", response_model=OperationalRecordOutput)
def validate_record(modulo: str, record_id: UUID, payload: RecordActionInput, actor: User = Depends(require_supervision), db: Session = Depends(get_db)):
    record = db.get(OperationalRecord, record_id)
    if record is None or record.modulo != modulo.upper(): raise HTTPException(status_code=404, detail="Registro inexistente")
    if record.estado != "CERRADO": raise HTTPException(status_code=422, detail="Solo se validan registros cerrados")
    record.estado = "VALIDADO"; write_audit(db, user_id=actor.id, table="registro_operativo", record_id=str(record.id), action="VALIDACION", after=audit_payload(record), reason=payload.comentario)
    db.commit(); db.refresh(record); return record


@router.post("/registros/{modulo}/{record_id}/anular", response_model=OperationalRecordOutput)
def void_record(modulo: str, record_id: UUID, payload: RecordActionInput, actor: User = Depends(require_supervision), db: Session = Depends(get_db)):
    record = db.get(OperationalRecord, record_id)
    if record is None or record.modulo != modulo.upper(): raise HTTPException(status_code=404, detail="Registro inexistente")
    if record.estado == "ANULADO": raise HTTPException(status_code=422, detail="Registro ya anulado")
    record.estado, record.motivo_anulacion = "ANULADO", payload.comentario
    write_audit(db, user_id=actor.id, table="registro_operativo", record_id=str(record.id), action="ANULACION", after=audit_payload(record), reason=payload.comentario)
    db.commit(); db.refresh(record); return record


def event_with_deadline(event: DeviationEvent, db: Session) -> DeviationEvent:
    if event.estado in {"ABIERTO", "EN_TRATAMIENTO", "VERIFICADO"} and event.vence_en and event.vence_en < datetime.now(timezone.utc): event.estado = "VENCIDO"
    return event


@router.get("/desvios", response_model=list[DeviationOutput])
def list_deviations(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    role = get_role(db, actor).nombre
    if actor.consulta_remota or role not in {"CARGA", "SUPERVISION", "ADMIN"}: raise HTTPException(status_code=403, detail="Permiso insuficiente")
    statement = select(DeviationEvent).join(OperationalRecord, OperationalRecord.id == DeviationEvent.id_registro)
    if role == "CARGA": statement = statement.where(OperationalRecord.sector == actor.sector, OperationalRecord.fecha_operativa >= date.today() - timedelta(days=6))
    events = [event_with_deadline(event, db) for event in db.scalars(statement.order_by(DeviationEvent.created_at.desc()))]
    db.commit()
    return events


def transition_deviation(event_id: UUID, action: str, payload: RecordActionInput, actor: User, db: Session):
    event = db.get(DeviationEvent, event_id)
    if event is None: raise HTTPException(status_code=404, detail="Desvio inexistente")
    record = db.get(OperationalRecord, event.id_registro); assert record is not None
    assert_record_access(db, actor, record.sector, write=True)
    role, previous = get_role(db, actor).nombre, event.estado
    target = {"tratar": "EN_TRATAMIENTO", "verificar": "VERIFICADO", "cerrar": "CERRADO"}.get(action)
    if target is None: raise HTTPException(status_code=404, detail="Accion inexistente")
    if action == "tratar" and previous not in {"ABIERTO", "ESCALADO", "VENCIDO"}: raise HTTPException(status_code=422, detail="Transicion invalida")
    if action == "verificar" and previous != "EN_TRATAMIENTO": raise HTTPException(status_code=422, detail="Debe tratarse antes de verificar")
    if action == "cerrar" and (role not in {"SUPERVISION", "ADMIN"} or previous != "VERIFICADO"): raise HTTPException(status_code=422, detail="El cierre requiere SUPERVISION/ADMIN y verificacion")
    event.estado = target
    db.add(DeviationHistory(id_evento=event.id, estado_anterior=previous, estado_nuevo=target, comentario=payload.comentario, id_usuario=actor.id))
    write_audit(db, user_id=actor.id, table="evento_desvio", record_id=str(event.id), action=action.upper(), after=audit_payload(event), reason=payload.comentario)
    db.commit(); db.refresh(event); return event


@router.post("/desvios/{event_id}/tratar", response_model=DeviationOutput)
def treat_deviation(event_id: UUID, payload: RecordActionInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transition_deviation(event_id, "tratar", payload, actor, db)


@router.post("/desvios/{event_id}/verificar", response_model=DeviationOutput)
def verify_deviation(event_id: UUID, payload: RecordActionInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transition_deviation(event_id, "verificar", payload, actor, db)


@router.post("/desvios/{event_id}/cerrar", response_model=DeviationOutput)
def close_deviation(event_id: UUID, payload: RecordActionInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return transition_deviation(event_id, "cerrar", payload, actor, db)


@router.post("/turnos/{fecha_operativa}/{turno_codigo}/{sector}/recibir", status_code=201)
def receive_shift(fecha_operativa: date, turno_codigo: str, sector: str, payload: ShiftReceiptInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_record_access(db, actor, sector, write=True)
    receipt = ShiftReceipt(fecha_operativa=fecha_operativa, turno_codigo=turno_codigo, sector=sector, id_usuario=actor.id, observacion=payload.observacion)
    db.add(receipt); db.flush()
    write_audit(db, user_id=actor.id, table="recepcion_turno", record_id=str(receipt.id), action="RECEPCION", after=audit_payload(receipt), reason=payload.observacion)
    db.commit(); return {"id": str(receipt.id)}


@router.post("/analitica/recalcular", response_model=AnalyticsRebuildOutput)
def recalculate_analytics(actor: User = Depends(require_supervision), db: Session = Depends(get_db)):
    run = rebuild_analytics(db)
    write_audit(db, user_id=actor.id, table="recalculo_analitico", record_id=str(run.id), action="RECALCULO", after=audit_payload(run))
    db.commit(); db.refresh(run); return run


@router.get("/kpi")
def get_kpi(desde: date | None = None, hasta: date | None = None, turno: str | None = None, linea: str | None = None, contexto: str | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    role = get_role(db, actor).nombre
    if role not in {"CARGA", "SUPERVISION", "ADMIN"}: raise HTTPException(status_code=403, detail="Permiso insuficiente")
    statement = select(ShiftFact)
    if role == "CARGA": statement = statement.where(ShiftFact.contexto_clave == actor.sector, ShiftFact.fecha_operativa >= date.today() - timedelta(days=6))
    if desde: statement = statement.where(ShiftFact.fecha_operativa >= desde)
    if hasta: statement = statement.where(ShiftFact.fecha_operativa <= hasta)
    if turno: statement = statement.where(ShiftFact.turno_codigo == turno)
    if linea: statement = statement.where(ShiftFact.linea_clave == linea)
    if contexto: statement = statement.where(ShiftFact.contexto_clave == contexto)
    facts = list(db.scalars(statement.order_by(ShiftFact.fecha_operativa, ShiftFact.turno_codigo)))
    last = db.scalar(select(AnalyticsRun).where(AnalyticsRun.estado == "COMPLETADO").order_by(AnalyticsRun.completado_en.desc()))
    return {"ultimo_recalculo": last.completado_en if last else None, "hechos": [{"fecha_operativa": row.fecha_operativa, "turno": row.turno_codigo, "contexto": row.contexto_clave, "metricas": row.metricas} for row in facts]}


@router.get("/kpi/tendencias")
def kpi_trends(metrica: str, desde: date | None = None, hasta: date | None = None, turno: str | None = None, contexto: str | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    role = get_role(db, actor).nombre
    if role not in {"CARGA", "SUPERVISION", "ADMIN"}: raise HTTPException(status_code=403, detail="Permiso insuficiente")
    statement = select(TemporalMeasurementFact).where(TemporalMeasurementFact.metrica == metrica)
    if role == "CARGA": statement = statement.where(TemporalMeasurementFact.contexto["sector"].astext == actor.sector, TemporalMeasurementFact.fecha_operativa >= date.today() - timedelta(days=6))
    if desde: statement = statement.where(TemporalMeasurementFact.fecha_operativa >= desde)
    if hasta: statement = statement.where(TemporalMeasurementFact.fecha_operativa <= hasta)
    if turno: statement = statement.where(TemporalMeasurementFact.turno_codigo == turno)
    if contexto: statement = statement.where(TemporalMeasurementFact.contexto["sector"].astext == contexto)
    rows = list(db.scalars(statement.order_by(TemporalMeasurementFact.instante_operativo)))
    return {"metrica": metrica, "puntos": [{"instante": row.instante_operativo, "valor": row.valor, "unidad": row.unidad, "banda_limite": row.contexto.get("banda_limite")} for row in rows]}


@router.get("/kpi/pareto-paradas")
def stoppage_pareto(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    payload = get_kpi(actor=actor, db=db)
    totals: dict[str, float] = {}
    for fact in payload["hechos"]:
        for stop in fact["metricas"].get("paradas", []): totals[stop["causa"]] = totals.get(stop["causa"], 0) + stop["duracion_horas"]
    return {"ultimo_recalculo": payload["ultimo_recalculo"], "pareto": [{"causa": cause, "duracion_horas": duration} for cause, duration in sorted(totals.items(), key=lambda row: row[1], reverse=True)]}


@router.post("/auth/login", response_model=TokenOutput)
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.nombre_usuario == payload.username))
    now = datetime.now(timezone.utc)
    if user is None or not user.activo or (user.bloqueado_hasta and user.bloqueado_hasta > now) or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.intentos_fallidos += 1
            if user.intentos_fallidos >= 5:
                user.bloqueado_hasta = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    role = get_role(db, user)
    token, expires_at = make_token(user, role)
    db.commit()
    return TokenOutput(access_token=token, expires_at=expires_at)


@router.get("/roles", response_model=list[RoleOutput])
def list_roles(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(Role).order_by(Role.nombre)))


@router.post("/roles/{role_id}/permisos", status_code=201)
def create_permission(role_id: UUID, payload: PermissionInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(Role, role_id) is None:
        raise HTTPException(status_code=404, detail="Rol inexistente")
    permission = Permission(id_rol=role_id, **payload.model_dump())
    db.add(permission)
    write_audit(db, user_id=actor.id, table="permiso", record_id=str(permission.id), action="ALTA", after=payload.model_dump(mode="json"))
    db.commit()
    return {"id": str(permission.id)}


@router.get("/personas", response_model=list[PersonOutput])
def list_people(incluir_inactivos: bool = False, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    statement = select(Person).order_by(Person.legajo)
    if not incluir_inactivos:
        statement = statement.where(Person.activo.is_(True))
    return list(db.scalars(statement))


@router.post("/personas", response_model=PersonOutput, status_code=201)
def create_person(payload: PersonInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    person = Person(**payload.model_dump(), activo=True, fecha_baja=None)
    db.add(person)
    db.flush()
    write_audit(db, user_id=actor.id, table="persona", record_id=str(person.id), action="ALTA", after=audit_payload(person))
    db.commit()
    db.refresh(person)
    return person


@router.patch("/personas/{person_id}", response_model=PersonOutput)
def update_person(person_id: UUID, payload: PersonPatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Persona inexistente")
    before = audit_payload(person)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("activo") is False and not changes.get("fecha_baja"):
        raise HTTPException(status_code=422, detail="fecha_baja es obligatoria al desactivar")
    if changes.get("activo") is True:
        changes["fecha_baja"] = None
    for field, value in changes.items():
        setattr(person, field, value)
    write_audit(db, user_id=actor.id, table="persona", record_id=str(person.id), action="MODIFICACION", before=before, after=audit_payload(person), reason="Actualizacion de persona")
    db.commit()
    db.refresh(person)
    return person


@router.post("/personas/{person_id}/puestos", status_code=201)
def add_position(person_id: UUID, payload: PositionInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(Person, person_id) is None:
        raise HTTPException(status_code=404, detail="Persona inexistente")
    position = PersonPosition(id_persona=person_id, **payload.model_dump())
    db.add(position)
    db.flush()
    write_audit(db, user_id=actor.id, table="persona_puesto", record_id=str(position.id), action="ALTA", after=payload.model_dump(mode="json"))
    db.commit()
    return {"id": str(position.id)}


@router.get("/usuarios", response_model=list[UserOutput])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.nombre_usuario)))


@router.post("/usuarios", response_model=UserOutput, status_code=201)
def create_user(payload: UserInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    person = db.get(Person, payload.id_persona)
    if person is None or not person.activo:
        raise HTTPException(status_code=422, detail="La persona debe existir y estar activa")
    if db.get(Role, payload.id_rol) is None:
        raise HTTPException(status_code=422, detail="Rol inexistente")
    user = User(id_persona=payload.id_persona, nombre_usuario=payload.nombre_usuario, password_hash=hash_password(payload.password), id_rol=payload.id_rol, sector=payload.sector, consulta_remota=payload.consulta_remota)
    db.add(user)
    db.flush()
    write_audit(db, user_id=actor.id, table="usuario", record_id=str(user.id), action="ALTA", after=audit_payload(user))
    db.commit()
    db.refresh(user)
    return user


@router.patch("/usuarios/{user_id}", response_model=UserOutput)
def update_user(user_id: UUID, payload: UserPatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario inexistente")
    before = audit_payload(user)
    changes = payload.model_dump(exclude_unset=True)
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    if "id_rol" in changes and db.get(Role, changes["id_rol"]) is None:
        raise HTTPException(status_code=422, detail="Rol inexistente")
    for field, value in changes.items():
        setattr(user, field, value)
    write_audit(db, user_id=actor.id, table="usuario", record_id=str(user.id), action="MODIFICACION", before=before, after=audit_payload(user), reason="Actualizacion de usuario")
    db.commit()
    db.refresh(user)
    return user


@router.get("/catalogos/{tipo}", response_model=list[CatalogOutput])
def list_catalogs(tipo: str, incluir_inactivos: bool = False, _: User = Depends(require_permission("M11", "ver")), db: Session = Depends(get_db)):
    statement = select(Catalog).where(Catalog.tipo == tipo).order_by(Catalog.codigo)
    if not incluir_inactivos:
        statement = statement.where(Catalog.activo.is_(True))
    return list(db.scalars(statement))


@router.post("/catalogos", response_model=CatalogOutput, status_code=201)
def create_catalog(payload: CatalogInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    catalog = Catalog(**payload.model_dump(), activo=True, fecha_baja=None)
    db.add(catalog)
    db.flush()
    write_audit(db, user_id=actor.id, table="catalogo", record_id=str(catalog.id), action="ALTA", after=audit_payload(catalog))
    db.commit()
    db.refresh(catalog)
    return catalog


@router.patch("/catalogos/{catalog_id}", response_model=CatalogOutput)
def update_catalog(catalog_id: UUID, payload: CatalogPatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    catalog = db.get(Catalog, catalog_id)
    if catalog is None:
        raise HTTPException(status_code=404, detail="Catalogo inexistente")
    before = audit_payload(catalog)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("activo") is False and not changes.get("fecha_baja"):
        raise HTTPException(status_code=422, detail="fecha_baja es obligatoria al desactivar")
    if changes.get("activo") is True:
        changes["fecha_baja"] = None
    for field, value in changes.items():
        setattr(catalog, field, value)
    write_audit(db, user_id=actor.id, table="catalogo", record_id=str(catalog.id), action="MODIFICACION", before=before, after=audit_payload(catalog), reason="Actualizacion de catalogo")
    db.commit()
    db.refresh(catalog)
    return catalog


def assert_no_overlap(db: Session, limit_id: str, start: date, end: date | None, excluding: UUID | None = None) -> None:
    statement = select(LimitVersion).where(LimitVersion.id_limite == limit_id, LimitVersion.estado != "CANCELADA")
    if excluding is not None:
        statement = statement.where(LimitVersion.id != excluding)
    for version in db.scalars(statement):
        version_end = version.vigente_hasta_exclusiva
        if (end is None or version.vigente_desde < end) and (version_end is None or start < version_end):
            raise HTTPException(status_code=422, detail="La version se solapa con una version existente")


@router.get("/limites", response_model=list[LimitVersionOutput])
def list_limits(fecha: date = Query(default_factory=date.today), _: User = Depends(require_permission("M12", "ver")), db: Session = Depends(get_db)):
    statement = select(LimitVersion).where(LimitVersion.vigente_desde <= fecha, or_(LimitVersion.vigente_hasta_exclusiva.is_(None), LimitVersion.vigente_hasta_exclusiva > fecha), LimitVersion.estado != "CANCELADA").order_by(LimitVersion.id_limite)
    return list(db.scalars(statement))


@router.post("/limites", response_model=LimitOutput, status_code=201)
def create_limit(payload: LimitInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = Limit(**payload.model_dump())
    db.add(item)
    db.flush()
    write_audit(db, user_id=actor.id, table="limite", record_id=item.id, action="ALTA", after=audit_payload(item))
    db.commit()
    return item


@router.post("/limites/{limit_id}/versiones", response_model=LimitVersionOutput, status_code=201)
def create_limit_version(limit_id: str, payload: LimitVersionInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(Limit, limit_id) is None:
        raise HTTPException(status_code=404, detail="Limite inexistente")
    assert_no_overlap(db, limit_id, payload.vigente_desde, payload.vigente_hasta_exclusiva)
    limit_state = "VIGENTE" if payload.vigente_desde <= date.today() else "PROGRAMADA"
    version = LimitVersion(id_limite=limit_id, id_usuario_alta=actor.id, estado=limit_state, **payload.model_dump())
    db.add(version)
    db.flush()
    write_audit(db, user_id=actor.id, table="limite_version", record_id=str(version.id), action="ALTA", after=audit_payload(version), reason=payload.motivo_cambio)
    db.commit()
    db.refresh(version)
    return version


@router.patch("/limites/{limit_id}/versiones/{version_id}", response_model=LimitVersionOutput)
def update_future_limit_version(limit_id: str, version_id: UUID, payload: LimitVersionInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    version = db.get(LimitVersion, version_id)
    if version is None or version.id_limite != limit_id:
        raise HTTPException(status_code=404, detail="Version inexistente")
    if version.vigente_desde <= date.today() or version.estado != "PROGRAMADA":
        raise HTTPException(status_code=422, detail="Solo se pueden editar versiones futuras programadas")
    assert_no_overlap(db, limit_id, payload.vigente_desde, payload.vigente_hasta_exclusiva, excluding=version.id)
    before = audit_payload(version)
    for field, value in payload.model_dump().items():
        setattr(version, field, value)
    write_audit(db, user_id=actor.id, table="limite_version", record_id=str(version.id), action="MODIFICACION", before=before, after=audit_payload(version), reason=payload.motivo_cambio)
    db.commit()
    db.refresh(version)
    return version


@router.post("/limites/{limit_id}/versiones/{version_id}/cancelar", response_model=LimitVersionOutput)
def cancel_future_limit_version(limit_id: str, version_id: UUID, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    version = db.get(LimitVersion, version_id)
    if version is None or version.id_limite != limit_id:
        raise HTTPException(status_code=404, detail="Version inexistente")
    if version.vigente_desde <= date.today() or version.estado != "PROGRAMADA":
        raise HTTPException(status_code=422, detail="Solo se pueden cancelar versiones futuras programadas")
    before = audit_payload(version)
    version.estado = "CANCELADA"
    version.cancelada_en = datetime.now(timezone.utc)
    write_audit(db, user_id=actor.id, table="limite_version", record_id=str(version.id), action="CANCELACION", before=before, after=audit_payload(version), reason="Cancelacion de version futura")
    db.commit()
    db.refresh(version)
    return version


@router.post("/parametros", status_code=201)
def create_parameter(payload: ParameterInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    for existing in db.scalars(select(SystemParameterVersion).where(SystemParameterVersion.clave == payload.clave)):
        if (payload.vigente_hasta_exclusiva is None or existing.vigente_desde < payload.vigente_hasta_exclusiva) and (existing.vigente_hasta_exclusiva is None or payload.vigente_desde < existing.vigente_hasta_exclusiva):
            raise HTTPException(status_code=422, detail="La version del parametro se solapa con una version existente")
    row = SystemParameterVersion(**payload.model_dump(), id_usuario=actor.id)
    db.add(row)
    db.flush()
    write_audit(db, user_id=actor.id, table="parametro_sistema_version", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason=payload.motivo)
    db.commit()
    return {"id": str(row.id)}


@router.post("/calendario", response_model=CalendarOutput, status_code=201)
def create_calendar(payload: CalendarInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = ProductionCalendar(**payload.model_dump())
    db.add(row)
    db.flush()
    write_audit(db, user_id=actor.id, table="calendario_produccion", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason=payload.motivo)
    db.commit()
    db.refresh(row)
    return row


@router.get("/calendario", response_model=list[CalendarOutput])
def list_calendar(desde: date, hasta: date, _: User = Depends(require_supervision), db: Session = Depends(get_db)):
    return list(db.scalars(select(ProductionCalendar).where(ProductionCalendar.fecha_operativa.between(desde, hasta)).order_by(ProductionCalendar.fecha_operativa, ProductionCalendar.turno_codigo)))


@router.get("/auditoria", response_model=list[AuditOutput])
def list_audit(_: User = Depends(require_supervision), db: Session = Depends(get_db)):
    return list(db.scalars(select(AuditLog).order_by(AuditLog.creado_en.desc()).limit(500)))


@router.post("/importaciones/preview", response_model=ImportPreview)
async def preview_import(file: UploadFile = File(...), actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    filename = file.filename or "archivo-sin-nombre"
    suffix = Path(filename).suffix
    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(await file.read())
        temporary_path = Path(temporary.name)
    try:
        preview = validate_excel_source(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    preview["filename"] = filename
    run = ImportRun(nombre_archivo=filename, sha256=preview["sha256"], modo="DRY_RUN", estado="VALIDO" if preview["valid"] else "INVALIDO", id_usuario=actor.id, resumen=preview)
    db.add(run)
    db.flush()
    for message in preview["errors"]:
        db.add(ImportResult(id_importacion=run.id, hoja="", fila=None, nivel="ERROR", mensaje=message))
    write_audit(db, user_id=actor.id, table="importacion_datos", record_id=str(run.id), action="DRY_RUN", after=preview)
    db.commit()
    return preview


@router.get("/sincronizacion/conflictos", response_model=list[SyncConflictOutput])
def list_sync_conflicts(_: User = Depends(require_supervision), db: Session = Depends(get_db)):
    return list(db.scalars(select(SyncConflict).order_by(SyncConflict.detectado_en.desc())))


@router.post("/sincronizacion/conflictos/{conflict_id}/resolver", response_model=SyncConflictOutput)
def resolve_sync_conflict(conflict_id: UUID, payload: SyncConflictResolution, actor: User = Depends(require_supervision), db: Session = Depends(get_db)):
    conflict = db.get(SyncConflict, conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflicto inexistente")
    if conflict.estado != "ABIERTO":
        raise HTTPException(status_code=422, detail="El conflicto ya fue resuelto")
    before = audit_payload(conflict)
    conflict.estado = "RESUELTO"
    conflict.resuelto_por = actor.id
    conflict.resolucion = payload.resolucion
    write_audit(db, user_id=actor.id, table="conflicto_sincronizacion", record_id=str(conflict.id), action="RESOLUCION", before=before, after=audit_payload(conflict), reason=payload.resolucion)
    db.commit()
    db.refresh(conflict)
    return conflict
