from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import AppliedLimit, LaboratoryDeviationEvent, LaboratoryGranulometryResult, User
from tests.conftest import auth
from tests.test_f1_operations import carga_token, seed_humidity_limit


def create_f7_configuration(client, token):
    unit = client.post("/api/v1/laboratorio/unidades", headers=auth(token), json={"codigo": "%", "descripcion": "Porcentaje"}).json()
    point = client.post("/api/v1/laboratorio/puntos-muestreo", headers=auth(token), json={"codigo": "VERDES", "descripcion": "Salida Verdes", "sector": "Laboratorio"}).json()
    humidity = client.post("/api/v1/laboratorio/determinaciones", headers=auth(token), json={"codigo": "HUMEDAD", "descripcion": "Humedad", "tipo_resultado": "NUMERICO"}).json()
    granulometry = client.post("/api/v1/laboratorio/determinaciones", headers=auth(token), json={"codigo": "GRAN", "descripcion": "Granulometria", "tipo_resultado": "GRANULOMETRIA"}).json()
    sieve = client.post("/api/v1/laboratorio/tamices", headers=auth(token), json={"codigo": "MESH-TEST", "descripcion": "Tamiz configurado", "torre": "TORRE-A"}).json()
    numeric = client.post("/api/v1/laboratorio/configuraciones", headers=auth(token), json={"id_punto": point["id"], "id_determinacion": humidity["id"], "id_unidad": unit["id"], "id_limite": "L02", "vigente_desde": "2020-01-01"})
    gran = client.post("/api/v1/laboratorio/configuraciones", headers=auth(token), json={"id_punto": point["id"], "id_determinacion": granulometry["id"], "id_unidad": unit["id"], "vigente_desde": "2020-01-01"})
    assert numeric.status_code == gran.status_code == 201
    for configuration in (numeric.json(), gran.json()):
        frequency = client.post("/api/v1/laboratorio/frecuencias", headers=auth(token), json={"id_configuracion": configuration["id"], "vigente_desde": "2026-01-02T00:00:00Z", "intervalo_horas": "8"})
        assert frequency.status_code == 201, frequency.text
    assert client.post(f"/api/v1/laboratorio/configuraciones/{gran.json()['id']}/tamices", headers=auth(token), json={"id_tamiz": sieve["id"]}).status_code == 201
    return point, numeric.json(), gran.json(), sieve


def test_f7_configurable_analysis_sieves_limits_agenda_and_compliance(client, admin_token):
    assert client.get("/api/v1/laboratorio/configuracion", headers=auth(admin_token)).json()["mensaje_configuracion"]
    seed_humidity_limit()
    point, numeric, gran, sieve = create_f7_configuration(client, admin_token)
    operator, lab_token = carga_token(client, admin_token, sector="Laboratorio")
    payload = {"client_uuid": "70000000-0000-0000-0000-000000000001", "id_punto": point["id"], "fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_muestreo": "2026-01-02T08:00:00Z", "resultados": [{"id_configuracion": numeric["id"], "valor": "4.1"}], "granulometria": [{"id_configuracion": gran["id"], "id_tamiz": sieve["id"], "valor": "50"}]}
    created = client.post("/api/v1/laboratorio/analisis", headers=auth(lab_token), json=payload)
    assert created.status_code == 201, created.text
    assert client.post("/api/v1/laboratorio/analisis", headers=auth(lab_token), json=payload).json()["id"] == created.json()["id"]
    with SessionLocal() as db:
        assert db.scalar(select(AppliedLimit).where(AppliedLimit.tabla_origen == "analisis_laboratorio_resultado")).resultado == "FUERA_DE_RANGO"
        assert db.scalar(select(LaboratoryDeviationEvent)).id_desvio == "D01"
        assert str(db.scalar(select(LaboratoryGranulometryResult)).id_tamiz) == sieve["id"]
    agenda = client.get(f"/api/v1/laboratorio/agenda?desde=2026-01-02T00:00:00Z&hasta=2026-01-03T00:00:00Z&id_punto={point['id']}", headers=auth(lab_token))
    assert agenda.status_code == 200
    assert agenda.json()["cumplimiento"]["esperados"] == 6
    assert agenda.json()["cumplimiento"]["realizados"] == 2
    assert client.get("/api/v1/laboratorio/analisis?desde=2020-01-01", headers=auth(lab_token)).status_code == 403
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token), json={}).status_code == 200
    facts = client.get("/api/v1/kpi?contexto=Laboratorio", headers=auth(admin_token)).json()["hechos"]
    assert facts[0]["metricas"]["analisis_laboratorio"] == 1.0


def test_f7_rejects_unconfigured_sieve_and_non_lab_carga(client, admin_token):
    seed_humidity_limit()
    point, numeric, gran, sieve = create_f7_configuration(client, admin_token)
    _, milling_token = carga_token(client, admin_token, sector="Molienda")
    payload = {"id_punto": point["id"], "fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_muestreo": datetime(2026, 1, 2, 8, tzinfo=timezone.utc).isoformat(), "resultados": [{"id_configuracion": numeric["id"], "valor": "2.8"}]}
    assert client.post("/api/v1/laboratorio/analisis", headers=auth(milling_token), json=payload).status_code == 403
    with SessionLocal.begin() as db:
        db.query(User).filter_by(nombre_usuario="carga.f1").one().sector = "Laboratorio"
    lab_token = client.post("/api/v1/auth/login", json={"username": "carga.f1", "password": "Clave-de-prueba-F1-123"}).json()["access_token"]
    payload["granulometria"] = [{"id_configuracion": gran["id"], "id_tamiz": numeric["id"], "valor": "10"}]
    assert client.post("/api/v1/laboratorio/analisis", headers=auth(lab_token), json=payload).status_code == 422
