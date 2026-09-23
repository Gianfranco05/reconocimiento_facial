"""Estado del servicio (para Docker healthchecks y el frontend)."""

import logging

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class HealthOut(BaseModel):
    """Público (lo usan los healthchecks): no expone datos de personas."""

    status: str
    database: str


@router.get("/api/health", response_model=HealthOut)
def health(session: DbSession, response: Response) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        logger.warning("Health check: database unavailable")
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthOut(status="ok" if database == "ok" else "degraded", database=database)
