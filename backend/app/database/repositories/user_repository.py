"""Acceso a usuarios del panel."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateError, NotFoundError
from app.core.security import hash_password
from app.database.models import User, UserRole

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,64}$")


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> str:
    username = normalize_username(username)
    if not USERNAME_PATTERN.match(username):
        raise ValueError("El usuario debe tener 3 a 64 caracteres: letras, números, punto, guion o guion bajo.")
    return username


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == normalize_username(username)))

    def list(self) -> list[User]:
        return list(self.session.scalars(select(User).order_by(User.username)))

    def create(self, username: str, password: str, role: UserRole) -> User:
        user = User(username=validate_username(username), password_hash=hash_password(password), role=role)
        try:
            with self.session.begin_nested():
                self.session.add(user)
                self.session.flush()
        except IntegrityError as exc:
            raise DuplicateError("Ya existe un usuario con ese nombre.") from exc
        return user

    def set_password(self, username: str, password: str) -> User:
        user = self._require(username)
        user.password_hash = hash_password(password)
        user.token_version += 1  # cierra las sesiones abiertas con la contraseña anterior
        self.session.flush()
        return user

    def set_active(self, username: str, active: bool) -> User:
        user = self._require(username)
        user.active = active
        if not active:
            user.token_version += 1
        self.session.flush()
        return user

    def _require(self, username: str) -> User:
        user = self.get_by_username(username)
        if user is None:
            raise NotFoundError(f"No existe el usuario '{normalize_username(username)}'.")
        return user
