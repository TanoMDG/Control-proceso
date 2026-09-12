from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.core import AnalyticsRun, AuditLog, BoxVerdesPeriod, Catalog, DeviationEvent, DeviationHistory, ImportResult, ImportRun, KsiderSiloPeriod, LaboratoryAnalysis, LaboratoryAnalysisResult, LaboratoryConfigurationSieve, LaboratoryDetermination, LaboratoryDeviationEvent, LaboratoryFrequency, LaboratoryPointDetermination, LaboratorySamplePoint, LaboratorySieve, LaboratoryUnit, Limit, LimitVersion, LineProductFormatPeriod, MUA, MaintenanceCorrelation, MaintenanceEquipment, MaintenanceProduct, MaintenanceProductFormatVersion, MaintenanceRecord, MuaBoxPresence, OperationalRecord, Permission, Person, PersonPosition, PlcAcquisitionStatus, PlcReadSource, PlcReadTag, ProductionCalendar, Role, ShiftFact, ShiftReceipt, SiloLinePeriod, SyncConflict, SystemParameterVersion, TemporalMeasurementFact, User
from app.schemas import (AnalyticsRebuildOutput, AuditOutput, BoxVerdesPeriodOutput, BoxVerdesStartInput, CalendarInput, CalendarOutput, CatalogInput, CatalogOutput, CatalogPatch, DeferredRecordInput, DeviationOutput, ImportPreview, KsiderSiloPeriodOutput, KsiderSiloStartInput, LaboratoryActionInput, LaboratoryAnalysisInput, LaboratoryAnalysisOutput, LaboratoryAnalysisUpdateInput, LaboratoryDeterminationInput, LaboratoryDeterminationOutput, LaboratoryFrequencyInput, LaboratoryMasterInput, LaboratoryMasterOutput, LaboratoryPointDeterminationInput, LaboratoryPointInput, LaboratoryPointOutput, LaboratorySieveConfigurationInput, LaboratorySieveInput, LaboratorySieveOutput, LimitInput, LimitOutput, LimitVersionInput, LimitVersionOutput, LineProductFormatPeriodOutput, LineProductFormatStartInput, LoginInput, MaintenanceEquipmentInput, MaintenanceEquipmentOutput, MaintenanceEquipmentPatch, MaintenanceProductFormatVersionInput, MaintenanceProductFormatVersionOutput, MaintenanceProductInput, MaintenanceProductOutput, MaintenanceProductPatch, MaintenanceRecordInput, MaintenanceRecordOutput, MuaBoxPeriodOutput, MuaBoxStartInput, MuaCreateInput, MuaListOutput, MuaOutput, OperationalRecordOutput, ParameterInput, PermissionInput, PersonInput, PersonOutput, PersonPatch, PlcAcquisitionStatusOutput, PlcReadSourceInput, PlcReadSourceOutput, PlcReadSourcePatch, PlcReadTagInput, PlcReadTagOutput, PlcReadTagPatch, PositionInput, RecordActionInput, RecordUpdateInput, RoleOutput, ShiftReceiptInput, SiloLinePeriodOutput, SiloLineStartInput, SyncConflictOutput, SyncConflictResolution, TemporalCloseInput, TemporalPeriodOutput, TokenOutput, UserInput, UserOutput, UserPatch)
from app.services.audit import write_audit
from app.services.importer import validate_excel_source
from app.services.operations import MODULE_SECTOR, evaluate_record, normalized_data
from app.services.analytics import rebuild_analytics
from app.services.plc import acquire_test_samples
from app.services.laboratory import PENDING_CONFIGURATION, agenda as laboratory_agenda, analysis_output, store_analysis
from app.services.security import current_user, hash_password, make_token, require_admin, require_permission, verify_password

router = APIRouter(prefix="/api/v1")
MAINTENANCE_RESPONSIBLES_PENDING = "Pendiente de configuracion: no hay responsables de mantenimiento configurados."


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
        "m6": "M6 Paradas", "m7": "M7 Mantenimiento", "m8": "M8 Vaciado de tolva", "m9": "M9 Prensado", "m10": "M10 Espesores",
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


def assert_traceability_access(db: Session, actor: User, *, create_mua: bool = False, read: bool = False) -> None:
    role = get_role(db, actor).nombre
    if actor.consulta_remota or role not in {"CARGA", "SUPERVISION", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Permiso de trazabilidad insuficiente")
    if create_mua and role not in {"SUPERVISION", "ADMIN"}:
        raise HTTPException(status_code=403, detail="La creacion de MUA requiere SUPERVISION o ADMIN")
    if read and role == "CARGA":
        raise HTTPException(status_code=403, detail="La consulta de trazabilidad requiere SUPERVISION o ADMIN")


def assert_maintenance_access(db: Session, actor: User) -> None:
    role = get_role(db, actor).nombre
    if actor.consulta_remota or role not in {"CARGA", "SUPERVISION", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Permiso de mantenimiento insuficiente")
    if role == "CARGA" and actor.sector != "Mantenimiento":
        raise HTTPException(status_code=403, detail="CARGA solo opera mantenimiento")


def maintenance_responsibles(db: Session, on_date: date) -> list[Person]:
    statement = select(Person).join(PersonPosition, PersonPosition.id_persona == Person.id).where(
        Person.activo.is_(True),
        PersonPosition.puesto.ilike("mantenimiento"),
        PersonPosition.vigente_desde <= on_date,
        or_(PersonPosition.vigente_hasta.is_(None), PersonPosition.vigente_hasta > on_date),
    ).order_by(Person.apellido_nombre)
    return list(db.scalars(statement).unique())


def maintenance_record_output(db: Session, record: MaintenanceRecord) -> dict:
    correlations = list(db.scalars(select(MaintenanceCorrelation).where(MaintenanceCorrelation.id_registro_mantenimiento == record.id)))
    payload = audit_payload(record)
    payload["campos_madirex"] = record.campos_madirex
    return {**payload, "correlaciones": [{"tipo_referencia": row.tipo_referencia, "id_referencia": str(row.id_referencia)} for row in correlations]}


def trace_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="Los periodos deben incluir zona horaria")
    return value


def close_period(period, until: datetime, actor: User) -> None:
    until = trace_time(until)
    if period.hasta is not None:
        raise HTTPException(status_code=422, detail="El periodo ya esta cerrado")
    if until <= period.desde:
        raise HTTPException(status_code=422, detail="El fin debe ser posterior al inicio del periodo")
    period.hasta, period.id_usuario_fin = until, actor.id


def overlaps(start: datetime, end: datetime | None, other_start: datetime, other_end: datetime | None) -> bool:
    return (end is None or other_start < end) and (other_end is None or start < other_end)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "F7"}


