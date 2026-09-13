import ast
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.db.session import SessionLocal
from app.main import app
from app.models.core import AppliedLimit, AuditLog, Base, LimitVersion, OperationalRecord, User
from tests.conftest import auth


def create_carga(client, admin_token, username: str, sector: str) -> tuple[dict, str]:
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": f"CP-{username}", "apellido_nombre": username}).json()
    role = next(row for row in client.get("/api/v1/roles", headers=headers).json() if row["nombre"] == "CARGA")
    created = client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": username, "password": "Clave-de-prueba-123", "id_rol": role["id"], "sector": sector})
    assert created.status_code == 201, created.text
    token = client.post("/api/v1/auth/login", json={"username": username, "password": "Clave-de-prueba-123"}).json()["access_token"]
    return person, token


def m1_payload(person_id: str, operational_date: date, humidity: str = "2.8") -> dict:
    measured_at = datetime.combine(operational_date, datetime.min.time(), tzinfo=timezone.utc).replace(hour=8)
    return {
        "client_uuid": str(uuid4()), "fecha_operativa": operational_date.isoformat(), "turno_codigo": "08-16",
        "instante_medicion": measured_at.isoformat(), "id_responsable": person_id,
        "origen_dato": "digital_directo",
        "datos": {"box_activo": 1, "humedad_verdes": humidity, "residuo": "1.8", "aeroseparador": "80", "punto": "verdes"},
    }


def test_cp21_cp44_cp62_backend_scope_and_own_draft_only(client, admin_token):
    person, token = create_carga(client, admin_token, "cp.scope.molienda", "Molienda")
    headers = auth(token)
    today = date.today()
    admin_record = client.post("/api/v1/registros/m1", headers=auth(admin_token), json=m1_payload(person["id"], today)).json()

    visible = client.get(f"/api/v1/registros/m1?desde={today.isoformat()}&hasta={today.isoformat()}", headers=headers)
    assert visible.status_code == 200
    assert [row["id"] for row in visible.json()] == [admin_record["id"]]
    assert client.get("/api/v1/registros/m9", headers=headers).status_code == 403
    assert client.get(f"/api/v1/registros/m1?desde={(today - timedelta(days=7)).isoformat()}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/registros/m1?hasta={(today - timedelta(days=7)).isoformat()}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/registros/m1?hasta={(today + timedelta(days=1)).isoformat()}", headers=headers).status_code == 403

    assert client.put(f"/api/v1/registros/m1/{admin_record['id']}", headers=headers, json={"revision": 1, "datos": admin_record["datos"]}).status_code == 403
    own_record = client.post("/api/v1/registros/m1", headers=headers, json=m1_payload(person["id"], today)).json()
    assert client.put(f"/api/v1/registros/m1/{own_record['id']}", headers=headers, json={"revision": 1, "datos": {**own_record["datos"], "humedad_verdes": "2.9"}}).status_code == 200

    _, lab_token = create_carga(client, admin_token, "cp.scope.lab", "Laboratorio")
    assert client.get(f"/api/v1/laboratorio/analisis?hasta={(today - timedelta(days=7)).isoformat()}", headers=auth(lab_token)).status_code == 403
    assert client.get(f"/api/v1/laboratorio/agenda?desde={(today - timedelta(days=7)).isoformat()}T00:00:00Z&hasta={today.isoformat()}T00:00:00Z", headers=auth(lab_token)).status_code == 403


def test_cp22_closed_correction_audit_exposes_old_new_user_and_timestamp(client, admin_token):
    person, token = create_carga(client, admin_token, "cp.audit.molienda", "Molienda")
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], date.today())).json()
    assert client.post(f"/api/v1/registros/m1/{created['id']}/cerrar", headers=auth(token), json={"comentario": "Cierre de turno"}).status_code == 200
    assert client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json={"revision": 2, "datos": created["datos"]}).status_code == 403
    corrected = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(admin_token), json={"revision": 2, "motivo_correccion": "Lectura verificada", "datos": {**created["datos"], "humedad_verdes": "2.9"}})
    assert corrected.status_code == 200, corrected.text

    audits = client.get("/api/v1/auditoria", headers=auth(admin_token)).json()
    correction = next(row for row in audits if row["accion"] == "CORRECCION" and row["id_registro"] == created["id"])
    with SessionLocal() as db:
        admin_id = db.scalar(select(User.id).where(User.nombre_usuario == "admin.test"))
    assert correction["id_usuario"] == str(admin_id)
    assert datetime.fromisoformat(correction["creado_en"].replace("Z", "+00:00")).tzinfo is not None
    assert ast.literal_eval(correction["valor_anterior"]["datos"])["humedad_verdes"] == "2.8"
    assert ast.literal_eval(correction["valor_nuevo"]["datos"])["humedad_verdes"] == "2.9"


