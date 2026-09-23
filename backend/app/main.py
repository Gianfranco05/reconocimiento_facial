"""API REST de FaceTrack.

Ejecutar (desde backend/):
    uvicorn app.main:app --reload

Documentación interactiva: http://localhost:8000/docs

Todas las rutas requieren sesión salvo /api/health y /api/auth/login.
Crear el primer usuario: python -m app.cli.users create <usuario> --role admin
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api import asistencia, auth, configuracion, estadisticas, health, liveness, personas, reconocimiento
from app.api.deps import require_user
from app.api.errors import register_error_handlers
from app.api.middleware import (
    BodySizeLimitMiddleware,
    OriginCheckMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.database.connection import get_session_factory
from app.services.auth_service import AuthService
from app.services.engine import FaceTrackEngine

API_DESCRIPTION = """
Reconocimiento facial, asistencia y estadísticas con **procesamiento local**.

**Autenticación.** `POST /api/auth/login` entrega una cookie de sesión HttpOnly;
el navegador la envía sola en las demás llamadas. Todas las rutas la requieren
salvo `GET /api/health` y el login. Las marcadas *Solo ADMIN* exigen ese rol.

**Errores.** Siempre `{"detail": str, "code": str}`; los 5xx agregan
`request_id` (también en la cabecera `X-Request-ID` de toda respuesta), que
permite encontrar el detalle en los logs.

**Privacidad.** Las imágenes se procesan en memoria y se descartan; ninguna
respuesta incluye embeddings.
"""

OPENAPI_TAGS = [
    {"name": "auth", "description": "Inicio y cierre de sesión."},
    {"name": "health", "description": "Estado del servicio (público, para healthchecks)."},
    {"name": "personas", "description": "Personas reconocibles y sus muestras faciales."},
    {"name": "reconocimiento", "description": "Reconocimiento por imagen e historial de eventos."},
    {"name": "liveness", "description": "Landmarks faciales y prueba de vida básica por desafíos."},
    {"name": "asistencia", "description": "Registros de entrada/salida y exportación CSV."},
    {"name": "estadisticas", "description": "Resumen del día y estadísticas por período."},
    {"name": "configuracion", "description": "Configuración editable en tiempo de ejecución."},
]

# Margen para las cabeceras y separadores del multipart sobre MAX_UPLOAD_MB.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

logger = logging.getLogger("facetrack.api")


def create_app(
    settings: Settings | None = None,
    engine: FaceTrackEngine | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> FastAPI:
    """`engine` y `session_factory` se inyectan en los tests; en producción se
    crean al arrancar (cargar los modelos lleva un momento)."""
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.session_factory = session_factory or get_session_factory()
        app.state.auth = AuthService(settings)
        owns_engine = engine is None
        app.state.engine = engine or FaceTrackEngine.create(settings)
        if owns_engine:
            with app.state.session_factory() as session:
                app.state.engine.start(session)
        logger.info("FaceTrack API started")
        yield
        if owns_engine:
            app.state.engine.close()
        logger.info("FaceTrack API stopped")

    docs = settings.api_docs_enabled
    app = FastAPI(
        title="FaceTrack API",
        version="1.0.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        # Bajo /api para que también sean accesibles a través de nginx.
        docs_url="/api/docs" if docs else None,
        redoc_url="/api/redoc" if docs else None,
        openapi_url="/api/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    # add_middleware apila hacia afuera: el último agregado se ejecuta primero.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES)
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.cors_origin_list)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    # El más externo: el id de request existe durante todo el procesamiento.
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.exception_handler(RequestValidationError)
    def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(error.errors()), "code": "validation_error"},
        )

    # Públicas: estado del servicio y login. Todo lo demás exige sesión; las
    # acciones de administración además exigen rol ADMIN (ver cada router).
    app.include_router(health.router)
    app.include_router(auth.router)
    for module in (personas, reconocimiento, liveness, asistencia, estadisticas, configuracion):
        app.include_router(module.router, dependencies=[Depends(require_user)])
    return app


app = create_app()