def assert_laboratory_access(db: Session, actor: User, *, write: bool = False) -> None:
    role = get_role(db, actor).nombre
    if actor.consulta_remota or role not in {"CARGA", "SUPERVISION", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Permiso de laboratorio insuficiente")
    if role == "CARGA" and actor.sector != "Laboratorio":
        raise HTTPException(status_code=403, detail="CARGA solo opera Laboratorio")


def lab_configuration_output(db: Session, on_date: date) -> dict:
    configurations = []
    statement = select(LaboratoryPointDetermination).where(LaboratoryPointDetermination.activo.is_(True), LaboratoryPointDetermination.vigente_desde <= on_date, or_(LaboratoryPointDetermination.vigente_hasta_exclusiva.is_(None), LaboratoryPointDetermination.vigente_hasta_exclusiva > on_date))
    for row in db.scalars(statement):
        point, determination, unit = db.get(LaboratorySamplePoint, row.id_punto), db.get(LaboratoryDetermination, row.id_determinacion), db.get(LaboratoryUnit, row.id_unidad)
        frequencies = list(db.scalars(select(LaboratoryFrequency).where(LaboratoryFrequency.id_configuracion == row.id, LaboratoryFrequency.activo.is_(True), LaboratoryFrequency.vigente_desde <= datetime.combine(on_date, datetime.max.time(), tzinfo=timezone.utc), or_(LaboratoryFrequency.vigente_hasta_exclusiva.is_(None), LaboratoryFrequency.vigente_hasta_exclusiva > datetime.combine(on_date, datetime.min.time(), tzinfo=timezone.utc)))))
        sieves = list(db.scalars(select(LaboratorySieve).join(LaboratoryConfigurationSieve, LaboratoryConfigurationSieve.id_tamiz == LaboratorySieve.id).where(LaboratoryConfigurationSieve.id_configuracion == row.id, LaboratorySieve.activo.is_(True))))
        configurations.append({"id": str(row.id), "punto": {"id": str(point.id), "codigo": point.codigo, "descripcion": point.descripcion}, "determinacion": {"id": str(determination.id), "codigo": determination.codigo, "descripcion": determination.descripcion, "tipo_resultado": determination.tipo_resultado}, "unidad": {"id": str(unit.id), "codigo": unit.codigo}, "id_limite": row.id_limite, "frecuencias": [{"id": str(item.id), "intervalo_horas": item.intervalo_horas, "vigente_desde": item.vigente_desde, "vigente_hasta_exclusiva": item.vigente_hasta_exclusiva} for item in frequencies], "tamices": [{"id": str(item.id), "codigo": item.codigo, "torre": item.torre, "descripcion": item.descripcion} for item in sieves]})
    ready = [row for row in configurations if row["frecuencias"] and (row["determinacion"]["tipo_resultado"] != "GRANULOMETRIA" or row["tamices"])]
    return {"configuraciones": configurations, "mensaje_configuracion": None if ready else PENDING_CONFIGURATION}


@router.get("/laboratorio/configuracion")
def get_laboratory_configuration(fecha: date = Query(default_factory=date.today), actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    return lab_configuration_output(db, fecha)


@router.get("/laboratorio/unidades", response_model=list[LaboratoryMasterOutput])
def list_laboratory_units(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    return list(db.scalars(select(LaboratoryUnit).where(LaboratoryUnit.activo.is_(True)).order_by(LaboratoryUnit.codigo)))


@router.post("/laboratorio/unidades", response_model=LaboratoryMasterOutput, status_code=201)
def create_laboratory_unit(payload: LaboratoryMasterInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = LaboratoryUnit(**payload.model_dump())
    db.add(item); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_unidad", record_id=str(item.id), action="ALTA", after=audit_payload(item), reason="Configuracion F7")
    db.commit(); db.refresh(item); return item


@router.get("/laboratorio/puntos-muestreo", response_model=list[LaboratoryPointOutput])
def list_laboratory_points(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    return list(db.scalars(select(LaboratorySamplePoint).where(LaboratorySamplePoint.activo.is_(True)).order_by(LaboratorySamplePoint.codigo)))


@router.post("/laboratorio/puntos-muestreo", response_model=LaboratoryPointOutput, status_code=201)
def create_laboratory_point(payload: LaboratoryPointInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = LaboratorySamplePoint(**payload.model_dump())
    db.add(item); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_punto_muestreo", record_id=str(item.id), action="ALTA", after=audit_payload(item), reason="Configuracion F7")
    db.commit(); db.refresh(item); return item


@router.get("/laboratorio/determinaciones", response_model=list[LaboratoryDeterminationOutput])
def list_laboratory_determinations(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    return list(db.scalars(select(LaboratoryDetermination).where(LaboratoryDetermination.activo.is_(True)).order_by(LaboratoryDetermination.codigo)))


@router.post("/laboratorio/determinaciones", response_model=LaboratoryDeterminationOutput, status_code=201)
def create_laboratory_determination(payload: LaboratoryDeterminationInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = LaboratoryDetermination(**payload.model_dump())
    db.add(item); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_determinacion", record_id=str(item.id), action="ALTA", after=audit_payload(item), reason="Configuracion F7")
    db.commit(); db.refresh(item); return item


@router.get("/laboratorio/tamices", response_model=list[LaboratorySieveOutput])
def list_laboratory_sieves(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    return list(db.scalars(select(LaboratorySieve).where(LaboratorySieve.activo.is_(True)).order_by(LaboratorySieve.torre, LaboratorySieve.codigo)))


@router.post("/laboratorio/tamices", response_model=LaboratorySieveOutput, status_code=201)
def create_laboratory_sieve(payload: LaboratorySieveInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = LaboratorySieve(**payload.model_dump())
    db.add(item); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_tamiz", record_id=str(item.id), action="ALTA", after=audit_payload(item), reason="Configuracion F7")
    db.commit(); db.refresh(item); return item


@router.post("/laboratorio/configuraciones", status_code=201)
def create_laboratory_configuration(payload: LaboratoryPointDeterminationInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not all((db.get(LaboratorySamplePoint, payload.id_punto), db.get(LaboratoryDetermination, payload.id_determinacion), db.get(LaboratoryUnit, payload.id_unidad))) or payload.id_limite and db.get(Limit, payload.id_limite) is None:
        raise HTTPException(status_code=422, detail="El punto, determinacion, unidad o limite configurado no existe")
    for row in db.scalars(select(LaboratoryPointDetermination).where(LaboratoryPointDetermination.id_punto == payload.id_punto, LaboratoryPointDetermination.id_determinacion == payload.id_determinacion, LaboratoryPointDetermination.activo.is_(True))):
        if (payload.vigente_hasta_exclusiva is None or row.vigente_desde < payload.vigente_hasta_exclusiva) and (row.vigente_hasta_exclusiva is None or payload.vigente_desde < row.vigente_hasta_exclusiva):
            raise HTTPException(status_code=422, detail="La configuracion punto-determinacion se solapa con una version existente")
    row = LaboratoryPointDetermination(**payload.model_dump())
    db.add(row); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_punto_determinacion", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Configuracion F7 versionada")
    db.commit(); return {"id": str(row.id)}


@router.post("/laboratorio/frecuencias", status_code=201)
def create_laboratory_frequency(payload: LaboratoryFrequencyInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.vigente_desde.tzinfo is None or payload.vigente_hasta_exclusiva and payload.vigente_hasta_exclusiva.tzinfo is None or db.get(LaboratoryPointDetermination, payload.id_configuracion) is None:
        raise HTTPException(status_code=422, detail="La frecuencia requiere configuracion existente y fechas con zona horaria")
    for row in db.scalars(select(LaboratoryFrequency).where(LaboratoryFrequency.id_configuracion == payload.id_configuracion, LaboratoryFrequency.activo.is_(True))):
        if (payload.vigente_hasta_exclusiva is None or row.vigente_desde < payload.vigente_hasta_exclusiva) and (row.vigente_hasta_exclusiva is None or payload.vigente_desde < row.vigente_hasta_exclusiva):
            raise HTTPException(status_code=422, detail="La frecuencia se solapa con una version existente")
    row = LaboratoryFrequency(**payload.model_dump())
    db.add(row); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_frecuencia_control", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Frecuencia F7 configurada")
    db.commit(); return {"id": str(row.id)}


@router.post("/laboratorio/configuraciones/{configuration_id}/tamices", status_code=201)
def configure_laboratory_sieve(configuration_id: UUID, payload: LaboratorySieveConfigurationInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    configuration, sieve = db.get(LaboratoryPointDetermination, configuration_id), db.get(LaboratorySieve, payload.id_tamiz)
    if configuration is None or sieve is None or db.get(LaboratoryDetermination, configuration.id_determinacion).tipo_resultado != "GRANULOMETRIA":
        raise HTTPException(status_code=422, detail="El tamiz requiere una configuracion granulometrica y un tamiz existente")
    row = LaboratoryConfigurationSieve(id_configuracion=configuration_id, id_tamiz=payload.id_tamiz)
    db.add(row); db.flush(); write_audit(db, user_id=actor.id, table="laboratorio_configuracion_tamiz", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Torre de tamices F7")
    db.commit(); return {"id": str(row.id)}


@router.post("/laboratorio/analisis", response_model=LaboratoryAnalysisOutput, status_code=201)
def create_laboratory_analysis(payload: LaboratoryAnalysisInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor, write=True)
    existing = db.scalar(select(LaboratoryAnalysis).where(LaboratoryAnalysis.client_uuid == payload.client_uuid))
    if existing is not None:
        return analysis_output(db, existing)
    analysis = LaboratoryAnalysis(client_uuid=payload.client_uuid, id_punto=payload.id_punto, fecha_operativa=payload.fecha_operativa, turno_codigo=payload.turno_codigo, instante_muestreo=payload.instante_muestreo, creado_por=actor.id)
    db.add(analysis); db.flush(); store_analysis(db, analysis, payload)
    write_audit(db, user_id=actor.id, table="analisis_laboratorio", record_id=str(analysis.id), action="ALTA", after=audit_payload(analysis), reason="P21 analisis configurado")
    db.commit(); return analysis_output(db, analysis)


@router.get("/laboratorio/analisis", response_model=list[LaboratoryAnalysisOutput])
def list_laboratory_analyses(desde: date | None = None, hasta: date | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    role = get_role(db, actor).nombre
    statement = select(LaboratoryAnalysis)
    if role == "CARGA":
        lower = date.today() - timedelta(days=6)
        if desde and desde < lower:
            raise HTTPException(status_code=403, detail="CARGA solo consulta los ultimos siete dias")
        statement = statement.where(LaboratoryAnalysis.fecha_operativa >= lower)
    if desde: statement = statement.where(LaboratoryAnalysis.fecha_operativa >= desde)
    if hasta: statement = statement.where(LaboratoryAnalysis.fecha_operativa <= hasta)
    return [analysis_output(db, row) for row in db.scalars(statement.order_by(LaboratoryAnalysis.instante_muestreo.desc()))]


@router.put("/laboratorio/analisis/{analysis_id}", response_model=LaboratoryAnalysisOutput)
def update_laboratory_analysis(analysis_id: UUID, payload: LaboratoryAnalysisUpdateInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor, write=True)
    analysis = db.get(LaboratoryAnalysis, analysis_id)
    if analysis is None: raise HTTPException(status_code=404, detail="Analisis inexistente")
    role = get_role(db, actor).nombre
    if analysis.revision != payload.revision: raise HTTPException(status_code=409, detail="Revision desactualizada")
    if role == "CARGA" and (analysis.estado != "BORRADOR" or analysis.creado_por != actor.id): raise HTTPException(status_code=403, detail="CARGA solo edita sus borradores de laboratorio")
    if analysis.estado != "BORRADOR" and (role not in {"SUPERVISION", "ADMIN"} or not payload.motivo_correccion): raise HTTPException(status_code=422, detail="La correccion requiere SUPERVISION/ADMIN y motivo")
    before = audit_payload(analysis); store_analysis(db, analysis, payload); analysis.revision += 1; analysis.motivo_correccion = payload.motivo_correccion
    write_audit(db, user_id=actor.id, table="analisis_laboratorio", record_id=str(analysis.id), action="CORRECCION", before=before, after=audit_payload(analysis), reason=payload.motivo_correccion)
    db.commit(); return analysis_output(db, analysis)


@router.post("/laboratorio/analisis/{analysis_id}/cerrar", response_model=LaboratoryAnalysisOutput)
def close_laboratory_analysis(analysis_id: UUID, payload: LaboratoryActionInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor, write=True)
    analysis = db.get(LaboratoryAnalysis, analysis_id)
    if analysis is None or analysis.estado != "BORRADOR": raise HTTPException(status_code=422, detail="Solo se cierran analisis borrador")
    if get_role(db, actor).nombre == "CARGA" and analysis.creado_por != actor.id: raise HTTPException(status_code=403, detail="CARGA solo cierra sus analisis")
    analysis.estado = "CERRADO"; write_audit(db, user_id=actor.id, table="analisis_laboratorio", record_id=str(analysis.id), action="CIERRE", after=audit_payload(analysis), reason=payload.comentario)
    db.commit(); return analysis_output(db, analysis)


@router.get("/laboratorio/agenda")
def get_laboratory_agenda(desde: datetime, hasta: datetime, id_punto: UUID | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    return laboratory_agenda(db, desde, hasta, id_punto)


@router.get("/laboratorio/desvios")
def list_laboratory_deviations(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor)
    statement = select(LaboratoryDeviationEvent)
    if get_role(db, actor).nombre == "CARGA":
        statement = statement.join(LaboratoryAnalysisResult, LaboratoryAnalysisResult.id == LaboratoryDeviationEvent.id_resultado).join(LaboratoryAnalysis, LaboratoryAnalysis.id == LaboratoryAnalysisResult.id_analisis).where(LaboratoryAnalysis.fecha_operativa >= date.today() - timedelta(days=6))
    return list(db.scalars(statement.order_by(LaboratoryDeviationEvent.created_at.desc())))


@router.post("/laboratorio/desvios/{event_id}/{action}")
def transition_laboratory_deviation(event_id: UUID, action: str, payload: LaboratoryActionInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_laboratory_access(db, actor, write=True)
    event = db.get(LaboratoryDeviationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Desvio de laboratorio inexistente")
    target = {"tratar": "EN_TRATAMIENTO", "verificar": "VERIFICADO", "cerrar": "CERRADO"}.get(action)
    if target is None:
        raise HTTPException(status_code=404, detail="Accion de desvio inexistente")
    role, previous = get_role(db, actor).nombre, event.estado
    if action == "tratar" and previous not in {"ABIERTO", "ESCALADO", "VENCIDO"}:
        raise HTTPException(status_code=422, detail="Transicion de desvio invalida")
    if action == "verificar" and previous != "EN_TRATAMIENTO":
        raise HTTPException(status_code=422, detail="El desvio debe tratarse antes de verificar")
    if action == "cerrar" and (role not in {"SUPERVISION", "ADMIN"} or previous != "VERIFICADO"):
        raise HTTPException(status_code=422, detail="El cierre requiere SUPERVISION/ADMIN y verificacion")
    event.estado = target
    write_audit(db, user_id=actor.id, table="evento_desvio_laboratorio", record_id=str(event.id), action=action.upper(), before={"estado": previous}, after=audit_payload(event), reason=payload.comentario)
    db.commit(); db.refresh(event)
    return {"id": str(event.id), "estado": event.estado}


def assert_plc_tag_values(tag: PlcReadTag) -> None:
    if tag.escala_factor == 0:
        raise HTTPException(status_code=422, detail="escala_factor no puede ser cero")


def plc_status_output(db: Session, source: PlcReadSource) -> dict:
    status_row = db.get(PlcAcquisitionStatus, source.id)
    active_tags = db.scalar(select(func.count()).select_from(PlcReadTag).where(PlcReadTag.id_fuente == source.id, PlcReadTag.activo.is_(True))) or 0
    return {
        "id_fuente": source.id,
        "fuente": source.nombre,
        "adaptador": source.adaptador,
        "fuente_activa": source.activo,
        "tags_activos": active_tags,
        "estado": status_row.estado if status_row else "SIN_MUESTRAS",
        "ultimo_intento_en": status_row.ultimo_intento_en if status_row else None,
        "ultima_muestra_en": status_row.ultima_muestra_en if status_row else None,
        "ultimo_error": status_row.ultimo_error if status_row else None,
    }


@router.get("/plc/configuracion", response_model=list[PlcReadSourceOutput])
def list_plc_sources(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(PlcReadSource).order_by(PlcReadSource.nombre)))


@router.post("/plc/configuracion", response_model=PlcReadSourceOutput, status_code=201)
def create_plc_source(payload: PlcReadSourceInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    source = PlcReadSource(**payload.model_dump())
    db.add(source)
    db.flush()
    db.add(PlcAcquisitionStatus(id_fuente=source.id, estado="CONFIGURADO"))
    write_audit(db, user_id=actor.id, table="plc_lectura_fuente", record_id=str(source.id), action="ALTA", after=audit_payload(source), reason="Configuracion F6: solo adaptador TEST_SIMULATOR")
    db.commit()
    db.refresh(source)
    return source


@router.patch("/plc/configuracion/{source_id}", response_model=PlcReadSourceOutput)
def update_plc_source(source_id: UUID, payload: PlcReadSourcePatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    source = db.get(PlcReadSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Fuente PLC inexistente")
    before = audit_payload(source)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    write_audit(db, user_id=actor.id, table="plc_lectura_fuente", record_id=str(source.id), action="MODIFICACION", before=before, after=audit_payload(source), reason="Configuracion F6 de solo lectura")
    db.commit()
    db.refresh(source)
    return source


@router.get("/plc/configuracion/{source_id}/tags", response_model=list[PlcReadTagOutput])
def list_plc_tags(source_id: UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(PlcReadSource, source_id) is None:
        raise HTTPException(status_code=404, detail="Fuente PLC inexistente")
    return list(db.scalars(select(PlcReadTag).where(PlcReadTag.id_fuente == source_id).order_by(PlcReadTag.metrica)))


@router.post("/plc/configuracion/{source_id}/tags", response_model=PlcReadTagOutput, status_code=201)
def create_plc_tag(source_id: UUID, payload: PlcReadTagInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(PlcReadSource, source_id) is None:
        raise HTTPException(status_code=404, detail="Fuente PLC inexistente")
    tag = PlcReadTag(id_fuente=source_id, **payload.model_dump())
    assert_plc_tag_values(tag)
    db.add(tag)
    db.flush()
    write_audit(db, user_id=actor.id, table="plc_lectura_tag", record_id=str(tag.id), action="ALTA", after=audit_payload(tag), reason="Tag F6 de solo lectura")
    db.commit()
    db.refresh(tag)
    return tag


@router.patch("/plc/configuracion/{source_id}/tags/{tag_id}", response_model=PlcReadTagOutput)
def update_plc_tag(source_id: UUID, tag_id: UUID, payload: PlcReadTagPatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    tag = db.get(PlcReadTag, tag_id)
    if tag is None or tag.id_fuente != source_id:
        raise HTTPException(status_code=404, detail="Tag PLC inexistente")
    before = audit_payload(tag)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    assert_plc_tag_values(tag)
    write_audit(db, user_id=actor.id, table="plc_lectura_tag", record_id=str(tag.id), action="MODIFICACION", before=before, after=audit_payload(tag), reason="Cambio de tag, escala, muestreo, agregacion o retencion")
    db.commit()
    db.refresh(tag)
    return tag


@router.post("/plc/configuracion/{source_id}/simular-lectura")
def sample_plc_test_source(source_id: UUID, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    source = db.get(PlcReadSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Fuente PLC inexistente")
    if not source.activo:
        raise HTTPException(status_code=422, detail="La fuente PLC esta inactiva")
    try:
        samples = acquire_test_samples(db, source)
    except ValueError as error:
        status_row = db.get(PlcAcquisitionStatus, source.id)
        if status_row is not None:
            status_row.estado, status_row.ultimo_error = "ERROR", str(error)
        db.commit()
        raise HTTPException(status_code=422, detail=str(error)) from error
    write_audit(db, user_id=actor.id, table="plc_estado_adquisicion", record_id=str(source.id), action="MUESTRA_TEST", after={"muestras_guardadas": samples, "adaptador": source.adaptador}, reason="Ejecucion manual del simulador F6; no se realizo conexion a PLC")
    db.commit()
    return {"muestras_guardadas": samples, "adaptador": source.adaptador}


@router.get("/plc/estado", response_model=list[PlcAcquisitionStatusOutput])
def get_plc_acquisition_status(_: User = Depends(require_supervision), db: Session = Depends(get_db)):
    return [plc_status_output(db, source) for source in db.scalars(select(PlcReadSource).order_by(PlcReadSource.nombre))]


@router.get("/exportar", response_class=HTMLResponse)
def export_blank_form(modulo: str, _: User = Depends(require_permission("M0", "ver"))) -> str:
    return printable_form(modulo)


@router.post("/registros/m7", response_model=MaintenanceRecordOutput, status_code=201)
def create_m7_record_alias(payload: MaintenanceRecordInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return create_maintenance_record(payload, actor, db)


@router.get("/registros/m7", response_model=list[MaintenanceRecordOutput])
def list_m7_records_alias(desde: date | None = None, hasta: date | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_maintenance_records(desde, hasta, actor, db)


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


def assert_active_maintenance_master(item, label: str) -> None:
    if item is None or not item.activo:
        raise HTTPException(status_code=422, detail=f"{label} inexistente o inactivo")


def assert_product_format_overlap(db: Session, product_id: UUID, format_id: UUID, start: date, end: date | None) -> None:
    versions = db.scalars(select(MaintenanceProductFormatVersion).where(MaintenanceProductFormatVersion.id_producto == product_id, MaintenanceProductFormatVersion.id_formato == format_id))
    for version in versions:
        if (end is None or version.vigente_desde < end) and (version.vigente_hasta_exclusiva is None or start < version.vigente_hasta_exclusiva):
            raise HTTPException(status_code=422, detail="La version producto-formato se solapa con una relacion existente")


@router.get("/mantenimiento/responsables")
def list_maintenance_responsibles(fecha: date = Query(default_factory=date.today), actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_maintenance_access(db, actor)
    rows = maintenance_responsibles(db, fecha)
    return {"responsables": [{"id": str(row.id), "legajo": row.legajo, "apellido_nombre": row.apellido_nombre} for row in rows], "mensaje_configuracion": None if rows else MAINTENANCE_RESPONSIBLES_PENDING}


@router.get("/mantenimiento/equipos", response_model=list[MaintenanceEquipmentOutput])
def list_maintenance_equipment(incluir_inactivos: bool = False, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_maintenance_access(db, actor)
    statement = select(MaintenanceEquipment).order_by(MaintenanceEquipment.codigo)
    if not incluir_inactivos:
        statement = statement.where(MaintenanceEquipment.activo.is_(True))
    return list(db.scalars(statement))


@router.post("/mantenimiento/equipos", response_model=MaintenanceEquipmentOutput, status_code=201)
def create_maintenance_equipment(payload: MaintenanceEquipmentInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = MaintenanceEquipment(**payload.model_dump())
    db.add(item); db.flush()
    write_audit(db, user_id=actor.id, table="equipo_mantenimiento", record_id=str(item.id), action="ALTA", after=audit_payload(item))
    db.commit(); db.refresh(item); return item


@router.patch("/mantenimiento/equipos/{equipment_id}", response_model=MaintenanceEquipmentOutput)
def update_maintenance_equipment(equipment_id: UUID, payload: MaintenanceEquipmentPatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(MaintenanceEquipment, equipment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Equipo inexistente")
    before, changes = audit_payload(item), payload.model_dump(exclude_unset=True)
    if changes.get("activo") is False and not changes.get("fecha_baja"):
        raise HTTPException(status_code=422, detail="fecha_baja es obligatoria al desactivar")
    if changes.get("activo") is True:
        changes["fecha_baja"] = None
    for field, value in changes.items():
        setattr(item, field, value)
    write_audit(db, user_id=actor.id, table="equipo_mantenimiento", record_id=str(item.id), action="MODIFICACION", before=before, after=audit_payload(item), reason="Actualizacion de equipo")
    db.commit(); db.refresh(item); return item


@router.get("/mantenimiento/productos", response_model=list[MaintenanceProductOutput])
def list_maintenance_products(incluir_inactivos: bool = False, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_maintenance_access(db, actor)
    statement = select(MaintenanceProduct).order_by(MaintenanceProduct.codigo)
    if not incluir_inactivos:
        statement = statement.where(MaintenanceProduct.activo.is_(True))
    return list(db.scalars(statement))


@router.post("/mantenimiento/productos", response_model=MaintenanceProductOutput, status_code=201)
def create_maintenance_product(payload: MaintenanceProductInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = MaintenanceProduct(**payload.model_dump())
    db.add(item); db.flush()
    write_audit(db, user_id=actor.id, table="producto_mantenimiento", record_id=str(item.id), action="ALTA", after=audit_payload(item))
    db.commit(); db.refresh(item); return item


@router.patch("/mantenimiento/productos/{product_id}", response_model=MaintenanceProductOutput)
def update_maintenance_product(product_id: UUID, payload: MaintenanceProductPatch, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(MaintenanceProduct, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Producto inexistente")
    before, changes = audit_payload(item), payload.model_dump(exclude_unset=True)
    if changes.get("activo") is False and not changes.get("fecha_baja"):
        raise HTTPException(status_code=422, detail="fecha_baja es obligatoria al desactivar")
    if changes.get("activo") is True:
        changes["fecha_baja"] = None
    for field, value in changes.items():
        setattr(item, field, value)
    write_audit(db, user_id=actor.id, table="producto_mantenimiento", record_id=str(item.id), action="MODIFICACION", before=before, after=audit_payload(item), reason="Actualizacion de producto")
    db.commit(); db.refresh(item); return item


@router.get("/mantenimiento/productos/{product_id}/formatos", response_model=list[MaintenanceProductFormatVersionOutput])
def list_maintenance_product_formats(product_id: UUID, fecha: date = Query(default_factory=date.today), incluir_historicos: bool = False, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_maintenance_access(db, actor)
    if db.get(MaintenanceProduct, product_id) is None:
        raise HTTPException(status_code=404, detail="Producto inexistente")
    statement = select(MaintenanceProductFormatVersion).where(MaintenanceProductFormatVersion.id_producto == product_id)
    if not incluir_historicos:
        statement = statement.where(MaintenanceProductFormatVersion.vigente_desde <= fecha, or_(MaintenanceProductFormatVersion.vigente_hasta_exclusiva.is_(None), MaintenanceProductFormatVersion.vigente_hasta_exclusiva > fecha))
    return list(db.scalars(statement.order_by(MaintenanceProductFormatVersion.vigente_desde)))


@router.post("/mantenimiento/productos/{product_id}/formatos", response_model=MaintenanceProductFormatVersionOutput, status_code=201)
def create_maintenance_product_format(product_id: UUID, payload: MaintenanceProductFormatVersionInput, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    product, format_item = db.get(MaintenanceProduct, product_id), db.get(Catalog, payload.id_formato)
    assert_active_maintenance_master(product, "Producto")
    if format_item is None or not format_item.activo or format_item.tipo != "formato":
        raise HTTPException(status_code=422, detail="Formato inexistente o inactivo")
    assert_product_format_overlap(db, product_id, payload.id_formato, payload.vigente_desde, payload.vigente_hasta_exclusiva)
    version = MaintenanceProductFormatVersion(id_producto=product_id, id_formato=payload.id_formato, id_usuario_alta=actor.id, **payload.model_dump(exclude={"id_formato"}))
    db.add(version); db.flush()
    write_audit(db, user_id=actor.id, table="producto_formato_mantenimiento_version", record_id=str(version.id), action="ALTA", after=audit_payload(version), reason=payload.motivo_cambio)
    db.commit(); db.refresh(version); return version


def resolve_maintenance_product_format(db: Session, payload: MaintenanceRecordInput) -> MaintenanceProductFormatVersion | None:
    if payload.id_producto_formato_version:
        version = db.get(MaintenanceProductFormatVersion, payload.id_producto_formato_version)
        if version is None or not (version.vigente_desde <= payload.fecha_operativa and (version.vigente_hasta_exclusiva is None or payload.fecha_operativa < version.vigente_hasta_exclusiva)):
            raise HTTPException(status_code=422, detail="La relacion producto-formato no esta vigente para la fecha operativa")
        if payload.id_producto and version.id_producto != payload.id_producto or payload.id_formato and version.id_formato != payload.id_formato:
            raise HTTPException(status_code=422, detail="La relacion producto-formato no coincide con la seleccion")
        return version
    if payload.id_producto is None and payload.id_formato is None:
        return None
    if payload.id_producto is None or payload.id_formato is None:
        raise HTTPException(status_code=422, detail="Producto y formato deben seleccionarse juntos")
    version = db.scalar(select(MaintenanceProductFormatVersion).where(MaintenanceProductFormatVersion.id_producto == payload.id_producto, MaintenanceProductFormatVersion.id_formato == payload.id_formato, MaintenanceProductFormatVersion.vigente_desde <= payload.fecha_operativa, or_(MaintenanceProductFormatVersion.vigente_hasta_exclusiva.is_(None), MaintenanceProductFormatVersion.vigente_hasta_exclusiva > payload.fecha_operativa)))
    if version is None:
        raise HTTPException(status_code=422, detail="No hay relacion producto-formato vigente para la fecha operativa")
    return version


@router.post("/mantenimiento/registros", response_model=MaintenanceRecordOutput, status_code=201)
def create_maintenance_record(payload: MaintenanceRecordInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_maintenance_access(db, actor)
    if payload.inicio.tzinfo is None or payload.fin and payload.fin.tzinfo is None or payload.fin and payload.fin < payload.inicio:
        raise HTTPException(status_code=422, detail="El intervalo de mantenimiento debe incluir zona horaria y ser valido")
    existing = db.scalar(select(MaintenanceRecord).where(MaintenanceRecord.client_uuid == payload.client_uuid))
    if existing is not None:
        return maintenance_record_output(db, existing)
    equipment = db.get(MaintenanceEquipment, payload.id_equipo)
    assert_active_maintenance_master(equipment, "Equipo")
    responsible_ids = {person.id for person in maintenance_responsibles(db, payload.fecha_operativa)}
    if not responsible_ids:
        raise HTTPException(status_code=422, detail=MAINTENANCE_RESPONSIBLES_PENDING)
    if payload.id_responsable not in responsible_ids:
        raise HTTPException(status_code=422, detail="El responsable debe tener un puesto de mantenimiento vigente")
    product_format = resolve_maintenance_product_format(db, payload)
    record = MaintenanceRecord(client_uuid=payload.client_uuid, fecha_operativa=payload.fecha_operativa, turno_codigo=payload.turno_codigo, inicio=payload.inicio, fin=payload.fin, id_equipo=equipment.id, id_producto_formato_version=product_format.id if product_format else None, id_responsable=payload.id_responsable, tipo=payload.tipo.strip(), descripcion=payload.descripcion.strip(), campos_madirex=payload.campos_madirex, creado_por=actor.id)
    db.add(record); db.flush()
    for stop_id in set(payload.ids_paradas):
        stop = db.get(OperationalRecord, stop_id)
        if stop is None or stop.modulo != "M6" or stop.estado == "ANULADO":
            raise HTTPException(status_code=422, detail="La parada correlacionada debe ser un M6 existente y no anulado")
        db.add(MaintenanceCorrelation(id_registro_mantenimiento=record.id, tipo_referencia="PARADA", id_referencia=stop_id))
    for deviation_id in set(payload.ids_desvios):
        if db.get(DeviationEvent, deviation_id) is None:
            raise HTTPException(status_code=422, detail="El desvio correlacionado debe existir")
        db.add(MaintenanceCorrelation(id_registro_mantenimiento=record.id, tipo_referencia="DESVIO", id_referencia=deviation_id))
    write_audit(db, user_id=actor.id, table="registro_mantenimiento", record_id=str(record.id), action="ALTA", after=audit_payload(record), reason="Campos Madirex informativos; sin limite ni desvio automatico")
    db.commit(); db.refresh(record); return maintenance_record_output(db, record)


@router.get("/mantenimiento/registros", response_model=list[MaintenanceRecordOutput])
def list_maintenance_records(desde: date | None = None, hasta: date | None = None, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_maintenance_access(db, actor)
    statement = select(MaintenanceRecord)
    if desde:
        statement = statement.where(MaintenanceRecord.fecha_operativa >= desde)
    if hasta:
        statement = statement.where(MaintenanceRecord.fecha_operativa <= hasta)
    return [maintenance_record_output(db, row) for row in db.scalars(statement.order_by(MaintenanceRecord.inicio.desc()))]


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


@router.post("/mua", response_model=MuaOutput, status_code=201)
def create_mua(payload: MuaCreateInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor, create_mua=True)
    preparer = db.get(Person, payload.id_preparador)
    if preparer is None:
        raise HTTPException(status_code=422, detail="Preparador inexistente")
    prefix = f"MUA-{payload.fecha_generacion:%Y-%m%d}-"
    sequence = sum(1 for code in db.scalars(select(MUA.codigo).where(MUA.codigo.like(f"{prefix}%")))) + 1
    mua = MUA(codigo=f"{prefix}{sequence:02d}", fecha_generacion=payload.fecha_generacion, id_preparador=payload.id_preparador, composicion=[component.model_dump(exclude_none=True) for component in payload.composicion], creado_por=actor.id)
    db.add(mua)
    db.flush()
    write_audit(db, user_id=actor.id, table="mua", record_id=str(mua.id), action="ALTA", after=audit_payload(mua), reason="Registro M4 de identidad y composicion")
    db.commit()
    db.refresh(mua)
    return mua


@router.get("/mua", response_model=list[MuaListOutput])
def list_mua(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    rows = list(db.scalars(select(MUA).order_by(MUA.fecha_generacion, MUA.codigo)))
    active = list(db.scalars(select(MuaBoxPresence).where(MuaBoxPresence.hasta.is_(None))))
    fifo_by_box: dict[str, list[MuaBoxPresence]] = {}
    for presence in active:
        fifo_by_box.setdefault(presence.box, []).append(presence)
    for presences in fifo_by_box.values():
        presences.sort(key=lambda row: db.get(MUA, row.id_mua).fecha_generacion)
    return [{"id": mua.id, "codigo": mua.codigo, "fecha_generacion": mua.fecha_generacion, "id_preparador": mua.id_preparador, "composicion": mua.composicion, "creado_por": mua.creado_por, "presencias_activas": [{"id": presence.id, "id_mua": presence.id_mua, "box": presence.box, "desde": presence.desde, "hasta": presence.hasta, "certeza": presence.certeza, "id_usuario_inicio": presence.id_usuario_inicio, "id_usuario_fin": presence.id_usuario_fin} for presence in active if presence.id_mua == mua.id], "orden_fifo": min((box_rows.index(presence) + 1 for box_rows in fifo_by_box.values() for presence in box_rows if presence.id_mua == mua.id), default=None)} for mua in rows]


@router.post("/trazabilidad/mua-box", response_model=MuaBoxPeriodOutput, status_code=201)
def start_mua_box(payload: MuaBoxStartInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    if db.get(MUA, payload.id_mua) is None:
        raise HTTPException(status_code=422, detail="La MUA debe existir antes de cargarla en un box")
    row = MuaBoxPresence(id_mua=payload.id_mua, box=payload.box.strip(), desde=trace_time(payload.desde), certeza=payload.certeza, id_usuario_inicio=actor.id)
    db.add(row)
    db.flush()
    write_audit(db, user_id=actor.id, table="mua_box_presencia", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Carga M5 de MUA en box")
    db.commit(); db.refresh(row)
    return row


@router.patch("/trazabilidad/mua-box/{period_id}", response_model=MuaBoxPeriodOutput)
def finish_mua_box(period_id: UUID, payload: TemporalCloseInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    row = db.get(MuaBoxPresence, period_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Periodo MUA-box inexistente")
    before = audit_payload(row); close_period(row, payload.hasta, actor)
    write_audit(db, user_id=actor.id, table="mua_box_presencia", record_id=str(row.id), action="CIERRE", before=before, after=audit_payload(row), reason="Fin de presencia MUA en box")
    db.commit(); db.refresh(row)
    return row


@router.post("/trazabilidad/box-verdes", response_model=BoxVerdesPeriodOutput, status_code=201)
def start_box_verdes(payload: BoxVerdesStartInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    started = trace_time(payload.desde)
    active = list(db.scalars(select(BoxVerdesPeriod).where(BoxVerdesPeriod.hasta.is_(None))))
    for previous in active:
        close_period(previous, started, actor)
        write_audit(db, user_id=actor.id, table="box_verdes_periodo", record_id=str(previous.id), action="CIERRE", after=audit_payload(previous), reason="Nuevo box activo hacia Verdes")
    row = BoxVerdesPeriod(box=payload.box.strip(), desde=started, id_usuario_inicio=actor.id)
    db.add(row); db.flush()
    write_audit(db, user_id=actor.id, table="box_verdes_periodo", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Activacion de box hacia Verdes")
    db.commit(); db.refresh(row)
    return row


@router.patch("/trazabilidad/box-verdes/{period_id}", response_model=BoxVerdesPeriodOutput)
def finish_box_verdes(period_id: UUID, payload: TemporalCloseInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    row = db.get(BoxVerdesPeriod, period_id)
    if row is None: raise HTTPException(status_code=404, detail="Periodo box-Verdes inexistente")
    before = audit_payload(row); close_period(row, payload.hasta, actor)
    write_audit(db, user_id=actor.id, table="box_verdes_periodo", record_id=str(row.id), action="CIERRE", before=before, after=audit_payload(row), reason="Fin de box hacia Verdes")
    db.commit(); db.refresh(row); return row


@router.post("/trazabilidad/ksider-silo", response_model=KsiderSiloPeriodOutput, status_code=201)
def start_ksider_silo(payload: KsiderSiloStartInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    started, receiver = trace_time(payload.desde), payload.receptor.strip().upper()
    active = list(db.scalars(select(KsiderSiloPeriod).where(KsiderSiloPeriod.receptor == receiver, KsiderSiloPeriod.hasta.is_(None))))
    for previous in active:
        close_period(previous, started, actor)
        write_audit(db, user_id=actor.id, table="ksider_silo_periodo", record_id=str(previous.id), action="CIERRE", after=audit_payload(previous), reason="Cambio de receptor K-Sider")
    row = KsiderSiloPeriod(receptor=receiver, silo=payload.silo, desde=started, id_usuario_inicio=actor.id)
    db.add(row); db.flush()
    write_audit(db, user_id=actor.id, table="ksider_silo_periodo", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Asignacion receptor K-Sider")
    db.commit(); db.refresh(row); return row


@router.patch("/trazabilidad/ksider-silo/{period_id}", response_model=KsiderSiloPeriodOutput)
def finish_ksider_silo(period_id: UUID, payload: TemporalCloseInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    row = db.get(KsiderSiloPeriod, period_id)
    if row is None: raise HTTPException(status_code=404, detail="Periodo K-Sider-silo inexistente")
    before = audit_payload(row); close_period(row, payload.hasta, actor)
    write_audit(db, user_id=actor.id, table="ksider_silo_periodo", record_id=str(row.id), action="CIERRE", before=before, after=audit_payload(row), reason="Fin de receptor K-Sider")
    db.commit(); db.refresh(row); return row


@router.post("/trazabilidad/silo-linea", response_model=SiloLinePeriodOutput, status_code=201)
def start_silo_line(payload: SiloLineStartInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    if (payload.silo <= 8 and payload.linea != "L7") or (payload.silo >= 9 and payload.linea != "L6"):
        raise HTTPException(status_code=422, detail="El silo no pertenece fisicamente a la linea seleccionada")
    row = SiloLinePeriod(silo=payload.silo, linea=payload.linea, desde=trace_time(payload.desde), id_usuario_inicio=actor.id)
    db.add(row); db.flush()
    write_audit(db, user_id=actor.id, table="silo_linea_periodo", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Asociacion temporal silo-linea")
    db.commit(); db.refresh(row); return row


@router.patch("/trazabilidad/silo-linea/{period_id}", response_model=SiloLinePeriodOutput)
def finish_silo_line(period_id: UUID, payload: TemporalCloseInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    row = db.get(SiloLinePeriod, period_id)
    if row is None: raise HTTPException(status_code=404, detail="Periodo silo-linea inexistente")
    before = audit_payload(row); close_period(row, payload.hasta, actor)
    write_audit(db, user_id=actor.id, table="silo_linea_periodo", record_id=str(row.id), action="CIERRE", before=before, after=audit_payload(row), reason="Fin de asociacion silo-linea")
    db.commit(); db.refresh(row); return row


@router.post("/lineas/{linea}/producto-formato", response_model=LineProductFormatPeriodOutput, status_code=201)
def start_line_product_format(linea: str, payload: LineProductFormatStartInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    if linea != payload.linea:
        raise HTTPException(status_code=422, detail="La linea de la ruta y el periodo deben coincidir")
    started = trace_time(payload.desde)
    active = list(db.scalars(select(LineProductFormatPeriod).where(LineProductFormatPeriod.linea == linea, LineProductFormatPeriod.hasta.is_(None))))
    for previous in active:
        close_period(previous, started, actor)
        write_audit(db, user_id=actor.id, table="linea_producto_formato_periodo", record_id=str(previous.id), action="CIERRE", after=audit_payload(previous), reason="Cambio de producto/formato de linea")
    row = LineProductFormatPeriod(linea=linea, producto=payload.producto.strip(), formato=payload.formato.strip(), desde=started, id_usuario_inicio=actor.id)
    db.add(row); db.flush()
    write_audit(db, user_id=actor.id, table="linea_producto_formato_periodo", record_id=str(row.id), action="ALTA", after=audit_payload(row), reason="Producto/formato de linea")
    db.commit(); db.refresh(row); return row


@router.patch("/lineas/{linea}/producto-formato/{period_id}", response_model=LineProductFormatPeriodOutput)
def finish_line_product_format(linea: str, period_id: UUID, payload: TemporalCloseInput, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor)
    row = db.get(LineProductFormatPeriod, period_id)
    if row is None or row.linea != linea: raise HTTPException(status_code=404, detail="Periodo producto-formato inexistente")
    before = audit_payload(row); close_period(row, payload.hasta, actor)
    write_audit(db, user_id=actor.id, table="linea_producto_formato_periodo", record_id=str(row.id), action="CIERRE", before=before, after=audit_payload(row), reason="Fin de producto/formato de linea")
    db.commit(); db.refresh(row); return row


@router.get("/mua/{mua_id}/trazabilidad")
def mua_traceability(mua_id: UUID, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    assert_traceability_access(db, actor, read=True)
    mua = db.get(MUA, mua_id)
    if mua is None:
        raise HTTPException(status_code=404, detail="MUA inexistente")
    edges: list[dict] = []
    presences = list(db.scalars(select(MuaBoxPresence).where(MuaBoxPresence.id_mua == mua.id).order_by(MuaBoxPresence.desde)))
    for presence in presences:
        edges.append({"relacion": "MUA->BOX", "origen": mua.codigo, "destino": f"BOX-{presence.box}", "desde": presence.desde, "hasta": presence.hasta, "certeza": presence.certeza, "id_periodo": str(presence.id)})
        box_periods = [row for row in db.scalars(select(BoxVerdesPeriod).where(BoxVerdesPeriod.box == presence.box)) if overlaps(presence.desde, presence.hasta, row.desde, row.hasta)]
        for box_period in box_periods:
            edges.append({"relacion": "BOX->VERDES", "origen": f"BOX-{presence.box}", "destino": "VERDES", "desde": max(presence.desde, box_period.desde), "hasta": box_period.hasta if presence.hasta is None else presence.hasta if box_period.hasta is None else min(presence.hasta, box_period.hasta), "certeza": "POTENCIAL", "id_periodo": str(box_period.id)})
            ksider_periods = [row for row in db.scalars(select(KsiderSiloPeriod)) if overlaps(box_period.desde, box_period.hasta, row.desde, row.hasta)]
            for ksider in ksider_periods:
                edges.append({"relacion": "K-SIDER->SILO", "origen": ksider.receptor, "destino": f"SILO-{ksider.silo}", "desde": ksider.desde, "hasta": ksider.hasta, "certeza": "INFERIDA", "id_periodo": str(ksider.id)})
                line_periods = [row for row in db.scalars(select(SiloLinePeriod).where(SiloLinePeriod.silo == ksider.silo)) if overlaps(ksider.desde, ksider.hasta, row.desde, row.hasta)]
                for silo_line in line_periods:
                    edges.append({"relacion": "SILO->LINEA", "origen": f"SILO-{ksider.silo}", "destino": silo_line.linea, "desde": silo_line.desde, "hasta": silo_line.hasta, "certeza": "INFERIDA", "id_periodo": str(silo_line.id)})
                    products = [row for row in db.scalars(select(LineProductFormatPeriod).where(LineProductFormatPeriod.linea == silo_line.linea)) if overlaps(silo_line.desde, silo_line.hasta, row.desde, row.hasta)]
                    edges.extend({"relacion": "LINEA->PRODUCTO_FORMATO", "origen": silo_line.linea, "destino": f"{row.producto} / {row.formato}", "desde": row.desde, "hasta": row.hasta, "certeza": "INFERIDA", "id_periodo": str(row.id)} for row in products)
    return {"mua": {"id": str(mua.id), "codigo": mua.codigo, "fecha_generacion": mua.fecha_generacion, "id_preparador": str(mua.id_preparador), "composicion": mua.composicion}, "aristas": sorted(edges, key=lambda edge: edge["desde"]), "sin_proporciones_inventadas": True}


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
