from datetime import date, datetime, timezone
from uuid import uuid4

from app.db.session import SessionLocal
from app.models.core import AuditLog, OperationalRecord
from tests.conftest import auth


def create_carga(client, admin_token):
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-FT-01", "apellido_nombre": "Digitador de Papel"}).json()
    roles = client.get("/api/v1/roles", headers=headers).json()
    role = next(item for item in roles if item["nombre"] == "CARGA")
    response = client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": "carga.ft", "password": "Clave-de-prueba-FT-123", "id_rol": role["id"], "sector": "Molienda"})
    assert response.status_code == 201
    token = client.post("/api/v1/auth/login", json={"username": "carga.ft", "password": "Clave-de-prueba-FT-123"}).json()["access_token"]
    return person, token


def test_paper_entry_preserves_operational_moment_and_is_idempotent(client, admin_token):
    person, token = create_carga(client, admin_token)
    client_uuid = uuid4()
    payload = {
        "client_uuid": str(client_uuid),
        "fecha_operativa": "2026-01-01",
        "turno_codigo": "20-04",
        "instante_medicion": datetime(2026, 1, 2, 1, 30, tzinfo=timezone.utc).isoformat(),
        "id_responsable": person["id"],
        "datos": {"formulario_id": "M1-2026-0101-01", "box_activo": 1, "humedad_verdes": "4.1", "residuo": "1.8", "aeroseparador": "80"},
    }
    first = client.post("/api/v1/registros/m1", headers=auth(token), json=payload)
    second = client.post("/api/v1/registros/m1", headers=auth(token), json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["origen_dato"] == "papel_digitado"
    assert first.json()["fecha_operativa"] == "2026-01-01"
    assert first.json()["id_usuario_digitador"] is not None
    with SessionLocal() as db:
        assert db.query(OperationalRecord).count() == 1
        assert db.query(AuditLog).filter(AuditLog.accion == "DIGITACION_PAPEL").count() == 1


def test_paper_entry_rejects_wrong_night_shift_operational_date(client, admin_token):
    person, token = create_carga(client, admin_token)
    response = client.post("/api/v1/registros/m1", headers=auth(token), json={
        "fecha_operativa": date(2026, 1, 2).isoformat(),
        "turno_codigo": "20-04",
        "instante_medicion": datetime(2026, 1, 2, 1, tzinfo=timezone.utc).isoformat(),
        "id_responsable": person["id"],
    })
    assert response.status_code == 422


def test_printable_forms_have_repeated_header_and_thickness_pages(client, admin_token):
    _, token = create_carga(client, admin_token)
    response = client.get("/api/v1/exportar?modulo=m10", headers=auth(token))
    assert response.status_code == 200
    assert response.text.count("M10 Espesores") == 3
    assert all(label in response.text for label in ("Prensa 1", "Prensa 2", "Prensa 3", "@page{size:A4 landscape"))
