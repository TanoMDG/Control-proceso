from datetime import date, timedelta

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.core import Catalog, Person, Role, User
from app.services.bootstrap import ensure_base_roles
from app.services.security import hash_password
from tests.conftest import auth


def test_admin_creates_person_user_and_audit(client, admin_token):
    headers = auth(admin_token)
    person_response = client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-002", "apellido_nombre": "Persona de Prueba"})
    assert person_response.status_code == 201
    person = person_response.json()
    roles = client.get("/api/v1/roles", headers=headers).json()
    carga_role = next(role for role in roles if role["nombre"] == "CARGA")
    user_response = client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": "carga.test", "password": "Clave-de-prueba-456", "id_rol": carga_role["id"], "sector": "Prensas"})
    assert user_response.status_code == 201
    audit = client.get("/api/v1/auditoria", headers=headers)
    assert audit.status_code == 200
    assert {row["tabla"] for row in audit.json()} >= {"persona", "usuario"}


def test_backend_enforces_permissions_not_frontend(client, admin_token):
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-003", "apellido_nombre": "Carga Prueba"}).json()
    carga_role = next(role for role in client.get("/api/v1/roles", headers=headers).json() if role["nombre"] == "CARGA")
    client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": "carga.permissions", "password": "Clave-de-prueba-789", "id_rol": carga_role["id"], "sector": "Prensas"})
    response = client.post("/api/v1/auth/login", json={"username": "carga.permissions", "password": "Clave-de-prueba-789"})
    token = response.json()["access_token"]
    assert client.get("/api/v1/usuarios", headers=auth(token)).status_code == 403
    assert client.get("/api/v1/catalogos/box", headers=auth(token)).status_code == 200


def test_remote_profile_is_limited_to_dashboard_summary(client, admin_token):
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-REMOTE", "apellido_nombre": "Consulta Remota"}).json()
    admin_role = next(role for role in client.get("/api/v1/roles", headers=headers).json() if role["nombre"] == "ADMIN")
    created = client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": "remote.dashboard", "password": "Clave-de-prueba-remote-123", "id_rol": admin_role["id"], "sector": "Administracion", "consulta_remota": True})
    assert created.status_code == 201
    token = client.post("/api/v1/auth/login", json={"username": "remote.dashboard", "password": "Clave-de-prueba-remote-123"}).json()["access_token"]
    assert client.get("/api/v1/kpi", headers=auth(token)).status_code == 200
    assert client.get("/api/v1/kpi/tendencias?metrica=humedad_verdes", headers=auth(token)).status_code == 403
    assert client.get("/api/v1/catalogos/box", headers=auth(token)).status_code == 403


def test_limit_versions_do_not_overlap_and_historical_read_is_stable(client, admin_token):
    headers = auth(admin_token)
    assert client.post("/api/v1/limites", headers=headers, json={"id": "TEST-L01", "variable": "Variable test", "etapa": "Prueba", "unidad": "%", "tipo_dato": "Especificacion"}).status_code == 201
    start = date.today() + timedelta(days=10)
    first = {"vigente_desde": start.isoformat(), "vigente_hasta_exclusiva": (start + timedelta(days=10)).isoformat(), "valor_min": "1", "operador_min": ">=", "nivel": "ADVERTENCIA", "motivo_cambio": "Prueba"}
    assert client.post("/api/v1/limites/TEST-L01/versiones", headers=headers, json=first).status_code == 201
    overlapping = {**first, "vigente_desde": (start + timedelta(days=5)).isoformat()}
    assert client.post("/api/v1/limites/TEST-L01/versiones", headers=headers, json=overlapping).status_code == 422
    historical = client.get(f"/api/v1/limites?fecha={start.isoformat()}", headers=headers)
    assert historical.status_code == 200
    assert historical.json()[0]["id_limite"] == "TEST-L01"


def test_audit_log_is_database_immutable(client, admin_token):
    headers = auth(admin_token)
    client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-004", "apellido_nombre": "Audit Test"})
    with SessionLocal.begin() as db:
        audit_id = db.execute(text("SELECT id FROM auditoria LIMIT 1")).scalar_one()
    with SessionLocal() as db:
        try:
            db.execute(text("DELETE FROM auditoria WHERE id = :id"), {"id": audit_id})
            db.commit()
        except Exception:
            db.rollback()
        else:
            raise AssertionError("La base permitio borrar auditoria")


def test_catalog_logical_deactivation_requires_date(client, admin_token):
    headers = auth(admin_token)
    catalog = client.post("/api/v1/catalogos", headers=headers, json={"tipo": "test", "codigo": "TEST", "descripcion": "Catalogo de prueba"}).json()
    assert client.patch(f"/api/v1/catalogos/{catalog['id']}", headers=headers, json={"activo": False}).status_code == 422
    assert client.patch(f"/api/v1/catalogos/{catalog['id']}", headers=headers, json={"activo": False, "fecha_baja": date.today().isoformat()}).status_code == 200
    assert client.get("/api/v1/catalogos/test", headers=headers).json() == []
