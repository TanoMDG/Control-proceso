import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.core import (
    DeviationEvent,
    LaboratoryAnalysis,
    LaboratoryDeviationEvent,
    LineProductFormatPeriod,
    OperationalRecord,
    ShiftReceipt,
    SiloLinePeriod,
    SiloScale,
    SiloScalePoint,
    TemporalMeasurementFact,
    User,
)
from tests.conftest import auth
from tests.test_cp_acceptance import create_carga, m1_payload
from tests.test_f1_operations import carga_token, m1_payload as f1_m1_payload, seed_humidity_limit
from tests.test_f3_prensas import base_payload, seed_press_configuration
from tests.test_f4_traceability import create_mua, make_palero
from tests.test_f7_laboratory import create_f7_configuration


def operation_payload(person_id: str, module_data: dict, *, module: str = "m1", when: datetime | None = None, client_uuid: str | None = None) -> dict:
    when = when or datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
    return {
        "client_uuid": client_uuid or str(uuid4()),
        "fecha_operativa": when.date().isoformat(),
        "turno_codigo": "08-16",
        "instante_medicion": when.isoformat(),
        "id_responsable": person_id,
        "origen_dato": "digital_directo",
        "datos": module_data,
    }


def create_silo_scale(admin_id, starts: date, version: int, tonnes_at_zero: str):
    with SessionLocal.begin() as db:
        scale = SiloScale(grupo_silos="1-8", version=version, vigente_desde=starts, aprobada_por=admin_id)
        db.add(scale)
        db.flush()
        db.add_all([
            SiloScalePoint(id_escala=scale.id, altura_m="0", toneladas=tonnes_at_zero),
            SiloScalePoint(id_escala=scale.id, altura_m="10", toneladas="0"),
        ])
        return str(scale.id)


def test_cp03_rejects_box_four_for_m1_consumption(client, admin_token):
    person, token = carga_token(client, admin_token)
    response = client.post("/api/v1/registros/m1", headers=auth(token), json=operation_payload(person["id"], {"box_activo": 4, "humedad_verdes": "2.8", "residuo": "1", "aeroseparador": "80"}))
    assert response.status_code == 422
    assert "1, 2, 3 o 6" in response.json()["detail"]


def test_cp04_burner_correction_requires_old_new_and_reason(client, admin_token):
    person, token = carga_token(client, admin_token)
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=operation_payload(person["id"], {"box_activo": 1, "humedad_verdes": "2.8", "residuo": "1", "aeroseparador": "80", "temperatura_quemador": "600"})).json()
    changed = {**created["datos"], "temperatura_quemador": "610"}
    for data in (changed, {**changed, "temperatura_quemador_previa": "599"}):
        assert client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json={"revision": created["revision"], "datos": data}).status_code == 422
    corrected = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json={"revision": created["revision"], "datos": {**changed, "temperatura_quemador_previa": "600", "motivo_cambio_quemador": "Ajuste de combustion"}})
    assert corrected.status_code == 200
    assert corrected.json()["datos"]["temperatura_quemador"] == "610"
    correction = next(row for row in client.get("/api/v1/auditoria", headers=auth(admin_token)).json() if row["accion"] == "CORRECCION" and row["id_registro"] == created["id"])
    with SessionLocal() as db:
        authenticated_user_id = db.scalar(select(User.id).where(User.nombre_usuario == "carga.f1"))
    assert ast.literal_eval(correction["valor_anterior"]["datos"])["temperatura_quemador"] == "600"
    assert ast.literal_eval(correction["valor_nuevo"]["datos"])["temperatura_quemador"] == "610"
    assert correction["id_usuario"] == str(authenticated_user_id)
    assert datetime.fromisoformat(correction["creado_en"].replace("Z", "+00:00")).tzinfo is not None
    assert correction["motivo"] == "Ajuste de combustion"


