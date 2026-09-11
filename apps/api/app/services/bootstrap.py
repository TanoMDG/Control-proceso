from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Permission, Person, Role, User
from app.services.security import hash_password

BASE_PERMISSIONS = {
    "CARGA": [("M11", "ver", "propio_sector"), ("M12", "ver", "propio_sector")],
    "SUPERVISION": [("M11", "ver", "todo"), ("M12", "ver", "todo"), ("M15", "ver", "todo")],
    "ADMIN": [
        ("M11", "ver", "todo"), ("M11", "crear", "todo"), ("M11", "editar", "todo"),
        ("M12", "ver", "todo"), ("M12", "crear", "todo"), ("M12", "editar", "todo"),
        ("M15", "ver", "todo"), ("M15", "crear", "todo"), ("M15", "editar", "todo"),
    ],
}


def ensure_base_roles(db: Session) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name in BASE_PERMISSIONS:
        role = db.scalar(select(Role).where(Role.nombre == name))
        if role is None:
            role = Role(nombre=name, descripcion=f"Rol operativo {name}")
            db.add(role)
            db.flush()
        roles[name] = role
        for module, action, scope in BASE_PERMISSIONS[name]:
            exists = db.scalar(select(Permission).where(Permission.id_rol == role.id, Permission.modulo == module, Permission.accion == action, Permission.alcance == scope))
            if exists is None:
                db.add(Permission(id_rol=role.id, modulo=module, accion=action, alcance=scope))
    db.flush()
    return roles


def bootstrap_admin(db: Session, *, legajo: str, nombre: str, username: str, password: str, sector: str) -> User:
    roles = ensure_base_roles(db)
    if db.scalar(select(User).where(User.nombre_usuario == username)) is not None:
        raise ValueError("El nombre de usuario ya existe")
    if db.scalar(select(Person).where(Person.legajo == legajo)) is not None:
        raise ValueError("El legajo ya existe")
    person = Person(legajo=legajo, apellido_nombre=nombre, activo=True, fecha_baja=None)
    db.add(person)
    db.flush()
    user = User(id_persona=person.id, nombre_usuario=username, password_hash=hash_password(password), id_rol=roles["ADMIN"].id, sector=sector)
    db.add(user)
    db.flush()
    return user
