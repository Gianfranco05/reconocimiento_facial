"""Configuración editable en tiempo de ejecución."""

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, Engine, require_admin
from app.schemas.configuracion import ConfigOut
from app.services.runtime_config import RuntimeConfig

router = APIRouter(prefix="/api/configuracion", tags=["configuracion"])


def to_out(engine) -> ConfigOut:
    return ConfigOut(**engine.config.model_dump(), model_version=engine.pipeline.embedder.model_version)


@router.get("", response_model=ConfigOut)
def get_config(engine: Engine) -> ConfigOut:
    return to_out(engine)


@router.put("", response_model=ConfigOut, dependencies=[Depends(require_admin)])
def update_config(body: RuntimeConfig, session: DbSession, engine: Engine) -> ConfigOut:
    """Reemplaza la configuración completa. Se guarda en la base y se aplica
    de inmediato (threshold, cooldown, máximo de rostros, etc.)."""
    engine.update_config(session, body)
    session.commit()
    engine.apply_config(body)
    return to_out(engine)
