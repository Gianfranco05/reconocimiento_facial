"""Autenticación: inicio de sesión, validación de la sesión y cierre.

- Las contraseñas se verifican contra hashes Argon2id; si el usuario no existe
  se verifica igual contra un hash ficticio, así la respuesta no revela qué
  usuarios existen (ni por el mensaje ni por el tiempo).
- Tras `login_max_attempts` fallos seguidos para un mismo usuario desde una
  misma IP, se bloquean los intentos durante `login_lockout_minutes`.
- La sesión es un JWT firmado en una cookie HttpOnly. Se rechaza si venció,
  si se cerró con logout (lista de revocados), si el usuario se desactivó o si
  cambió su contraseña (token_version).
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, TooManyAttemptsError
from app.core.security import (
    TokenClaims,
    create_access_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.database.models import RevokedToken, User
from app.database.repositories.user_repository import UserRepository, normalize_username

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Usuario o contraseña incorrectos."


class LoginThrottle:
    """Cuenta fallos por (usuario, IP) en memoria del proceso."""

    def __init__(self, max_attempts: int, lockout: timedelta) -> None:
        self.max_attempts = max_attempts
        self.lockout = lockout
        self._failures: dict[tuple[str, str], tuple[int, datetime]] = {}
        self._lock = threading.Lock()

    def check(self, key: tuple[str, str], now: datetime) -> None:
        with self._lock:
            count, last = self._failures.get(key, (0, now))
            if count >= self.max_attempts:
                remaining = self.lockout - (now - last)
                if remaining > timedelta(0):
                    raise TooManyAttemptsError(
                        "Demasiados intentos fallidos. Probá de nuevo en unos minutos.",
                        retry_after_seconds=int(remaining.total_seconds()) + 1,
                    )
                del self._failures[key]

    def failure(self, key: tuple[str, str], now: datetime) -> None:
        with self._lock:
            count, _ = self._failures.get(key, (0, now))
            self._failures[key] = (count + 1, now)
            if len(self._failures) > 10_000:  # evita crecer sin límite
                cutoff = now - self.lockout
                self._failures = {k: v for k, v in self._failures.items() if v[1] > cutoff}

    def success(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)


@dataclass(frozen=True)
class LoginResult:
    user: User
    token: str
    claims: TokenClaims


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.throttle = LoginThrottle(settings.login_max_attempts, timedelta(minutes=settings.login_lockout_minutes))

    def login(self, session: Session, username: str, password: str, client_ip: str, now: datetime) -> LoginResult:
        key = (normalize_username(username), client_ip)
        self.throttle.check(key, now)

        user = UserRepository(session).get_by_username(username)
        valid = verify_password(password, user.password_hash if user else None)
        if not valid or user is None or not user.active:
            self.throttle.failure(key, now)
            logger.warning("Failed login attempt")  # sin usuario ni IP: no llenar el log de datos personales
            raise AuthenticationError(INVALID_CREDENTIALS)

        self.throttle.success(key)
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = now
        token, claims = create_access_token(self.settings, user.id, user.token_version, now)
        logger.info("User logged in (role=%s)", user.role.value)
        return LoginResult(user, token, claims)

    def authenticate(self, session: Session, token: str | None) -> tuple[User, TokenClaims]:
        if not token:
            raise AuthenticationError("Iniciá sesión para continuar.")
        claims = decode_access_token(self.settings, token)
        if session.get(RevokedToken, claims.jti) is not None:
            raise AuthenticationError("La sesión fue cerrada.")
        user = UserRepository(session).get(claims.user_id)
        if user is None or not user.active or user.token_version != claims.token_version:
            raise AuthenticationError("La sesión ya no es válida. Iniciá sesión de nuevo.")
        return user, claims

    def logout(self, session: Session, claims: TokenClaims, now: datetime) -> None:
        if session.get(RevokedToken, claims.jti) is None:
            session.add(RevokedToken(jti=claims.jti, expires_at=claims.expires_at))
        # Los revocados ya vencidos no hacen falta: el JWT se rechaza por vencimiento.
        session.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
        session.flush()
