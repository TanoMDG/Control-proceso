import ast
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import AuditLog, Permission, Person, Role, User
from app.services.security import hash_password
from tests.conftest import auth


def create_carga(client, admin_token, *, username: str, sector: str):
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": f"AUTH-{username[:14]}", "apellido_nombre": username}).json()
    role = next(item for item in client.get("/api/v1/roles", headers=headers).json() if item["nombre"] == "CARGA")
    assert client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": username, "password": "Clave-de-prueba-123", "id_rol": role["id"], "sector": sector}).status_code == 201
    return person, client.post("/api/v1/auth/login", json={"username": username, "password": "Clave-de-prueba-123"}).json()["access_token"]


def create_permission_limited_user(username: str) -> str:
    with SessionLocal.begin() as db:
        role = Role(nombre=f"LECTOR-{username}", descripcion="Rol de prueba con solo KPI")
        person = Person(legajo=f"AUTH-{username[:14]}", apellido_nombre=username, activo=True, fecha_baja=None)
        db.add_all((role, person))
        db.flush()
        db.add(Permission(id_rol=role.id, modulo="M2", accion="ver", alcance="todo"))
        db.add(User(id_persona=person.id, nombre_usuario=username, password_hash=hash_password("Clave-de-prueba-123"), id_rol=role.id, sector="Administracion"))
    return username


def test_cp23_remote_is_limited_to_exact_dashboard_endpoint(client, admin_token):
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-REMOTE-STRICT", "apellido_nombre": "Consulta Remota Estricta"}).json()
    admin_role = next(item for item in client.get("/api/v1/roles", headers=headers).json() if item["nombre"] == "ADMIN")
    assert client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": "remote.strict", "password": "Clave-de-prueba-123", "id_rol": admin_role["id"], "sector": "Administracion", "consulta_remota": True}).status_code == 201
    remote = auth(client.post("/api/v1/auth/login", json={"username": "remote.strict", "password": "Clave-de-prueba-123"}).json()["access_token"])

    assert client.get("/api/v1/kpi", headers=remote).status_code == 200
    assert client.get("/api/v1/health", headers=remote).status_code == 403
    assert client.get("/api/v1/catalogos/box", headers=remote).status_code == 403
    assert client.get("/api/v1/laboratorio/configuracion", headers=remote).status_code == 403
    assert client.get("/api/v1/registros/m1", headers=remote).status_code == 403
    assert client.post("/api/v1/catalogos", headers=remote, json={"tipo": "box", "codigo": "REMOTE", "descripcion": "No debe crearse"}).status_code == 403


def test_cp21_cp44_cp62_carga_cannot_read_other_sector_or_old_history(client, admin_token):
    _, token = create_carga(client, admin_token, username="carga.prensas.scope", sector="Prensas")
    headers = auth(token)

    assert client.get("/api/v1/registros/m1", headers=headers).status_code == 403
    assert client.get(f"/api/v1/registros/m9?desde={(date.today() - timedelta(days=7)).isoformat()}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/registros/m9?desde={(date.today() - timedelta(days=6)).isoformat()}", headers=headers).status_code == 200


def test_cp22_closed_record_correction_requires_reason_and_is_audited(client, admin_token):
    person, token = create_carga(client, admin_token, username="carga.molienda.correction", sector="Molienda")
    payload = {
        "fecha_operativa": "2026-01-02", "turno_codigo": "08-16",
        "instante_medicion": datetime(2026, 1, 2, 8, tzinfo=timezone.utc).isoformat(),
        "id_responsable": person["id"], "origen_dato": "digital_directo",
        "datos": {"box_activo": 1, "humedad_verdes": "2.8", "residuo": "1.8", "aeroseparador": "80", "punto": "verdes"},
    }
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=payload).json()
    assert client.post(f"/api/v1/registros/m1/{created['id']}/cerrar", headers=auth(token), json={"comentario": "Cierre"}).status_code == 200
    assert client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(admin_token), json={"revision": 2, "datos": created["datos"]}).status_code == 422
    corrected = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(admin_token), json={"revision": 2, "motivo_correccion": "Correccion supervisada", "datos": {**created["datos"], "humedad_verdes": "2.9"}})
    assert corrected.status_code == 200
    with SessionLocal() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.tabla == "registro_operativo", AuditLog.accion == "CORRECCION"))
        assert audit is not None and audit.motivo == "Correccion supervisada"
        assert ast.literal_eval(audit.valor_anterior["datos"])["humedad_verdes"] == "2.8"
        assert ast.literal_eval(audit.valor_nuevo["datos"])["humedad_verdes"] == "2.9"


def test_cp48_permission_table_blocks_ungranted_protected_operations(client, admin_token):
    username = create_permission_limited_user("lector.sin-operaciones")
    limited = auth(client.post("/api/v1/auth/login", json={"username": username, "password": "Clave-de-prueba-123"}).json()["access_token"])

    assert client.get("/api/v1/kpi", headers=limited).status_code == 200
    assert client.get("/api/v1/catalogos/box", headers=limited).status_code == 403
    assert client.post("/api/v1/registros/m1", headers=limited, json={}).status_code == 403
