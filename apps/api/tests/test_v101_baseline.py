"""Regression coverage for the source-backed v1.0.1 baseline migration."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.api import get_baseline_configuration
from app.db.session import SessionLocal
from app.models.core import AuditLog, BaselineConfiguration, BaselineReconciliation, Catalog, LaboratoryFrequency, Limit, Person, ReactionPlan, User
from app.services.bootstrap import bootstrap_admin


API_ROOT = Path(__file__).parents[1]
MIGRATION_PATH = API_ROOT / "alembic" / "versions" / "0013_v101_baseline.py"


def migration_module():
    spec = spec_from_file_location("v101_baseline", MIGRATION_PATH)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def apply_from_v100() -> None:
    config = alembic_config()
    command.downgrade(config, "0012_cp_acceptance_guards")
    command.upgrade(config, "head")


def baseline_counts() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "limits": db.scalar(select(func.count()).select_from(Limit)) or 0,
            "reactions": db.scalar(select(func.count()).select_from(ReactionPlan)) or 0,
            "people": db.scalar(select(func.count()).select_from(Person).where(Person.legajo.like("000%"))) or 0,
            "frequencies": db.scalar(select(func.count()).select_from(LaboratoryFrequency)) or 0,
            "baseline": db.scalar(select(func.count()).select_from(BaselineConfiguration)) or 0,
            "reconciliation": db.scalar(select(func.count()).select_from(BaselineReconciliation)) or 0,
        }


def reconciliation_report() -> dict:
    with SessionLocal() as db:
        row = db.scalar(select(BaselineReconciliation))
        assert row is not None
        return row.reporte


def test_v101_baseline_fresh_database_has_source_counts():
    apply_from_v100()
    assert baseline_counts() == {"limits": 44, "reactions": 23, "people": 35, "frequencies": 28, "baseline": 1, "reconciliation": 1}
    entities = reconciliation_report()["entidades"]
    for entity in entities.values():
        assert set(entity) == {"expected", "inserted", "already_existing", "updated", "omitted", "pending", "conflicts"}
        assert entity["updated"] == entity["already_existing"] == entity["conflicts"] == 0
    assert entities["catalogos"] == {"expected": 68, "inserted": 68, "already_existing": 0, "updated": 0, "omitted": 0, "pending": 0, "conflicts": 0}
    assert entities["personas"] == {"expected": 35, "inserted": 35, "already_existing": 0, "updated": 0, "omitted": 0, "pending": 0, "conflicts": 0}
    assert entities["limites"]["expected"] == entities["limites"]["inserted"] == 44
    assert entities["planes_reaccion"]["expected"] == entities["planes_reaccion"]["inserted"] == 23
    assert entities["frecuencias_laboratorio"]["expected"] == entities["frecuencias_laboratorio"]["inserted"] == 28
    assert entities["responsables_mantenimiento"]["pending"] == 1
    assert entities["productos_formato"]["pending"] == 1


def test_v101_baseline_is_idempotent_after_upgrade():
    apply_from_v100()
    before = baseline_counts()
    command.upgrade(alembic_config(), "head")
    assert baseline_counts() == before


def test_v101_baseline_v100_upgrade_does_not_overwrite_existing_master():
    config = alembic_config()
    command.downgrade(config, "0012_cp_acceptance_guards")
    with SessionLocal.begin() as db:
        db.add(Catalog(tipo="formato", codigo="64x64", descripcion="Formato conservado", atributos={"origen": "v1.0.0"}, activo=True, fecha_baja=None))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        preserved = db.scalar(select(Catalog).where(Catalog.tipo == "formato", Catalog.codigo == "64x64"))
        assert preserved is not None
        assert preserved.descripcion == "Formato conservado"
        assert preserved.atributos == {"origen": "v1.0.0"}
    catalogos = reconciliation_report()["entidades"]["catalogos"]
    assert catalogos == {"expected": 68, "inserted": 67, "already_existing": 0, "updated": 0, "omitted": 0, "pending": 0, "conflicts": 1}


def test_v101_baseline_names_and_provenance_are_source_backed():
    apply_from_v100()
    migration = migration_module()
    assert len(migration.LIMITS) == 44
    assert len(migration.REACTIONS) == 23
    assert {item[0] for item in migration.LIMITS} == {f"L{number:02d}" for number in range(1, 45)}
    assert {item[0] for item in migration.REACTIONS} == {f"D{number:02d}" for number in range(1, 24)}
    assert not any("mantenimiento" in jobs for *_, jobs in migration.PEOPLE)
    with SessionLocal.begin() as db:
        actor = bootstrap_admin(db, legajo="BASELINE-ADMIN", nombre="Admin Baseline", username="baseline.admin", password="Clave-baseline-123", sector="Administracion")
    with SessionLocal() as db:
        payload = get_baseline_configuration(db.get(User, actor.id), db)
    assert payload["baseline"]["sha256_docx"] == migration.DOCX_SHA256
    assert payload["baseline"]["sha256_xlsx"] == migration.XLSX_SHA256
    assert payload["reconciliacion"]["estado"] == "PENDIENTES"
    assert "D01/D02" in payload["reconciliacion"]["reporte"]["limitacion_modelo"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.accion == "BASELINE_V101")) == 1
