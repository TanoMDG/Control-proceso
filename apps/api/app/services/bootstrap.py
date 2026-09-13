from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Permission, Person, Role, User
from app.services.security import hash_password

BASE_PERMISSIONS = {
    "CARGA": [
        ("M0", action, "propio_sector") for action in ("ver", "crear", "editar", "cerrar", "tratar", "verificar")
    ] + [
        (module, action, "propio_sector")
        for module, actions in {
            "M2": ("ver",), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"),
            "M11": ("ver",), "M12": ("ver",), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"),
        }.items()
        for action in actions
    ],
    "SUPERVISION": [
        (module, action, "todo")
        for module, actions in {
            "M0": ("ver", "crear", "editar", "cerrar", "validar", "anular", "tratar", "verificar"),
            "M2": ("ver", "recalcular"), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"),
            "M11": ("ver",), "M12": ("ver",), "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"),
            "M14": ("ver",), "M15": ("ver",),
        }.items()
        for action in actions
    ],
    "ADMIN": [
        (module, action, "todo")
        for module, actions in {
            "M0": ("ver", "crear", "editar", "cerrar", "validar", "anular", "tratar", "verificar"),
            "M2": ("ver", "recalcular"), "M4": ("ver", "crear", "editar"), "M7": ("ver", "crear", "editar"),
            "M11": ("ver", "crear", "editar"), "M12": ("ver", "crear", "editar"),
            "M13": ("ver", "crear", "editar", "cerrar", "tratar", "verificar"), "M14": ("ver", "crear", "editar"),
            "M15": ("ver", "crear", "editar", "administrar"),
        }.items()
        for action in actions
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
