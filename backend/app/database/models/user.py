import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class UserRole(enum.StrEnum):
    # Administra personas, rostros, configuración y usuarios.
    ADMIN = "ADMIN"
    # Opera la cámara (reconocimiento, asistencia, liveness) y consulta datos.
    OPERATOR = "OPERATOR"


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Usuario del panel (no confundir con `Person`, las personas reconocidas)."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Hash Argon2id; nunca la contraseña.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    # Se incrementa al cambiar la contraseña o desactivar: invalida todas las sesiones abiertas.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
