from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import AuditLog, PlcRawReading, PlcReadingAggregate, TemporalMeasurementFact
from tests.conftest import auth


def tag_payload(**overrides):
    payload = {
        "metrica": "medicion_prueba",
        "referencia_tag": "TEST.TAG.01",
        "unidad": "unidad_prueba",
        "escala_factor": "2",
        "escala_offset": "1",
        "muestreo_segundos": 60,
        "agregacion_segundos": 300,
        "retencion_crudo_dias": 2,
        "retencion_agregado_dias": 5,
        "turno_codigo": "TURNO_PRUEBA",
        "sector": "Sector de prueba",
        "valor_simulado_crudo": "5",
        "calidad_simulada": "GOOD",
        "activo": True,
    }
    payload.update(overrides)
    return payload


def create_source(client, token):
    response = client.post("/api/v1/plc/configuracion", headers=auth(token), json={"nombre": "Fuente de prueba", "adaptador": "TEST_SIMULATOR", "activo": True})
    assert response.status_code == 201, response.text
    return response.json()


def supervision_token(client, admin_token):
    roles = client.get("/api/v1/roles", headers=auth(admin_token)).json()
    role_id = next(row["id"] for row in roles if row["nombre"] == "SUPERVISION")
    person = client.post("/api/v1/personas", headers=auth(admin_token), json={"legajo": "TEST-SUP", "apellido_nombre": "Supervision de Prueba"})
    assert person.status_code == 201
    user = client.post("/api/v1/usuarios", headers=auth(admin_token), json={"id_persona": person.json()["id"], "nombre_usuario": "supervision.test", "password": "Clave-de-prueba-123", "id_rol": role_id, "sector": "Supervision"})
    assert user.status_code == 201
    login = client.post("/api/v1/auth/login", json={"username": "supervision.test", "password": "Clave-de-prueba-123"})
    assert login.status_code == 200
    return login.json()["access_token"]


def test_f6_requires_explicit_test_only_configuration_and_admin(client, admin_token):
    supervisor = supervision_token(client, admin_token)
    assert client.post("/api/v1/plc/configuracion", headers=auth(supervisor), json={"nombre": "No permitido", "adaptador": "TEST_SIMULATOR", "activo": True}).status_code == 403
    assert client.post("/api/v1/plc/configuracion", headers=auth(admin_token), json={"nombre": "No permitido", "adaptador": "OTRO", "activo": True}).status_code == 422
    source = create_source(client, admin_token)
    incomplete = client.post(f"/api/v1/plc/configuracion/{source['id']}/tags", headers=auth(admin_token), json={"metrica": "sin configuracion"})
    assert incomplete.status_code == 422
    invalid_scale = client.post(f"/api/v1/plc/configuracion/{source['id']}/tags", headers=auth(admin_token), json=tag_payload(escala_factor="0"))
    assert invalid_scale.status_code == 422


def test_f6_test_simulator_persists_raw_quality_aggregates_facts_status_and_audit(client, admin_token):
    source = create_source(client, admin_token)
    tag = client.post(f"/api/v1/plc/configuracion/{source['id']}/tags", headers=auth(admin_token), json=tag_payload()).json()
    sampled = client.post(f"/api/v1/plc/configuracion/{source['id']}/simular-lectura", headers=auth(admin_token))
    assert sampled.status_code == 200, sampled.text
    assert sampled.json() == {"muestras_guardadas": 1, "adaptador": "TEST_SIMULATOR"}
    assert client.post(f"/api/v1/plc/configuracion/{source['id']}/simular-lectura", headers=auth(admin_token)).json()["muestras_guardadas"] == 0
    with SessionLocal() as db:
        raw = db.scalar(select(PlcRawReading))
        aggregate = db.scalar(select(PlcReadingAggregate))
        fact = db.scalar(select(TemporalMeasurementFact).where(TemporalMeasurementFact.tabla_origen == "plc_lectura_cruda"))
        audits = list(db.scalars(select(AuditLog).where(AuditLog.tabla == "plc_estado_adquisicion")))
        assert str(raw.id_tag) == tag["id"]
        assert str(raw.valor_crudo) == "5.00000000"
        assert str(raw.valor_escalado) == "11.00000000"
        assert raw.calidad == "GOOD"
        assert aggregate.cantidad_muestras == 1
        assert str(aggregate.valor_promedio) == "11.00000000"
        assert fact.id_registro_origen == raw.id
        assert fact.valor == raw.valor_escalado
        assert fact.contexto["referencia_tag"] == "TEST.TAG.01"
        assert len(audits) == 2
    status = client.get("/api/v1/plc/estado", headers=auth(admin_token))
    assert status.status_code == 200
    assert status.json()[0]["estado"] == "ACTIVO"
    assert status.json()[0]["tags_activos"] == 1
    assert status.json()[0]["ultima_muestra_en"] is not None
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token), json={}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(TemporalMeasurementFact).where(TemporalMeasurementFact.tabla_origen == "plc_lectura_cruda")) is not None


def test_f6_supervision_can_only_read_acquisition_status(client, admin_token):
    source = create_source(client, admin_token)
    supervisor = supervision_token(client, admin_token)
    status = client.get("/api/v1/plc/estado", headers=auth(supervisor))
    assert status.status_code == 200
    assert status.json()[0]["id_fuente"] == source["id"]
    assert client.get("/api/v1/plc/configuracion", headers=auth(supervisor)).status_code == 403


def test_f6_keeps_bad_quality_raw_readings_without_a_numeric_fact(client, admin_token):
    source = create_source(client, admin_token)
    tag = client.post(f"/api/v1/plc/configuracion/{source['id']}/tags", headers=auth(admin_token), json=tag_payload(metrica="medicion_calidad_mala", referencia_tag="TEST.TAG.BAD", calidad_simulada="BAD")).json()
    assert client.post(f"/api/v1/plc/configuracion/{source['id']}/simular-lectura", headers=auth(admin_token)).json()["muestras_guardadas"] == 1
    with SessionLocal() as db:
        raw = db.scalar(select(PlcRawReading).where(PlcRawReading.id_tag == tag["id"]))
        aggregate = db.scalar(select(PlcReadingAggregate).where(PlcReadingAggregate.id_tag == tag["id"]))
        fact = db.scalar(select(TemporalMeasurementFact).where(TemporalMeasurementFact.id_registro_origen == raw.id))
        assert raw.calidad == aggregate.calidad == "BAD"
        assert aggregate.valor_minimo is None
        assert fact.valor is None
