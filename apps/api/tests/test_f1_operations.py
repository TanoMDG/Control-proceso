from datetime import date, datetime, timezone

from app.db.session import SessionLocal
from app.models.core import DeviationEvent, Limit, LimitVersion, ReactionPlan, SiloScale, SiloScalePoint, SyncConflict, SyncRevision, User
from tests.conftest import auth


def carga_token(client, admin_token, sector="Molienda"):
    headers = auth(admin_token)
    person = client.post("/api/v1/personas", headers=headers, json={"legajo": "TEST-F1-01", "apellido_nombre": "Operador Molienda"}).json()
    role = next(item for item in client.get("/api/v1/roles", headers=headers).json() if item["nombre"] == "CARGA")
    client.post("/api/v1/usuarios", headers=headers, json={"id_persona": person["id"], "nombre_usuario": "carga.f1", "password": "Clave-de-prueba-F1-123", "id_rol": role["id"], "sector": sector})
    token = client.post("/api/v1/auth/login", json={"username": "carga.f1", "password": "Clave-de-prueba-F1-123"}).json()["access_token"]
    return person, token


def seed_humidity_limit():
    with SessionLocal.begin() as db:
        admin = db.query(User).filter_by(nombre_usuario="admin.test").one()
        db.add(ReactionPlan(id_desvio="D01", senal="Humedad", etapa="Molienda", limite_referencia="L02", causas_probables="Prueba", accion_inmediata="Ajustar", verificacion="Medir", plazo_texto="1 h", registro_escalamiento="Escalar", tipo_plazo="HORAS"))
        db.add(Limit(id="L02", variable="Humedad", etapa="Molienda", unidad="%", tipo_dato="numero"))
        db.add(LimitVersion(id_limite="L02", vigente_desde=date(2020, 1, 1), valor_min="2", valor_max="3.5", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", id_desvio="D01", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"))


def m1_payload(person_id, humidity, hour=8):
    return {"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_medicion": datetime(2026, 1, 2, hour, tzinfo=timezone.utc).isoformat(), "id_responsable": person_id, "origen_dato": "digital_directo", "datos": {"box_activo": 1, "humedad_verdes": humidity, "residuo": "1.8", "aeroseparador": "80", "punto": "verdes"}}


def test_m1_limits_deviations_consecutivity_and_lifecycle(client, admin_token):
    person, token = carga_token(client, admin_token); seed_humidity_limit()
    first = client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], "4.1", 8))
    second = client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], "4.2", 9))
    assert first.status_code == second.status_code == 201
    with SessionLocal() as db:
        events = db.query(DeviationEvent).order_by(DeviationEvent.created_at).all()
        assert [event.estado for event in events] == ["ABIERTO", "ESCALADO"]
        event_id = events[0].id
    treatment = client.post(f"/api/v1/desvios/{event_id}/tratar", headers=auth(token), json={"comentario": "Ajustado"})
    assert treatment.status_code == 200, treatment.text
    assert client.post(f"/api/v1/desvios/{event_id}/verificar", headers=auth(token), json={"comentario": "Verificado"}).status_code == 200
    assert client.post(f"/api/v1/desvios/{event_id}/cerrar", headers=auth(token), json={"comentario": "No permitido"}).status_code == 422
    assert client.post(f"/api/v1/desvios/{event_id}/cerrar", headers=auth(admin_token), json={"comentario": "Cierre supervisor"}).json()["estado"] == "CERRADO"


def test_in_range_measurement_resets_consecutive_deviation_sequence(client, admin_token):
    person, token = carga_token(client, admin_token); seed_humidity_limit()
    for humidity, hour in (("4.1", 8), ("2.8", 9), ("4.2", 10)):
        assert client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], humidity, hour)).status_code == 201
    with SessionLocal() as db:
        events = db.query(DeviationEvent).order_by(DeviationEvent.created_at).all()
        assert [event.estado for event in events] == ["ABIERTO", "ABIERTO"]


