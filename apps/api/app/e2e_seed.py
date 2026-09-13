"""Synthetic fixtures for the disposable Compose E2E database only."""

from datetime import date, datetime, timezone

from sqlalchemy import select, text

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.core import Catalog, LaboratoryDetermination, LaboratoryFrequency, LaboratoryPointDetermination, LaboratorySamplePoint, LaboratoryUnit, Limit, LimitVersion, MaintenanceEquipment, Person, PersonPosition, ReactionPlan, User
from app.services.bootstrap import ensure_base_roles
from app.services.security import hash_password


PASSWORD = "e2e-test-password"


def reset(db) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def add_user(db, roles, username: str, role: str, sector: str, position: str | None = None, remote: bool = False) -> Person:
    person = Person(legajo=f"E2E-{username.removeprefix('e2e-').upper()}", apellido_nombre=f"E2E {username}", activo=True, fecha_baja=None)
    db.add(person)
    db.flush()
    if position:
        db.add(PersonPosition(id_persona=person.id, puesto=position, vigente_desde=date(2020, 1, 1)))
    db.add(User(id_persona=person.id, nombre_usuario=username, password_hash=hash_password(PASSWORD), id_rol=roles[role].id, sector=sector, consulta_remota=remote))
    return person


def seed() -> None:
    if settings.app_env != "test":
        raise RuntimeError("La semilla E2E solo puede ejecutarse con APP_ENV=test")
    with SessionLocal.begin() as db:
        reset(db)
        roles = ensure_base_roles(db)
        add_user(db, roles, "e2e-admin", "ADMIN", "Administracion")
        add_user(db, roles, "e2e-supervision", "SUPERVISION", "Molienda")
        add_user(db, roles, "e2e-molienda", "CARGA", "Molienda", "Palero")
        add_user(db, roles, "e2e-prensas", "CARGA", "Prensas")
        add_user(db, roles, "e2e-laboratorio", "CARGA", "Laboratorio")
        maintenance_person = add_user(db, roles, "e2e-mantenimiento", "CARGA", "Mantenimiento", "Mantenimiento")
        add_user(db, roles, "e2e-remoto", "CARGA", "Remoto", remote=True)

        db.add(Catalog(tipo="formato", codigo="E2E-64X64", descripcion="Formato sintetico E2E", atributos={"espesor_nominal_mm": "7.10", "tolerancia_mm": "0.15"}, activo=True, fecha_baja=None))
        db.add(MaintenanceEquipment(codigo="E2E-EQ-01", descripcion="Equipo sintetico E2E", sector="Mantenimiento", atributos={}, activo=True, fecha_baja=None))
        admin = db.scalar(select(User).where(User.nombre_usuario == "e2e-admin"))
        assert admin is not None
        db.add(ReactionPlan(id_desvio="D01", senal="Humedad", etapa="Molienda", limite_referencia="L02", causas_probables="Fixture E2E", accion_inmediata="Ajustar", verificacion="Medir", plazo_texto="1 h", registro_escalamiento="Escalar", tipo_plazo="HORAS"))
        db.add(Limit(id="L02", variable="Humedad Verdes", etapa="Molienda", unidad="%", tipo_dato="numero", modulo_destino="M1", campo_destino="humedad_verdes"))
        db.add(LimitVersion(id_limite="L02", vigente_desde=date(2020, 1, 1), valor_min="2", valor_max="3.5", operador_min=">=", operador_max="<=", nivel="ADVERTENCIA", id_desvio="D01", motivo_cambio="Fixture E2E", id_usuario_alta=admin.id, estado="VIGENTE"))

        unit = LaboratoryUnit(codigo="pct", descripcion="Porcentaje sintetico", activo=True)
        point = LaboratorySamplePoint(codigo="E2E-PUNTO", descripcion="Punto sintetico", sector="Laboratorio", activo=True)
        determination = LaboratoryDetermination(codigo="E2E-HUM", descripcion="Humedad sintetica", tipo_resultado="NUMERICO", activo=True)
        db.add_all([unit, point, determination])
        db.flush()
        configuration = LaboratoryPointDetermination(id_punto=point.id, id_determinacion=determination.id, id_unidad=unit.id, vigente_desde=date(2020, 1, 1), activo=True)
        db.add(configuration)
        db.flush()
        db.add(LaboratoryFrequency(id_configuracion=configuration.id, vigente_desde=datetime(2020, 1, 1, tzinfo=timezone.utc), intervalo_horas=8, activo=True))
        # Keep the maintenance person referenced in the fixture graph for readability.
        assert maintenance_person.activo


if __name__ == "__main__":
    seed()
