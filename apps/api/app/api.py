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
from app.models.core import AuditLog, Catalog, ImportResult, ImportRun, Limit, LimitVersion, OperationalRecord, Permission, Person, PersonPosition, ProductionCalendar, Role, SyncConflict, SystemParameterVersion, User
from app.schemas import (AuditOutput, CalendarInput, CalendarOutput, CatalogInput, CatalogOutput, CatalogPatch, DeferredRecordInput, ImportPreview, LimitInput, LimitOutput, LimitVersionInput, LimitVersionOutput, LoginInput, OperationalRecordOutput, ParameterInput, PermissionInput, PersonInput, PersonOutput, PersonPatch, PositionInput, RoleOutput, SyncConflictOutput, SyncConflictResolution, TokenOutput, UserInput, UserOutput, UserPatch)
from app.services.audit import write_audit
from app.services.importer import validate_excel_source
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


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "F0"}


@router.get("/exportar", response_class=HTMLResponse)
def export_blank_form(modulo: str, _: User = Depends(require_permission("M0", "ver"))) -> str:
    return printable_form(modulo)


@router.post("/registros/{modulo}", response_model=OperationalRecordOutput, status_code=201)
def create_deferred_record(modulo: str, payload: DeferredRecordInput, actor: User = Depends(require_permission("M0", "crear")), db: Session = Depends(get_db)):
    module = modulo.upper()
    if module not in {"M1", "M2", "M3", "M6", "M10"}:
        raise HTTPException(status_code=404, detail="Modulo no habilitado para carga diferida")
    if db.get(Person, payload.id_responsable) is None:
        raise HTTPException(status_code=422, detail="Responsable inexistente")
    if payload.fecha_operativa != expected_operational_date(payload.turno_codigo, payload.instante_medicion):
        raise HTTPException(status_code=422, detail="La fecha operativa no corresponde al turno y momento de medicion originales")
    existing = db.scalar(select(OperationalRecord).where(OperationalRecord.modulo == module, OperationalRecord.client_uuid == payload.client_uuid))
    if existing is not None:
        return existing
    record = OperationalRecord(
        modulo=module,
        client_uuid=payload.client_uuid,
        estado="BORRADOR",
        origen_dato="papel_digitado",
        fecha_operativa=payload.fecha_operativa,
        turno_codigo=payload.turno_codigo,
        instante_medicion=payload.instante_medicion,
        id_responsable=payload.id_responsable,
        id_usuario_digitador=actor.id,
        creado_por=actor.id,
        datos=payload.datos,
    )
    db.add(record)
    db.flush()
    write_audit(db, user_id=actor.id, table="registro_operativo", record_id=str(record.id), action="DIGITACION_PAPEL", after=audit_payload(record), reason="Carga diferida desde formulario en papel")
    db.commit()
    db.refresh(record)
    return record


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