def test_cp06_lecho_temperature_warns_with_d10_without_supervisor_override(client, admin_token):
    person, token = carga_token(client, admin_token)
    with SessionLocal.begin() as db:
        admin = db.scalar(select(User).where(User.nombre_usuario == "admin.test"))
        from app.models.core import Limit, LimitVersion, ReactionPlan
        db.add_all([ReactionPlan(id_desvio="D10", senal="Temperatura lecho", etapa="Molienda", limite_referencia="L13", causas_probables="Prueba", accion_inmediata="Ajustar", verificacion="Medir", plazo_texto="1 h", registro_escalamiento="Interno", tipo_plazo="HORAS"), Limit(id="L13", variable="Temperatura lecho", etapa="Molienda", unidad="C", tipo_dato="numero"), LimitVersion(id_limite="L13", vigente_desde=date(2020, 1, 1), valor_max="320", operador_max="<=", nivel="ADVERTENCIA", id_desvio="D10", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE")])
    created = client.post("/api/v1/registros/m3", headers=auth(token), json=operation_payload(person["id"], {"tipo_registro": "lecho", "humedad": "7", "temperatura": "330"}, module="m3"))
    assert created.status_code == 201
    event = client.get("/api/v1/desvios", headers=auth(admin_token)).json()[0]
    assert event["id_desvio"] == "D10" and event["estado"] == "ABIERTO"
    assert client.post(f"/api/v1/desvios/{event['id']}/cerrar", headers=auth(token), json={"comentario": "No autorizado"}).status_code == 422


def test_cp07_cp69_low_silo_stock_creates_d16_without_blocking(client, admin_token):
    person, token = carga_token(client, admin_token)
    with SessionLocal.begin() as db:
        admin = db.scalar(select(User).where(User.nombre_usuario == "admin.test"))
        from app.models.core import Limit, LimitVersion, ReactionPlan
        db.add_all([ReactionPlan(id_desvio="D16", senal="Stock silo", etapa="Molienda", limite_referencia="L26", causas_probables="Prueba", accion_inmediata="Reponer", verificacion="Confirmar", plazo_texto="1 h", registro_escalamiento="Interno", tipo_plazo="HORAS"), Limit(id="L26", variable="Stock silo", etapa="Molienda", unidad="t", tipo_dato="numero"), LimitVersion(id_limite="L26", vigente_desde=date(2020, 1, 1), valor_min="20", operador_min=">=", nivel="ADVERTENCIA", id_desvio="D16", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE")])
        admin_id = admin.id
    create_silo_scale(admin_id, date(2020, 1, 1), 1, "100")
    created = client.post("/api/v1/registros/m3", headers=auth(token), json=operation_payload(person["id"], {"tipo_registro": "stock_silo", "silo": 1, "linea": "L7", "altura_libre_m": "9"}, module="m3"))
    assert created.status_code == 201
    assert float(created.json()["datos"]["toneladas_calculadas"]) < 20
    assert client.get("/api/v1/desvios", headers=auth(admin_token)).json()[0]["id_desvio"] == "D16"


def test_cp14_hopper_emptying_optionally_creates_and_audits_associated_stoppage(client, admin_token):
    person, token = carga_token(client, admin_token, "Prensas")
    seed_press_configuration()
    data = {"linea": "L7", "prensa": "PH5000-1", "causa_vaciado": "Limpieza", "duracion_min": "10"}
    created = client.post("/api/v1/registros/m8", headers=auth(token), json={**base_payload(person["id"]), "datos": data})
    assert created.status_code == 201
    assert created.json()["datos"]["recordatorio_descarte_min"] == "10"
    assert "id_parada_asociada" not in created.json()["datos"]
    associated = client.get("/api/v1/registros/m6", headers=auth(admin_token)).json()
    assert not any(row["datos"].get("id_m8_asociado") == created.json()["id"] for row in associated)

    opted_in = client.post("/api/v1/registros/m8", headers=auth(token), json={**base_payload(person["id"]), "crear_parada_asociada": True, "datos": data})
    assert opted_in.status_code == 201
    linked_id = opted_in.json()["datos"]["id_parada_asociada"]
    associated = client.get("/api/v1/registros/m6", headers=auth(admin_token)).json()
    assert any(row["id"] == linked_id and row["datos"]["causa"] == "VACIADO_TOLVA" and row["datos"]["id_m8_asociado"] == opted_in.json()["id"] for row in associated)
    audits = client.get("/api/v1/auditoria", headers=auth(admin_token)).json()
    assert any(row["id_registro"] == linked_id and row["motivo"] == "Parada asociada al vaciado de tolva M8" for row in audits)
    assert any(row["id_registro"] == opted_in.json()["id"] and linked_id in row["valor_nuevo"]["datos"] for row in audits)


def test_cp24_deactivated_palero_is_hidden_but_mua_history_remains(client, admin_token):
    with SessionLocal() as db:
        preparer_id = str(db.scalar(select(User.id_persona).where(User.nombre_usuario == "admin.test")))
    make_palero(preparer_id)
    mua = create_mua(client, admin_token, preparer_id).json()
    assert client.post("/api/v1/trazabilidad/mua-box", headers=auth(admin_token), json={"id_mua": mua["id"], "box": "1", "desde": "2026-01-02T08:00:00Z"}).status_code == 201
    assert client.patch(f"/api/v1/personas/{preparer_id}", headers=auth(admin_token), json={"activo": False, "fecha_baja": "2026-01-03"}).status_code == 200
    assert client.get("/api/v1/trazabilidad/preparadores", headers=auth(admin_token)).json() == []
    assert client.get(f"/api/v1/mua/{mua['id']}/trazabilidad", headers=auth(admin_token)).json()["mua"]["id_preparador"] == preparer_id


def test_cp26_dashboard_total_matches_manual_calculation(client, admin_token):
    person, token = carga_token(client, admin_token)
    day = date(2026, 1, 2)
    for humidity, hour in (("2", 8), ("4", 9), ("3", 10)):
        assert client.post("/api/v1/registros/m1", headers=auth(token), json=operation_payload(person["id"], {"box_activo": 1, "humedad_verdes": humidity, "residuo": "1", "aeroseparador": "80"}, when=datetime(2026, 1, 2, hour, tzinfo=timezone.utc))).status_code == 201
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    fact = client.get(f"/api/v1/kpi?desde={day}&hasta={day}&contexto=Molienda", headers=auth(admin_token)).json()["hechos"][0]["metricas"]
    assert fact["humedad_verdes"] == (2 + 4 + 3) / 3


def test_cp33_two_silos_can_feed_line_seven_concurrently(client, admin_token):
    person, token = carga_token(client, admin_token)
    for silo in (1, 2):
        assert client.post("/api/v1/trazabilidad/silo-linea", headers=auth(token), json={"silo": silo, "linea": "L7", "desde": "2026-01-02T08:00:00Z"}).status_code == 201
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SiloLinePeriod).where(SiloLinePeriod.linea == "L7", SiloLinePeriod.hasta.is_(None))))) == 2


def test_cp36_line_change_closes_period_and_is_inherited_by_both_ph5000_presses(client, admin_token):
    person, token = carga_token(client, admin_token, "Prensas")
    seed_press_configuration()
    first = client.post("/api/v1/lineas/L7/producto-formato", headers=auth(token), json={"linea": "L7", "producto": "Pasta A", "formato": "64x64", "desde": "2026-01-02T07:00:00Z"}).json()
    second = client.post("/api/v1/lineas/L7/producto-formato", headers=auth(token), json={"linea": "L7", "producto": "Pasta B", "formato": "64x64", "desde": "2026-01-02T08:00:00Z"}).json()
    with SessionLocal() as db:
        assert db.get(LineProductFormatPeriod, first["id"]).hasta == datetime.fromisoformat(second["desde"].replace("Z", "+00:00"))
    records = []
    for press in ("PH5000-1", "PH5000-2"):
        response = client.post("/api/v1/registros/m9", headers=auth(token), json={**base_payload(person["id"]), "datos": {"linea": "L7", "prensa": press, "formato": "64x64", "humedad_pasta": "7", "presion": "240", "humedad_residual": "1"}})
        assert response.status_code == 201
        records.append(response.json())
    assert {row["datos"]["producto_formato_linea"]["producto"] for row in records} == {"Pasta B"}


def test_cp37_shift_receipt_keeps_open_stoppage_continuous(client, admin_token):
    person, token = carga_token(client, admin_token)
    stop = client.post("/api/v1/registros/m6", headers=auth(token), json=operation_payload(person["id"], {"causa": "P01", "inicio": "2026-01-02T23:30:00Z"}, module="m6", when=datetime(2026, 1, 2, 23, 30, tzinfo=timezone.utc)))
    assert stop.status_code == 201
    assert client.post("/api/v1/turnos/2026-01-02/20-04/Molienda/recibir", headers=auth(token), json={"observacion": "Recibo parada abierta"}).status_code == 201
    assert client.get("/api/v1/registros/m6", headers=auth(admin_token)).json()[0]["datos"].get("fin") is None
    with SessionLocal() as db:
        assert db.scalar(select(ShiftReceipt).where(ShiftReceipt.sector == "Molienda")) is not None


def test_cp40_future_limit_can_change_and_cancel_with_audit(client, admin_token):
    start = date.today() + timedelta(days=10)
    assert client.post("/api/v1/limites", headers=auth(admin_token), json={"id": "CP40", "variable": "CP40", "etapa": "Prueba", "unidad": "%", "tipo_dato": "numero"}).status_code == 201
    created = client.post("/api/v1/limites/CP40/versiones", headers=auth(admin_token), json={"vigente_desde": start.isoformat(), "valor_max": "4", "operador_max": "<=", "nivel": "ADVERTENCIA", "motivo_cambio": "Programada"}).json()
    changed = client.patch(f"/api/v1/limites/CP40/versiones/{created['id']}", headers=auth(admin_token), json={"vigente_desde": (start + timedelta(days=1)).isoformat(), "valor_max": "5", "operador_max": "<=", "nivel": "ADVERTENCIA", "motivo_cambio": "Reprogramada"})
    assert changed.status_code == 200 and float(changed.json()["valor_max"]) == 5
    assert client.post(f"/api/v1/limites/CP40/versiones/{created['id']}/cancelar", headers=auth(admin_token)).json()["estado"] == "CANCELADA"
    audits = client.get("/api/v1/auditoria", headers=auth(admin_token)).json()
    assert {row["accion"] for row in audits if row["id_registro"] == created["id"]} >= {"ALTA", "MODIFICACION", "CANCELACION"}


def test_cp42_missing_lab_analysis_only_reduces_compliance(client, admin_token):
    seed_humidity_limit()
    point, numeric, _, _ = create_f7_configuration(client, admin_token)
    agenda = client.get(f"/api/v1/laboratorio/agenda?desde=2026-01-02T00:00:00Z&hasta=2026-01-03T00:00:00Z&id_punto={point['id']}", headers=auth(admin_token)).json()
    assert agenda["cumplimiento"]["esperados"] > 0 and agenda["cumplimiento"]["realizados"] == 0
    with SessionLocal() as db:
        assert db.query(LaboratoryAnalysis).count() == db.query(LaboratoryDeviationEvent).count() == 0
        assert numeric["id"]


def test_cp46_historic_preparer_without_user_remains_valid(client, admin_token):
    historic = client.post("/api/v1/personas", headers=auth(admin_token), json={"legajo": "CP46", "apellido_nombre": "Preparador historico"}).json()
    assert client.post("/api/v1/registros/m1", headers=auth(admin_token), json=m1_payload(historic["id"], date.today())).status_code == 201
    assert client.post("/api/v1/registros/m1", json=m1_payload(historic["id"], date.today())).status_code == 401
    assert not client.get("/api/v1/usuarios", headers=auth(admin_token)).json()[-1]["id_persona"] == historic["id"]


def test_cp47_new_silo_scale_does_not_rewrite_old_stock(client, admin_token):
    person, token = carga_token(client, admin_token)
    with SessionLocal() as db:
        admin_id = db.scalar(select(User.id).where(User.nombre_usuario == "admin.test"))
    old_scale = create_silo_scale(admin_id, date(2026, 1, 1), 1, "100")
    new_scale = create_silo_scale(admin_id, date(2027, 1, 1), 2, "200")
    old = client.post("/api/v1/registros/m3", headers=auth(token), json=operation_payload(person["id"], {"tipo_registro": "stock_silo", "silo": 1, "altura_libre_m": "9"}, module="m3", when=datetime(2026, 1, 2, 8, tzinfo=timezone.utc))).json()
    new = client.post("/api/v1/registros/m3", headers=auth(token), json=operation_payload(person["id"], {"tipo_registro": "stock_silo", "silo": 1, "altura_libre_m": "9"}, module="m3", when=datetime(2027, 1, 2, 8, tzinfo=timezone.utc))).json()
    assert old["datos"]["id_escala_version"] == old_scale and new["datos"]["id_escala_version"] == new_scale
    assert float(old["datos"]["toneladas_calculadas"]) == 10 and float(new["datos"]["toneladas_calculadas"]) == 20


def test_cp49_person_is_the_single_user_identity_source(client, admin_token):
    person, _ = create_carga(client, admin_token, "cp49.user", "Molienda")
    assert client.patch(f"/api/v1/personas/{person['id']}", headers=auth(admin_token), json={"legajo": "CP49-EDIT", "apellido_nombre": "Identidad editada"}).status_code == 200
    user = next(row for row in client.get("/api/v1/usuarios", headers=auth(admin_token)).json() if row["nombre_usuario"] == "cp49.user")
    assert set(user) == {"id", "id_persona", "nombre_usuario", "id_rol", "sector", "activo", "consulta_remota"}
    audit = next(row for row in client.get("/api/v1/auditoria", headers=auth(admin_token)).json() if row["tabla"] == "persona" and row["id_registro"] == person["id"] and row["accion"] == "MODIFICACION")
    assert audit["valor_nuevo"]["legajo"] == "CP49-EDIT"


def test_cp54_deactivated_catalog_is_hidden_retained_and_audited(client, admin_token):
    catalog = client.post("/api/v1/catalogos", headers=auth(admin_token), json={"tipo": "formato", "codigo": "CP54", "descripcion": "Formato historico", "atributos": {"espesor_nominal_mm": "7", "tolerancia_mm": "1"}}).json()
    person, token = carga_token(client, admin_token, "Prensas")
    record = client.post("/api/v1/registros/m9", headers=auth(token), json={**base_payload(person["id"]), "datos": {"linea": "L7", "prensa": "PH5000-1", "formato": "CP54", "humedad_pasta": "7", "presion": "240", "humedad_residual": "1"}}).json()
    assert client.patch(f"/api/v1/catalogos/{catalog['id']}", headers=auth(admin_token), json={"activo": False, "fecha_baja": "2026-01-03"}).status_code == 200
    assert client.get("/api/v1/catalogos/formato", headers=auth(admin_token)).json() == []
    assert client.get("/api/v1/registros/m9", headers=auth(admin_token)).json()[0]["datos"]["formato"] == record["datos"]["formato"]
    assert any(row["tabla"] == "catalogo" and row["id_registro"] == catalog["id"] and row["accion"] == "MODIFICACION" for row in client.get("/api/v1/auditoria", headers=auth(admin_token)).json())


def test_cp56_summary_and_controls_aggregate_one_shift_without_double_counting(client, admin_token):
    person, token = carga_token(client, admin_token)
    for hour in (8, 9, 10):
        assert client.post("/api/v1/registros/m1", headers=auth(token), json=operation_payload(person["id"], {"box_activo": 1, "humedad_verdes": "2.8", "residuo": "1", "aeroseparador": "80"}, when=datetime(2026, 1, 2, hour, tzinfo=timezone.utc))).status_code == 201
    summary = client.post("/api/v1/registros/m1", headers=auth(token), json=operation_payload(person["id"], {"tipo_registro": "resumen_turno", "toneladas_procesadas": "120", "horas_marcha": "7"}, when=datetime(2026, 1, 2, 11, tzinfo=timezone.utc)))
    assert summary.status_code == 201, summary.text
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    facts = client.get("/api/v1/kpi?desde=2026-01-02&hasta=2026-01-02&contexto=Molienda", headers=auth(admin_token)).json()["hechos"]
    assert len(facts) == 1 and facts[0]["metricas"]["toneladas_procesadas"] == 120 and facts[0]["metricas"]["horas_marcha"] == 7


def test_cp57_cross_midnight_stoppage_keeps_operational_date_duration_and_open_state(client, admin_token):
    person, token = carga_token(client, admin_token)
    created = client.post("/api/v1/registros/m6", headers=auth(token), json={"fecha_operativa": "2026-01-02", "turno_codigo": "20-04", "instante_medicion": "2026-01-02T23:30:00Z", "id_responsable": person["id"], "origen_dato": "digital_directo", "datos": {"causa": "P01", "inicio": "2026-01-02T23:30:00Z"}}).json()
    assert created["fecha_operativa"] == "2026-01-02" and "fin" not in created["datos"]
    closed = client.put(f"/api/v1/registros/m6/{created['id']}", headers=auth(token), json={"revision": created["revision"], "datos": {**created["datos"], "fin": "2026-01-03T01:15:00Z"}})
    assert closed.status_code == 200
    assert closed.json()["fecha_operativa"] == "2026-01-02" and float(closed.json()["datos"]["duracion_calculada_horas"]) == 1.75


def test_cp58_overlapping_stoppages_use_union_and_keep_pareto_events(client, admin_token):
    person, token = carga_token(client, admin_token)
    assert client.post("/api/v1/calendario", headers=auth(admin_token), json={"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "programado": True, "horas_programadas": "8"}).status_code == 201
    for cause, start, end in (("P01", "2026-01-02T08:00:00Z", "2026-01-02T11:00:00Z"), ("P02", "2026-01-02T09:00:00Z", "2026-01-02T12:00:00Z")):
        assert client.post("/api/v1/registros/m6", headers=auth(token), json=operation_payload(person["id"], {"causa": cause, "inicio": start, "fin": end}, module="m6")).status_code == 201
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    fact = client.get("/api/v1/kpi?contexto=Molienda", headers=auth(admin_token)).json()["hechos"][0]["metricas"]
    assert fact["indisponibilidad_horas"] == 4 and fact["disponibilidad"] == 0.5
    assert {row["causa"]: row["duracion_horas"] for row in client.get("/api/v1/kpi/pareto-paradas", headers=auth(admin_token)).json()["pareto"]} == {"P01": 3.0, "P02": 3.0}


def test_cp59_out_of_range_correction_updates_same_event_history(client, admin_token):
    person, token = carga_token(client, admin_token)
    seed_humidity_limit()
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=f1_m1_payload(person["id"], "4.1")).json()
    corrected = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json={"revision": created["revision"], "datos": {**created["datos"], "humedad_verdes": "4.2"}})
    assert corrected.status_code == 200
    with SessionLocal() as db:
        events = list(db.scalars(select(DeviationEvent).where(DeviationEvent.id_registro == created["id"])))
        assert len(events) == 1 and str(events[0].valor_actual) == "4.2000"


def test_cp63_generic_put_cannot_set_closed_state(client, admin_token):
    person, token = carga_token(client, admin_token)
    created = client.post("/api/v1/registros/m1", headers=auth(token), json=operation_payload(person["id"], {"box_activo": 1, "humedad_verdes": "2.8", "residuo": "1", "aeroseparador": "80"})).json()
    generic = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json={"revision": created["revision"], "estado": "CERRADO", "datos": created["datos"]})
    assert generic.status_code == 422
    corrected = client.put(f"/api/v1/registros/m1/{created['id']}", headers=auth(token), json={"revision": created["revision"], "datos": {**created["datos"], "humedad_verdes": "2.9"}})
    assert corrected.status_code == 200 and corrected.json()["estado"] == "BORRADOR"
    assert client.post(f"/api/v1/registros/m1/{created['id']}/cerrar", headers=auth(token), json={"comentario": "Cierre explicito"}).json()["estado"] == "CERRADO"


def test_cp65_dashboard_shows_overdue_escalated_invalidated_and_excludes_invalidated(client, admin_token):
    person, token = carga_token(client, admin_token)
    seed_humidity_limit()
    records = [client.post("/api/v1/registros/m1", headers=auth(token), json=f1_m1_payload(person["id"], humidity, hour)).json() for humidity, hour in (("4.1", 8), ("4.2", 9), ("4.3", 10))]
    assert client.put(f"/api/v1/registros/m1/{records[2]['id']}", headers=auth(token), json={"revision": records[2]["revision"], "datos": {**records[2]["datos"], "humedad_verdes": "2.8"}}).status_code == 200
    with SessionLocal.begin() as db:
        first = db.scalar(select(DeviationEvent).where(DeviationEvent.id_registro == records[0]["id"]))
        first.vence_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert {row["estado"] for row in client.get("/api/v1/desvios", headers=auth(admin_token)).json()} >= {"VENCIDO", "ESCALADO", "INVALIDADO"}
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    metrics = client.get("/api/v1/kpi?contexto=Molienda", headers=auth(admin_token)).json()["hechos"][0]["metricas"]
    assert set(metrics["desvios_por_estado"]) >= {"VENCIDO", "ESCALADO", "INVALIDADO"} and metrics["desvios_reales"] == 2


def test_cp66_m2_temporal_measurements_keep_grain_while_shift_aggregates(client, admin_token):
    person, token = carga_token(client, admin_token)
    for water, hour in (("7500", 8), ("6000", 9)):
        assert client.post("/api/v1/registros/m2", headers=auth(token), json=operation_payload(person["id"], {"caudal_pasta": "30", "caudal_agua": water, "humedad_salida": "5"}, module="m2", when=datetime(2026, 1, 2, hour, tzinfo=timezone.utc))).status_code == 201
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    with SessionLocal() as db:
        assert len(list(db.scalars(select(TemporalMeasurementFact).where(TemporalMeasurementFact.metrica == "dosificacion_calc")))) == 2
    assert client.get("/api/v1/kpi?contexto=Molienda", headers=auth(admin_token)).json()["hechos"][0]["metricas"]["dosificacion_calc"] == 225


def test_cp70_escalation_has_no_notification_outbox_or_webhook_infrastructure(client, admin_token):
    person, token = carga_token(client, admin_token)
    seed_humidity_limit()
    for humidity, hour in (("4.1", 8), ("4.2", 9), ("2.8", 10)):
        assert client.post("/api/v1/registros/m1", headers=auth(token), json=f1_m1_payload(person["id"], humidity, hour)).status_code == 201
    assert [row["estado"] for row in client.get("/api/v1/desvios", headers=auth(admin_token)).json()] == ["ESCALADO", "ABIERTO"]
    assert not any(term in " ".join(app.openapi()["paths"]).lower() for term in ("webhook", "notificacion", "notification"))
    assert not any(term in table.name for table in OperationalRecord.metadata.sorted_tables for term in ("outbox", "webhook", "notificacion", "notification"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in (Path(__file__).parents[1] / "app").rglob("*.py"))
    assert "webhook" not in source.lower() and "outbox" not in source.lower()
