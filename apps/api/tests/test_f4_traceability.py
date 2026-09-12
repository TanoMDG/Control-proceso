from app.db.session import SessionLocal
from datetime import date

from app.models.core import BoxVerdesPeriod, KsiderSiloPeriod, MuaBoxPresence, PersonPosition, User
from tests.conftest import auth
from tests.test_f1_operations import carga_token


def create_mua(client, token, preparer_id, day="2026-01-02"):
    return client.post("/api/v1/mua", headers=auth(token), json={"fecha_generacion": day, "id_preparador": preparer_id, "composicion": [{"componente": "Pasta recuperada", "referencia": "Lote A"}]})


def make_palero(person_id):
    with SessionLocal.begin() as db:
        db.add(PersonPosition(id_persona=person_id, puesto="Palero", vigente_desde=date(2020, 1, 1)))


def test_m4_identity_composition_and_m5_existing_mua_only(client, admin_token):
    with SessionLocal() as db:
        preparer_id = str(db.query(User).filter_by(nombre_usuario="admin.test").one().id_persona)
    make_palero(preparer_id)
    created = create_mua(client, admin_token, preparer_id)
    assert created.status_code == 201
    mua = created.json()
    assert mua["codigo"] == "MUA-2026-0102-01"
    assert mua["composicion"] == [{"componente": "Pasta recuperada", "referencia": "Lote A"}]
    missing = client.post("/api/v1/trazabilidad/mua-box", headers=auth(admin_token), json={"id_mua": "00000000-0000-0000-0000-000000000001", "box": "1", "desde": "2026-01-02T08:00:00Z"})
    assert missing.status_code == 422
    assert client.post("/api/v1/trazabilidad/mua-box", headers=auth(admin_token), json={"id_mua": mua["id"], "box": "1", "desde": "2026-01-02T08:00:00Z"}).status_code == 201
    listed = client.get("/api/v1/mua", headers=auth(admin_token))
    assert listed.status_code == 200
    assert listed.json()[0]["presencias_activas"][0]["box"] == "1"
    assert listed.json()[0]["orden_fifo"] == 1


def test_mua_creation_requires_supervision_and_boxes_can_hold_two_muas(client, admin_token):
    person, carga = carga_token(client, admin_token, "Molienda")
    assert create_mua(client, carga, person["id"]).status_code == 403
    assert create_mua(client, admin_token, person["id"]).status_code == 422
    make_palero(person["id"])
    first, second = create_mua(client, admin_token, person["id"]).json(), create_mua(client, admin_token, person["id"]).json()
    for mua in (first, second):
        assert client.post("/api/v1/trazabilidad/mua-box", headers=auth(carga), json={"id_mua": mua["id"], "box": "2", "desde": "2026-01-02T08:00:00Z"}).status_code == 201
    with SessionLocal() as db:
        assert db.query(MuaBoxPresence).filter_by(box="2", hasta=None).count() == 2


def test_temporal_handoffs_mapping_and_certainty_trace(client, admin_token):
    with SessionLocal() as db:
        preparer_id = str(db.query(User).filter_by(nombre_usuario="admin.test").one().id_persona)
    make_palero(preparer_id)
    mua = create_mua(client, admin_token, preparer_id).json()
    assert client.post("/api/v1/trazabilidad/mua-box", headers=auth(admin_token), json={"id_mua": mua["id"], "box": "1", "desde": "2026-01-02T08:00:00Z"}).status_code == 201
    assert client.post("/api/v1/trazabilidad/box-verdes", headers=auth(admin_token), json={"box": "1", "desde": "2026-01-02T08:10:00Z"}).status_code == 201
    assert client.post("/api/v1/trazabilidad/box-verdes", headers=auth(admin_token), json={"box": "2", "desde": "2026-01-02T09:00:00Z"}).status_code == 201
    assert client.post("/api/v1/trazabilidad/ksider-silo", headers=auth(admin_token), json={"silo": 1, "desde": "2026-01-02T08:20:00Z"}).status_code == 201
    assert client.post("/api/v1/trazabilidad/ksider-silo", headers=auth(admin_token), json={"silo": 2, "desde": "2026-01-02T09:10:00Z"}).status_code == 201
    assert client.post("/api/v1/trazabilidad/silo-linea", headers=auth(admin_token), json={"silo": 1, "linea": "L6", "desde": "2026-01-02T08:20:00Z"}).status_code == 422
    assert client.post("/api/v1/trazabilidad/silo-linea", headers=auth(admin_token), json={"silo": 1, "linea": "L7", "desde": "2026-01-02T08:20:00Z"}).status_code == 201
    assert client.post("/api/v1/lineas/L7/producto-formato", headers=auth(admin_token), json={"linea": "L7", "producto": "Producto A", "formato": "64x64", "desde": "2026-01-02T08:25:00Z"}).status_code == 201
    trace = client.get(f"/api/v1/mua/{mua['id']}/trazabilidad", headers=auth(admin_token))
    assert trace.status_code == 200 and trace.json()["sin_proporciones_inventadas"] is True
    assert {edge["certeza"] for edge in trace.json()["aristas"]} >= {"CONFIRMADA", "POTENCIAL", "INFERIDA"}
    with SessionLocal() as db:
        assert db.query(BoxVerdesPeriod).filter(BoxVerdesPeriod.hasta.isnot(None)).count() == 1
        assert db.query(KsiderSiloPeriod).filter(KsiderSiloPeriod.hasta.isnot(None)).count() == 1
