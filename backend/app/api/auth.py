"""Inicio y cierre de sesión."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SESSION_COOKIE, Auth, DbSession, SessionClaims
from app.database.models import User, UserRole
from app.schemas.common import ErrorOut
from app.utils.dates import utc_now

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: UserRole
    last_login_at: datetime | None


def to_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, last_login_at=user.last_login_at)


@router.post(
    "/login",
    response_model=UserOut,
    responses={401: {"model": ErrorOut}, 429: {"model": ErrorOut, "description": "Demasiados intentos"}},
)
def login(body: LoginIn, request: Request, response: Response, session: DbSession, auth: Auth) -> UserOut:
    """Valida usuario y contraseña y abre una sesión en una cookie HttpOnly
    (no accesible desde JavaScript). Mensaje genérico ante cualquier error de credenciales."""
    client_ip = request.client.host if request.client else "unknown"
    result = auth.login(session, body.username, body.password, client_ip, utc_now())
    session.commit()
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=auth.settings.access_token_minutes * 60,
        httponly=True,
        secure=auth.settings.cookie_secure,
        samesite="strict",
        path="/api",
    )
    return to_out(result.user)


@router.get("/me", response_model=UserOut, responses={401: {"model": ErrorOut}})
def me(claims: SessionClaims) -> UserOut:
    return to_out(claims[0])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses={401: {"model": ErrorOut}})
def logout(claims: SessionClaims, session: DbSession, auth: Auth) -> Response:
    """Revoca el token actual (aunque alguien lo haya copiado, deja de servir) y borra la cookie."""
    auth.logout(session, claims[1], utc_now())
    session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        SESSION_COOKIE, path="/api", httponly=True, secure=auth.settings.cookie_secure, samesite="strict"
    )
    return response
