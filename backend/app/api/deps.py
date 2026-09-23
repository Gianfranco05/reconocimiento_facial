"""Dependencias compartidas por los routers."""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.exceptions import PermissionDeniedError
from app.core.security import TokenClaims
from app.database.models import User, UserRole
from app.services.auth_service import AuthService
from app.services.engine import FaceTrackEngine
from app.utils.dates import local_day_bounds

SESSION_COOKIE = "facetrack_session"

# Declara la cookie de sesión como esquema de seguridad en OpenAPI (la
# documentación marca qué rutas la requieren). auto_error=False: la ausencia
# de cookie la informa AuthService con el formato de error de la API.
session_cookie_scheme = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    description="Cookie HttpOnly que entrega POST /api/auth/login.",
)


def get_db(request: Request) -> Iterator[Session]:
    """Una sesión por request. Los endpoints que escriben hacen commit
    explícito; si algo falla antes, se revierte."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine(request: Request) -> FaceTrackEngine:
    return request.app.state.engine


DbSession = Annotated[Session, Depends(get_db)]
Engine = Annotated[FaceTrackEngine, Depends(get_engine)]


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


Auth = Annotated[AuthService, Depends(get_auth)]


def get_session_claims(
    request: Request,
    session: DbSession,
    auth: Auth,
    token: Annotated[str | None, Depends(session_cookie_scheme)],
) -> tuple[User, TokenClaims]:
    """Valida la cookie de sesión. 401 si falta, venció o fue revocada."""
    user, claims = auth.authenticate(session, token)
    request.state.user = user
    return user, claims


SessionClaims = Annotated[tuple[User, TokenClaims], Depends(get_session_claims)]


def require_user(claims: SessionClaims) -> User:
    return claims[0]


CurrentUser = Annotated[User, Depends(require_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise PermissionDeniedError("Esta acción requiere un usuario administrador.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


def query_error(param: str, message: str) -> RequestValidationError:
    """Error 422 con el mismo formato que las validaciones automáticas de FastAPI."""
    return RequestValidationError([{"loc": ("query", param), "msg": message, "type": "value_error"}])


def date_range(
    engine: Engine,
    day: Annotated[date | None, Query(alias="date", description="Un día (hora local)")] = None,
    date_from: Annotated[date | None, Query(alias="from", description="Desde (incluido, hora local)")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Hasta (incluido, hora local)")] = None,
) -> tuple[datetime | None, datetime | None]:
    """Convierte los filtros de fecha local (`date`, o `from`/`to`) a un rango UTC [inicio, fin)."""
    if day is not None and (date_from is not None or date_to is not None):
        raise query_error("date", "Usá 'date' o 'from'/'to', no ambos.")
    if date_from and date_to and date_from > date_to:
        raise query_error("from", "'from' es posterior a 'to'.")

    tz = engine.settings.tz
    if day is not None:
        return local_day_bounds(day, tz)
    start = local_day_bounds(date_from, tz)[0] if date_from else None
    end = local_day_bounds(date_to, tz)[1] if date_to else None
    return start, end


DateRange = Annotated[tuple[datetime | None, datetime | None], Depends(date_range)]
