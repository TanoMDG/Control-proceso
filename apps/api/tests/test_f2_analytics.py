from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.core import ProductionCalendar, User
from tests.conftest import auth


def test_rebuilds_facts_and_serves_kpi_without_operational_queries(client, admin_token):
    headers = auth(admin_token)
    with SessionLocal.begin() as db:
        db.add(ProductionCalendar(fecha_operativa=datetime(2026, 1, 2).date(), turno_codigo="08-16", programado=True, horas_programadas="8", motivo="Prueba"))
        person_id = db.query(User).filter_by(nombre_usuario="admin.test").one().id_persona
    base = {"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_medicion": datetime(2026, 1, 2, 8, tzinfo=timezone.utc).isoformat(), "id_responsable": str(person_id), "origen_dato": "digital_directo"}
    assert client.post("/api/v1/registros/m2", headers=headers, json={**base, "datos": {"caudal_pasta": "30", "caudal_agua": "7500", "humedad_salida": "13"}}).status_code == 201
    assert client.post("/api/v1/registros/m6", headers=headers, json={**base, "datos": {"causa": "P01", "inicio": "2026-01-02T08:00:00+00:00", "fin": "2026-01-02T10:00:00+00:00"}}).status_code == 201
    rebuilt = client.post("/api/v1/analitica/recalcular", headers=headers)
    assert rebuilt.status_code == 200 and rebuilt.json()["estado"] == "COMPLETADO"
    kpi = client.get("/api/v1/kpi", headers=headers).json()
    fact = kpi["hechos"][0]["metricas"]
    assert kpi["ultimo_recalculo"] is not None
    assert fact["dosificacion_calc"] == 250
    assert fact["disponibilidad"] == 0.75
    assert client.get("/api/v1/kpi/pareto-paradas", headers=headers).json()["pareto"] == [{"causa": "P01", "duracion_horas": 2.0}]
