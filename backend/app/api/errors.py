"""Traduce las excepciones de dominio a respuestas HTTP.

Todas las respuestas de error tienen la forma {"detail": str, "code": str}.
Los errores inesperados devuelven 500 con un mensaje genérico: el detalle
(que puede incluir rutas, SQL o la URL de la base) solo va al log.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core import exceptions as exc
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

# (excepción, status HTTP, código estable para el frontend). Orden: de la más
# específica a la más general.
ERROR_MAP: list[tuple[type[Exception], int, str]] = [
    (exc.AuthenticationError, status.HTTP_401_UNAUTHORIZED, "unauthenticated"),
    (exc.PermissionDeniedError, status.HTTP_403_FORBIDDEN, "forbidden"),
    (exc.NotFoundError, status.HTTP_404_NOT_FOUND, "not_found"),
    (exc.DuplicateError, status.HTTP_409_CONFLICT, "duplicate"),
    (exc.FaceConflictError, status.HTTP_409_CONFLICT, "face_conflict"),
    (exc.PayloadTooLargeError, status.HTTP_413_CONTENT_TOO_LARGE, "payload_too_large"),
    (exc.UnsupportedMediaError, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type"),
    (exc.InvalidImageError, status.HTTP_400_BAD_REQUEST, "invalid_image"),
    (exc.FaceNotFoundError, status.HTTP_422_UNPROCESSABLE_CONTENT, "face_not_found"),
    (exc.MultipleFacesError, status.HTTP_422_UNPROCESSABLE_CONTENT, "multiple_faces"),
    (exc.FaceTooSmallError, status.HTTP_422_UNPROCESSABLE_CONTENT, "face_too_small"),
    (exc.LowQualityFaceError, status.HTTP_422_UNPROCESSABLE_CONTENT, "low_quality"),
    (exc.EmbeddingError, status.HTTP_422_UNPROCESSABLE_CONTENT, "embedding_error"),
]


def _error(status_code: int, code: str, detail: str) -> JSONResponse:
    content = {"detail": detail, "code": code}
    if status_code >= 500:
        # Para reportar el problema: el mismo id está en el log con el detalle.
        content["request_id"] = request_id_var.get()
    return JSONResponse(status_code=status_code, content=content)


def register_error_handlers(app: FastAPI) -> None:
    for exception_type, status_code, code in ERROR_MAP:

        def handler(request: Request, error: Exception, status_code=status_code, code=code) -> JSONResponse:
            return _error(status_code, code, str(error))

        app.add_exception_handler(exception_type, handler)

    @app.exception_handler(exc.TooManyAttemptsError)
    def too_many_attempts(request: Request, error: exc.TooManyAttemptsError) -> JSONResponse:
        response = _error(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts", str(error))
        response.headers["Retry-After"] = str(error.retry_after_seconds)
        return response

    @app.exception_handler(SQLAlchemyError)
    def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error on %s %s: %s", request.method, request.url.path, error.__class__.__name__)
        logger.debug("Database error detail", exc_info=error)
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "database_error", "Error de base de datos.")

    @app.exception_handler(exc.FaceTrackError)
    def domain_error(request: Request, error: exc.FaceTrackError) -> JSONResponse:
        logger.error("Unhandled domain error on %s %s: %s", request.method, request.url.path, error)
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Error interno.")
