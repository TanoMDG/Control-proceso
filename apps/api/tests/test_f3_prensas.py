from datetime import date, datetime, timezone

from app.db.session import SessionLocal
from app.models.core import AppliedLimit, Catalog, DeviationEvent, Limit, LimitVersion, ReactionPlan, User
from tests.conftest import auth
from tests.test_f1_operations import carga_token


def seed_press_configuration():
    with SessionLocal.begin() as db:
        admin = db.query(User).filter_by(nombre_usuario="admin.test").one()
        db.add_all([
            Catalog(tipo="prensa", codigo="PH Siti", descripcion="PH Siti", atributos={"linea": "L6"}, activo=True, fecha_baja=None),
            Catalog(tipo="prensa", codigo="PH5000-1", descripcion="PH5000-1", atributos={"linea": "L7"}, activo=True, fecha_baja=None),
            Catalog(tipo="prensa", codigo="PH5000-2", descripcion="PH5000-2", atributos={"linea": "L7"}, activo=True, fecha_baja=None),
            Catalog(tipo="formato", codigo="64x64", descripcion="64x64", atributos={"espesor_nominal_mm": "7.10", "tolerancia_mm": "0.15"}, activo=True, fecha_baja=None),
            Catalog(tipo="formato", codigo="64x122", descripcion="64x122", atributos={"espesor_nominal_mm": "7.50", "tolerancia_mm": "0.15"}, activo=True, fecha_baja=None),
            ReactionPlan(id_desvio="D19", senal="Presion", etapa="Prensas", limite_referencia="L32", causas_probables="Prueba", accion_inmediata="Ajustar", verificacion="Medir", plazo_texto="1 h", registro_escalamiento="Escalar", tipo_plazo="HORAS"),
            Limit(id="L32", variable="Presion", etapa="Prensas", unidad="kg/cm2", tipo_dato="numero"),
            Limit(id="L33", variable="Espesor 64x64", etapa="Prensas", unidad="mm", tipo_dato="numero"),
            Limit(id="L34", variable="Espesor 64x122", etapa="Prensas", unidad="mm", tipo_dato="numero"),
            Limit(id="L42", variable="Dispersion", etapa="Prensas", unidad="mm", tipo_dato="numero"),
            Limit(id="L43", variable="Dispersion", etapa="Prensas", unidad="mm", tipo_dato="numero"),
            Limit(id="L44", variable="Dispersion", etapa="Prensas", unidad="mm", tipo_dato="numero"),
        ])
        db.add_all([
            LimitVersion(id_limite="L32", vigente_desde=date(2020, 1, 1), valor_min="210", valor_max="270", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", id_desvio="D19", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"),
            LimitVersion(id_limite="L33", vigente_desde=date(2020, 1, 1), valor_min="6.95", valor_max="7.25", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"),
            LimitVersion(id_limite="L34", vigente_desde=date(2020, 1, 1), valor_min="7.35", valor_max="7.65", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"),
            # L42 has no Dxx: it is a visible warning and must not manufacture an event.
            LimitVersion(id_limite="L42", vigente_desde=date(2020, 1, 1), valor_min="0", valor_max="0.30", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"),
            LimitVersion(id_limite="L43", vigente_desde=date(2020, 1, 1), valor_min="0", valor_max="0.30", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"),
            LimitVersion(id_limite="L44", vigente_desde=date(2020, 1, 1), valor_min="0", valor_max="0.30", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", motivo_cambio="Prueba", id_usuario_alta=admin.id, estado="VIGENTE"),
        ])


def thickness_details(line: str, value: str = "7.10", outlier: str | None = None):
    presses = ["PH Siti"] if line == "L6" else ["PH5000-1", "PH5000-2"]
    details = [{"prensa": press, "cavidad": cavity, "sector": sector, "espesor_mm": value} for press in presses for cavity in (1, 2) for sector in range(1, 10)]
    if outlier:
        details[0]["espesor_mm"] = outlier
    return details


def base_payload(person_id):
    return {"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_medicion": datetime(2026, 1, 2, 8, tzinfo=timezone.utc).isoformat(), "id_responsable": person_id, "origen_dato": "digital_directo"}


def test_m8_m9_validate_press_line_and_pressure_deviation(client, admin_token):
    person, token = carga_token(client, admin_token, "Prensas")
    seed_press_configuration()
    base = base_payload(person["id"])
    valid = client.post("/api/v1/registros/m8", headers=auth(token), json={**base, "datos": {"linea": "L7", "prensa": "PH5000-1", "causa_vaciado": "Tolva", "duracion_min": "10"}})
    assert valid.status_code == 201
    assert valid.json()["datos"]["recordatorio_descarte_min"] == "10"
    invalid = client.post("/api/v1/registros/m8", headers=auth(token), json={**base, "datos": {"linea": "L7", "prensa": "PH Siti", "causa_vaciado": "Tolva", "duracion_min": "10"}})
    assert invalid.status_code == 422
    pressed = client.post("/api/v1/registros/m9", headers=auth(token), json={**base, "datos": {"linea": "L7", "prensa": "PH5000-1", "formato": "64x64", "humedad_pasta": "7.8", "presion": "200", "humedad_residual": "0.5"}})
    assert pressed.status_code == 201
    assert pressed.json()["datos"]["formato_aplicado"] == {"codigo": "64x64", "espesor_nominal_mm": "7.10", "tolerancia_mm": "0.15"}
    with SessionLocal() as db:
        assert db.query(DeviationEvent).filter_by(id_desvio="D19").count() == 1


def test_m10_requires_full_grids_uses_format_tolerance_and_does_not_invent_dispersion_event(client, admin_token):
    person, token = carga_token(client, admin_token, "Prensas")
    seed_press_configuration()
    base = base_payload(person["id"])
    incomplete = client.post("/api/v1/registros/m10", headers=auth(token), json={**base, "datos": {"linea": "L7", "formato": "64x64", "detalles": thickness_details("L7")[:-1]}})
    assert incomplete.status_code == 422
    response = client.post("/api/v1/registros/m10", headers=auth(token), json={**base, "datos": {"linea": "L7", "formato": "64x64", "detalles": thickness_details("L7", outlier="7.45")}})
    assert response.status_code == 201
    result = response.json()["datos"]
    assert result["espesor_min"] == "7.10" and result["espesor_max"] == "7.45" and result["dispersion_mm"] == "0.35"
    assert result["advertencia_espesor"] is True and result["advertencia_dispersion"] is True
    assert result["limites_dispersion_advertidos"] == ["L42", "L43", "L44"]
    with SessionLocal() as db:
        assert db.query(DeviationEvent).count() == 0
        assert db.query(AppliedLimit).filter(AppliedLimit.campo.in_(["dispersion_mm:L42", "dispersion_mm:L43", "dispersion_mm:L44"])).count() == 3
    different_format = client.post("/api/v1/registros/m10", headers=auth(token), json={**base, "datos": {"linea": "L6", "formato": "64x122", "detalles": thickness_details("L6", value="7.45")}})
    assert different_format.status_code == 201
    assert different_format.json()["datos"]["advertencia_espesor"] is False


def test_f3_records_rebuild_press_facts(client, admin_token):
    person, token = carga_token(client, admin_token, "Prensas")
    seed_press_configuration()
    base = base_payload(person["id"])
    assert client.post("/api/v1/registros/m8", headers=auth(token), json={**base, "datos": {"linea": "L7", "prensa": "PH5000-1", "causa_vaciado": "Tolva", "duracion_min": "10"}}).status_code == 201
    assert client.post("/api/v1/registros/m9", headers=auth(token), json={**base, "datos": {"linea": "L7", "prensa": "PH5000-1", "formato": "64x64", "humedad_pasta": "7.8", "presion": "240", "humedad_residual": "0.5"}}).status_code == 201
    assert client.post("/api/v1/registros/m10", headers=auth(token), json={**base, "datos": {"linea": "L7", "formato": "64x64", "detalles": thickness_details("L7")}}).status_code == 201
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token)).status_code == 200
    facts = client.get("/api/v1/kpi?linea=L7", headers=auth(admin_token)).json()["hechos"]
    assert facts[0]["metricas"]["vaciados_tolva"] == 1.0
    assert facts[0]["metricas"]["presion"] == 240.0
    assert facts[0]["metricas"]["controles_espesor"] == 1.0
    assert facts[0]["metricas"]["espesor_mm"] == 7.1
