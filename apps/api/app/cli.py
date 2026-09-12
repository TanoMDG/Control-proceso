import argparse
from pathlib import Path

from app.db.session import SessionLocal
from app.services.bootstrap import bootstrap_admin
from app.services.importer import ensure_development_import_admin, import_master_data, validate_excel_source
from app.services.analytics import rebuild_analytics


def main() -> None:
    parser = argparse.ArgumentParser(prog="control-procesos")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("bootstrap-admin", help="Crea el primer ADMIN con datos provistos por el despliegue")
    admin.add_argument("--legajo", required=True)
    admin.add_argument("--nombre", required=True)
    admin.add_argument("--usuario", required=True)
    admin.add_argument("--password", required=True)
    admin.add_argument("--sector", default="Administracion")
    preview = commands.add_parser("import-preview", help="Valida el libro fuente sin escribir datos")
    preview.add_argument("archivo", type=Path)
    apply_import = commands.add_parser("import-apply-development", help="Importa datos maestros en desarrollo con la cuenta ADMIN técnica autorizada")
    apply_import.add_argument("archivo", type=Path)
    apply_import.add_argument("--password", required=True)
    commands.add_parser("recalculate-analytics", help="Reconstruye los hechos analiticos desde registros operativos")
    args = parser.parse_args()
    if args.command == "import-preview":
        print(validate_excel_source(args.archivo))
        return
    with SessionLocal.begin() as db:
        if args.command == "recalculate-analytics":
            run = rebuild_analytics(db)
            print(f"Recalculo completado: {run.id}")
            return
        if args.command == "import-apply-development":
            actor = ensure_development_import_admin(db, password=args.password)
            print(import_master_data(db, path=args.archivo, actor=actor))
            return
        user = bootstrap_admin(db, legajo=args.legajo, nombre=args.nombre, username=args.usuario, password=args.password, sector=args.sector)
        print(f"ADMIN creado: {user.nombre_usuario} ({user.id})")


if __name__ == "__main__":
    main()
