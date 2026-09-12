from datetime import date, datetime, timezone

from app.db.session import SessionLocal
from app.models.core import DeviationEvent, MaintenanceRecord, PersonPosition, User
from tests.conftest import auth
from tests.test_f1_operations import carga_token, m1_payload, seed_humidity_limit


PENDING_MESSAGE = "Pendiente de configuracion: no hay responsables de mantenimiento configurados."


def add_maintenance_position(person_id):
    with SessionLocal.begin() as db:
        db.add(PersonPosition(id_persona=person_id, puesto="Mantenimiento", vigente_desde=date(2020, 1, 1)))


def create_masters(client, token):
    equipment = client.post("/api/v1/mantenimiento/equipos", headers=auth(token), json={"codigo": "EQ-01", "descripcion": "Madirex 1", "sector": "Molienda", "atributos": {"linea": "L7"}})
    product = client.post("/api/v1/mantenimiento/productos", headers=auth(token), json={"codigo": "PR-01", "descripcion": "Pasta 64"})
    format_item = client.post("/api/v1/catalogos", headers=auth(token), json={"tipo": "formato", "codigo": "64X64", "descripcion": "64 x 64"})
    assert equipment.status_code == product.status_code == format_item.status_code == 201
    relation = client.post(f"/api/v1/mantenimiento/productos/{product.json()['id']}/formatos", headers=auth(token), json={"id_formato": format_item.json()["id"], "vigente_desde": "2020-01-01", "motivo_cambio": "Alta inicial"})
    assert relation.status_code == 201, relation.text
    return equipment.json(), product.json(), format_item.json(), relation.json()


def test_m7_filters_responsibles_and_exposes_pending_configuration(client, admin_token):
    empty = client.get("/api/v1/mantenimiento/responsables", headers=auth(admin_token))
    assert empty.status_code == 200
    assert empty.json() == {"responsables": [], "mensaje_configuracion": PENDING_MESSAGE}
    with SessionLocal() as db:
        person_id = str(db.query(User).filter_by(nombre_usuario="admin.test").one().id_persona)
    add_maintenance_position(person_id)
    configured = client.get("/api/v1/mantenimiento/responsables?fecha=2026-01-02", headers=auth(admin_token))
    assert configured.json()["mensaje_configuracion"] is None
    assert configured.json()["responsables"][0]["id"] == person_id


def test_m7_record_versions_masters_and_correlates_stop_and_deviation(client, admin_token):
    with SessionLocal() as db:
        responsible_id = str(db.query(User).filter_by(nombre_usuario="admin.test").one().id_persona)
    add_maintenance_position(responsible_id)
    equipment, product, format_item, relation = create_masters(client, admin_token)
    assert client.post(f"/api/v1/mantenimiento/productos/{product['id']}/formatos", headers=auth(admin_token), json={"id_formato": format_item["id"], "vigente_desde": "2020-06-01", "motivo_cambio": "Solapa"}).status_code == 422
    operator, carga = carga_token(client, admin_token)
    stop = client.post("/api/v1/registros/m6", headers=auth(carga), json={"fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "instante_medicion": "2026-01-02T08:00:00Z", "id_responsable": operator["id"], "origen_dato": "digital_directo", "datos": {"causa": "P01", "inicio": "2026-01-02T08:00:00Z", "fin": "2026-01-02T09:00:00Z"}})
    seed_humidity_limit()
    assert client.post("/api/v1/registros/m1", headers=auth(carga), json=m1_payload(operator["id"], "4.1")).status_code == 201
    with SessionLocal() as db:
        deviation_id = str(db.query(DeviationEvent).one().id)
    payload = {"client_uuid": "10000000-0000-0000-0000-000000000001", "fecha_operativa": "2026-01-02", "turno_codigo": "08-16", "inicio": "2026-01-02T08:10:00Z", "fin": "2026-01-02T09:10:00Z", "id_equipo": equipment["id"], "id_responsable": responsible_id, "tipo": "CORRECTIVO", "descripcion": "Cambio de rodamiento", "id_producto_formato_version": relation["id"], "campos_madirex": {"presion": "7.5", "observacion": "Solo informativo"}, "ids_paradas": [stop.json()["id"]], "ids_desvios": [deviation_id]}
    created = client.post("/api/v1/registros/m7", headers=auth(admin_token), json=payload)
    assert created.status_code == 201, created.text
    assert {row["tipo_referencia"] for row in created.json()["correlaciones"]} == {"PARADA", "DESVIO"}
    assert client.post("/api/v1/mantenimiento/registros", headers=auth(admin_token), json=payload).json()["id"] == created.json()["id"]
    assert client.get("/api/v1/registros/m7", headers=auth(admin_token)).json()[0]["id"] == created.json()["id"]
    with SessionLocal() as db:
        assert db.query(MaintenanceRecord).one().campos_madirex["presion"] == "7.5"
    assert client.post("/api/v1/analitica/recalcular", headers=auth(admin_token), json={}).status_code == 200
    facts = client.get("/api/v1/kpi?contexto=Mantenimiento", headers=auth(admin_token)).json()["hechos"]
    assert facts[0]["metricas"]["intervenciones_mantenimiento"] == 1.0
    assert facts[0]["metricas"]["correlaciones_mantenimiento"] == {"PARADA": 1, "DESVIO": 1}