def test_invalidated_deviation_is_visible_but_excluded_from_real_kpi(client, admin_token):
    person, token = carga_token(client, admin_token); seed_humidity_limit()
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], "4.1", 8)).json()
    corrected = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(admin_token), json={"revision": created["revision"], "motivo_correccion": "Lectura corregida", "datos": {**created["datos"], "humedad_verdes": "2.8"}})
    assert corrected.status_code == 200, corrected.text
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    fact = client.get("/api/v1/kpi", headers=auth(admin_token)).json()["hechos"][0]["metricas"]
    assert fact["desvios_por_estado"] == {"INVALIDADO": 1}
    assert fact["desvios_reales"] == 0


def test_closed_record_stale_revision_creates_one_sync_conflict(client, admin_token):
    person, token = carga_token(client, admin_token); seed_humidity_limit()
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=m1_payload(person["id"], "4.1", 8)).json()
    assert client.post(f"/api/v1/registros/m1/{created['id']}/cerrar", headers=auth(token), json={"comentario": "Cierre"}).status_code == 200
    payload = {"revision": created["revision"], "datos": created["datos"]}
    for _ in range(2):
        response = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json=payload)
        assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(SyncRevision).filter_by(tabla="registro_operativo").count() == 2
        assert db.query(SyncConflict).filter_by(tabla="registro_operativo", estado="ABIERTO").count() == 1


def test_m2_dosage_and_stoppage_rules(client, admin_token):
    person, token = carga_token(client, admin_token)
    base = {"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_medicion": datetime(2026, 1, 2, 8, tzinfo=timezone.utc).isoformat(), "id_responsable": person["id"], "origen_dato": "digital_directo"}
    m2 = client.post("/api/v1/registros/m2", headers=auth(token), json={**base, "datos": {"caudal_pasta": "30", "caudal_agua": "7500", "humedad_salida": "13"}})
    assert m2.status_code == 201 and m2.json()["datos"]["dosificacion_calc"] == "250"
    invalid_stop = client.post("/api/v1/registros/m6", headers=auth(token), json={**base, "datos": {"causa": "P12", "inicio": "2026-01-02T23:30:00+00:00", "fin": "2026-01-03T01:15:00+00:00"}})
    assert invalid_stop.status_code == 422
    valid_stop = client.post("/api/v1/registros/m6", headers=auth(token), json={**base, "datos": {"causa": "P12", "descripcion": "Atasco", "inicio": "2026-01-02T23:30:00+00:00", "fin": "2026-01-03T01:15:00+00:00"}})
    assert valid_stop.status_code == 201
    assert float(valid_stop.json()["datos"]["duracion_calculada_horas"]) == 1.75


def test_m3_lecho_ksider_silos_and_physical_mapping(client, admin_token):
    person, token = carga_token(client, admin_token)
    with SessionLocal.begin() as db:
        admin = db.query(User).filter_by(nombre_usuario="admin.test").one()
        scale = SiloScale(grupo_silos="1-8", version=1, vigente_desde=date(2020, 1, 1), aprobada_por=admin.id)
        db.add(scale); db.flush()
        db.add_all([SiloScalePoint(id_escala=scale.id, altura_m="0", toneladas="100"), SiloScalePoint(id_escala=scale.id, altura_m="11", toneladas="0")])
    base = {"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_medicion": datetime(2026, 1, 2, 8, tzinfo=timezone.utc).isoformat(), "id_responsable": person["id"], "origen_dato": "digital_directo"}
    assert client.post("/api/v1/registros/m3", headers=auth(token), json={**base, "datos": {"tipo_registro": "lecho", "humedad": "7.8", "temperatura": "330"}}).status_code == 201
    assert client.post("/api/v1/registros/m3", headers=auth(token), json={**base, "datos": {"tipo_registro": "ksider_rechazo", "humedad_ksider": "7", "segundos_pesada": "60"}}).status_code == 201
    stock = client.post("/api/v1/registros/m3", headers=auth(token), json={**base, "datos": {"tipo_registro": "stock_silo", "silo": 1, "linea": "L7", "altura_libre_m": "9"}})
    assert stock.status_code == 201 and float(stock.json()["datos"]["toneladas_calculadas"]) < 20
    invalid = client.post("/api/v1/registros/m3", headers=auth(token), json={**base, "datos": {"tipo_registro": "stock_silo", "silo": 1, "linea": "L6", "altura_libre_m": "9"}})
    assert invalid.status_code == 422
