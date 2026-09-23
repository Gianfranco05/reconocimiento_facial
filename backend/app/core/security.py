"""Protección de datos biométricos.

Los embeddings se guardan cifrados en PostgreSQL con Fernet (AES-128-CBC +
HMAC-SHA256). Quien acceda a la base sin la clave no puede leerlos ni
modificarlos sin que se detecte. La clave vive solo en el entorno
(`EMBEDDING_ENCRYPTION_KEY`), nunca en el repositorio ni en la base.

También: hash de contraseñas (Argon2id) y tokens de sesión (JWT firmados).
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
import numpy as np
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import PLACEHOLDER_SECRET, Settings
from app.core.exceptions import AuthenticationError, ConfigurationError, InvalidEmbeddingError

logger = logging.getLogger(__name__)


class EmbeddingCipher:
    def __init__(self, key: str | bytes) -> None:
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(
                "EMBEDDING_ENCRYPTION_KEY no es una clave Fernet válida (32 bytes en base64 url-safe)."
            ) from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> "EmbeddingCipher":
        if settings.embedding_encryption_key is None:
            raise ConfigurationError(
                "Falta EMBEDDING_ENCRYPTION_KEY. Generala con: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        return cls(settings.embedding_encryption_key.get_secret_value())

    def encrypt(self, embedding: np.ndarray) -> bytes:
        return self._fernet.encrypt(np.asarray(embedding, dtype=np.float32).tobytes())

    def decrypt(self, token: bytes, dimension: int) -> np.ndarray:
        try:
            raw = self._fernet.decrypt(bytes(token))
        except InvalidToken as exc:
            raise InvalidEmbeddingError(
                "No se pudo descifrar el embedding: clave incorrecta o dato alterado."
            ) from exc
        vector = np.frombuffer(raw, dtype=np.float32)
        if vector.size != dimension:
            raise InvalidEmbeddingError(f"Se esperaban {dimension} dimensiones, se descifraron {vector.size}.")
        return vector.copy()


# --- Contraseñas ---------------------------------------------------------

_password_hasher = PasswordHasher()  # Argon2id con los parámetros recomendados por la librería
# Hash de una contraseña que nadie conoce: se verifica contra él cuando el
# usuario no existe, para que la respuesta tarde lo mismo y no revele si existe.
_DUMMY_HASH = _password_hasher.hash("facetrack-dummy-password")

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres.")
    if password.isdigit() or password.isalpha():
        raise ValueError("La contraseña debe combinar letras con números o símbolos.")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verifica en tiempo similar exista o no el usuario (`password_hash=None`)."""
    try:
        _password_hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


# --- Tokens de sesión (JWT) ------------------------------------------------

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "facetrack"
MIN_SECRET_LENGTH = 32

_ephemeral_key = secrets.token_urlsafe(48)
_warned_weak_key = False


def signing_key(settings: Settings) -> str:
    """Clave para firmar los JWT. En desarrollo, si SECRET_KEY es débil (o el
    valor de ejemplo), se usa una clave aleatoria de este proceso: firmar con
    "change_me" permitiría a cualquiera fabricar sesiones válidas. Las sesiones
    se pierden al reiniciar. En producción la configuración ya exige una clave fuerte."""
    global _warned_weak_key
    secret = settings.secret_key.get_secret_value()
    if secret != PLACEHOLDER_SECRET and len(secret) >= MIN_SECRET_LENGTH:
        return secret
    if not _warned_weak_key:
        logger.warning("SECRET_KEY is weak or unset: using a random per-process key (sessions end on restart)")
        _warned_weak_key = True
    return _ephemeral_key


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    jti: str
    token_version: int
    expires_at: datetime


def create_access_token(
    settings: Settings, user_id: uuid.UUID, token_version: int, now: datetime
) -> tuple[str, TokenClaims]:
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    claims = TokenClaims(user_id, secrets.token_urlsafe(24), token_version, expires_at)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "jti": claims.jti,
            "ver": token_version,
            "iss": JWT_ISSUER,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        signing_key(settings),
        algorithm=JWT_ALGORITHM,
    )
    return token, claims


def decode_access_token(settings: Settings, token: str) -> TokenClaims:
    """Valida firma, emisor y vencimiento. Solo acepta HS256 (evita el ataque
    de cambiar el algoritmo a 'none' u otro)."""
    try:
        payload = jwt.decode(
            token,
            signing_key(settings),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "jti", "ver", "exp", "iss"]},
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            jti=str(payload["jti"]),
            token_version=int(payload["ver"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise AuthenticationError("Sesión inválida o vencida.") from exc
