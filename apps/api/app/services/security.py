from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.core import Permission, Role, User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def permission_for_request(request: Request) -> tuple[str, str] | None:
    path, method = request.url.path, request.method
    action = {"GET": "ver", "POST": "crear", "PUT": "editar", "PATCH": "editar"}.get(method)
    if action is None:
        return None
    if path.startswith("/api/v1/registros/m7") or path.startswith("/api/v1/mantenimiento"):
        return "M7", action
    if path.startswith("/api/v1/registros") or path.startswith("/api/v1/desvios") or path.startswith("/api/v1/turnos") or path == "/api/v1/exportar":
        if path.endswith("/validar"):
            action = "validar"
        elif path.endswith("/anular"):
            action = "anular"
        elif path.endswith("/cerrar"):
            action = "cerrar"
        elif "/desvios/" in path:
            action = path.rsplit("/", 1)[-1]
        return "M0", action
    if path.startswith("/api/v1/laboratorio"):
        if path.endswith("/cerrar"):
            action = "cerrar"
        elif "/desvios/" in path:
            action = path.rsplit("/", 1)[-1]
        return "M13", action
    if path.startswith("/api/v1/plc"):
        return "M14", action
    if path.startswith("/api/v1/mua") or path.startswith("/api/v1/trazabilidad") or path.startswith("/api/v1/lineas"):
        return "M4", action
    if path.startswith("/api/v1/catalogos"):
        return "M11", action
    if path.startswith("/api/v1/limites"):
        return "M12", action
    if path.startswith("/api/v1/analitica"):
        return "M2", "recalcular"
    if path.startswith("/api/v1/kpi"):
        return "M2", "ver"
    if path.startswith(("/api/v1/roles", "/api/v1/personas", "/api/v1/usuarios", "/api/v1/parametros", "/api/v1/calendario", "/api/v1/auditoria", "/api/v1/importaciones", "/api/v1/sincronizacion")):
        if path.startswith("/api/v1/sincronizacion/") and method == "POST":
            action = "editar"
        return "M15", action
    return None


def ensure_permission(db: Session, user: User, module: str, action: str) -> None:
    role = db.get(Role, user.id_rol)
    if role is None or not role.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol inactivo")
    permission = db.scalar(select(Permission).where(Permission.id_rol == user.id_rol, Permission.modulo == module, Permission.accion == action))
    if permission is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")


def permission_scopes(db: Session, user: User, module: str, action: str) -> set[str]:
    return set(db.scalars(select(Permission.alcance).where(Permission.id_rol == user.id_rol, Permission.modulo == module, Permission.accion == action)))


def authenticated_user(credentials: HTTPAuthorizationCredentials | None, db: Session) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido") from exc
    user = db.get(User, user_id)
    if user is None or not user.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo")
    return user


def restrict_remote_request(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> None:
    if credentials is None:
        return
    user = authenticated_user(credentials, db)
    if user.consulta_remota and not (request.method == "GET" and request.url.path == "/api/v1/kpi"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consulta remota solo puede acceder a GET /api/v1/kpi")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def make_token(user: User, role: Role) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user.id), "role": role.nombre, "sector": user.sector, "remote": user.consulta_remota, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_at


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    user = authenticated_user(credentials, db)
    if user.consulta_remota:
        if request.method == "GET" and request.url.path == "/api/v1/kpi":
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consulta remota solo puede acceder a GET /api/v1/kpi")
    required = permission_for_request(request)
    if required is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ruta protegida sin permiso asignado")
    ensure_permission(db, user, *required)
    return user


def require_permission(module: str, action: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        ensure_permission(db, user, module, action)
        return user
    return dependency


def require_admin(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    ensure_permission(db, user, "M15", "administrar")
    return user
