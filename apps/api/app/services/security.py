from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.core import Permission, Role, User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def make_token(user: User, role: Role) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user.id), "role": role.nombre, "sector": user.sector, "remote": user.consulta_remota, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_at


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
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


def require_permission(module: str, action: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        role = db.get(Role, user.id_rol)
        if role is None or not role.activo:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol inactivo")
        if user.consulta_remota and action != "ver":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consulta remota es solo lectura")
        permission = db.scalar(select(Permission).where(Permission.id_rol == user.id_rol, Permission.modulo == module, Permission.accion == action))
        if permission is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")
        return user
    return dependency


def require_admin(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    role = db.get(Role, user.id_rol)
    if role is None or role.nombre != "ADMIN" or user.consulta_remota:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol ADMIN")
    return user