def test_cp28_void_requires_reason_prevents_physical_delete_and_keeps_immutable_audit(client, admin_token):
    person, token = create_carga(client, admin_token, "cp.void.molienda", "Molienda")
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], date.today())).json()
    assert client.post(f"/api/v1/registros/m1/{created['id']}/anular", headers=auth(admin_token), json={"comentario": ""}).status_code == 422
    voided = client.post(f"/api/v1/registros/m1/{created['id']}/anular", headers=auth(admin_token), json={"comentario": "Duplicado en formulario"})
    assert voided.status_code == 200 and voided.json()["estado"] == "ANULADO"
    assert client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(admin_token), json={"revision": 2, "motivo_correccion": "No debe cambiar", "datos": created["datos"]}).status_code == 422

    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as db:
            db.delete(db.get(OperationalRecord, created["id"]))
    with SessionLocal() as db:
        assert db.get(OperationalRecord, created["id"]).motivo_anulacion == "Duplicado en formulario"
    audit = next(row for row in client.get("/api/v1/auditoria", headers=auth(admin_token)).json() if row["accion"] == "ANULACION")
    assert audit["motivo"] == "Duplicado en formulario"
    assert ast.literal_eval(audit["valor_nuevo"]["datos"])["humedad_verdes"] == "2.8"

    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as db:
            db.get(AuditLog, audit["id"]).motivo = "Alterado"
    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as db:
            db.delete(db.get(AuditLog, audit["id"]))


def test_cp45_applied_limit_version_and_historical_kpi_are_preserved(client, admin_token):
    today, historical_date = date.today(), date.today() - timedelta(days=1)
    assert client.post("/api/v1/limites", headers=auth(admin_token), json={"id": "L02", "variable": "Humedad", "etapa": "Molienda", "unidad": "%", "tipo_dato": "numero"}).status_code == 201
    old_version = client.post("/api/v1/limites/L02/versiones", headers=auth(admin_token), json={"vigente_desde": (today - timedelta(days=2)).isoformat(), "vigente_hasta_exclusiva": today.isoformat(), "valor_min": "2", "valor_max": "3.5", "operador_min": ">=", "operador_max": "<=", "nivel": "ADVERTENCIA", "motivo_cambio": "Limite historico"}).json()
    new_version = client.post("/api/v1/limites/L02/versiones", headers=auth(admin_token), json={"vigente_desde": today.isoformat(), "valor_min": "2.5", "valor_max": "3", "operador_min": ">=", "operador_max": "<=", "nivel": "ADVERTENCIA", "motivo_cambio": "Cambio vigente"}).json()
    with SessionLocal() as db:
        person_id = db.scalar(select(User.id_persona).where(User.nombre_usuario == "admin.test"))
    created = client.post("/api/v1/registros/m1", headers=auth(admin_token), json=m1_payload(str(person_id), historical_date, "2.2")).json()
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200

    with SessionLocal() as db:
        applied = db.scalar(select(AppliedLimit).where(AppliedLimit.id_registro == created["id"], AppliedLimit.campo == "humedad_verdes"))
        assert str(applied.id_limite_version) == old_version["id"]
        assert db.get(LimitVersion, applied.id_limite_version).valor_min == 2
    historical_limits = client.get(f"/api/v1/limites?fecha={historical_date.isoformat()}", headers=auth(admin_token)).json()
    assert historical_limits[0]["id"] == old_version["id"]
    assert new_version["id"] != old_version["id"]
    trend = client.get(f"/api/v1/kpi/tendencias?metrica=humedad_verdes&desde={historical_date.isoformat()}&hasta={historical_date.isoformat()}", headers=auth(admin_token)).json()
    assert trend["puntos"][0]["banda_limite"]["min"] == 2.0


def test_cp50_rejects_ia_for_every_registros_path_and_has_no_prediction_surface(client, admin_token):
    for module in ("m1", "m2", "m3", "m6", "m8", "m9", "m10"):
        response = client.post(f"/api/v1/registros/{module}", headers=auth(admin_token), json={"origen_dato": "ia"})
        assert response.status_code == 422
        assert any(error["loc"][-1] == "origen_dato" for error in response.json()["detail"])
    maintenance = client.post("/api/v1/registros/m7", headers=auth(admin_token), json={"origen_dato": "ia"})
    assert maintenance.status_code == 422
    assert any(error["loc"][-1] == "origen_dato" for error in maintenance.json()["detail"])
    assert not any("predic" in path for path in app.openapi()["paths"])
    assert not any("predic" in table.name for table in Base.metadata.sorted_tables)

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.nombre_usuario == "admin.test"))
    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as db:
            db.add(OperationalRecord(modulo="M1", sector="Molienda", client_uuid=uuid4(), estado="BORRADOR", origen_dato="ia", fecha_operativa=date.today(), turno_codigo="08-16", instante_medicion=datetime.now(timezone.utc), id_responsable=admin.id_persona, creado_por=admin.id, datos={}))


def test_cp55_voided_operational_record_keeps_calendar_scheduled_denominator(client, admin_token):
    today = date.today()
    with SessionLocal() as db:
        person_id = db.scalar(select(User.id_persona).where(User.nombre_usuario == "admin.test"))
    assert client.post("/api/v1/calendario", headers=auth(admin_token), json={"fecha_operativa": today.isoformat(), "turno_codigo": "08-16", "programado": True, "horas_programadas": "8", "motivo": "Turno programado"}).status_code == 201
    record = client.post("/api/v1/registros/m1", headers=auth(admin_token), json=m1_payload(str(person_id), today)).json()
    assert client.post(f"/api/v1/registros/m1/{record['id']}/anular", headers=auth(admin_token), json={"comentario": "Carga duplicada"}).status_code == 200
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    fact = next(row for row in client.get(f"/api/v1/kpi?desde={today.isoformat()}&hasta={today.isoformat()}&contexto=Molienda", headers=auth(admin_token)).json()["hechos"] if row["turno"] == "08-16")
    assert fact["metricas"]["horas_programadas"] == 8.0
    assert "humedad_verdes" not in fact["metricas"]
