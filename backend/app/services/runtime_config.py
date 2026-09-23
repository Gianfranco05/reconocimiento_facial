"""Configuración editable en tiempo de ejecución (página Configuración).

Los valores iniciales salen de las variables de entorno; los cambios hechos
desde la API se guardan en la tabla `app_settings` y tienen prioridad.
"""

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import AppSetting

SETTINGS_KEY = "runtime"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    face_recognition_threshold: float = Field(ge=0.2, le=1.0)
    recognition_cooldown_seconds: int = Field(ge=0, le=3600)
    attendance_min_interval_minutes: int = Field(ge=0, le=24 * 60)
    # FPS con que el cliente (navegador) envía frames para reconocer.
    camera_fps: int = Field(ge=1, le=30)
    max_faces: int = Field(ge=1, le=50)
    camera_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    save_events: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> "RuntimeConfig":
        return cls(
            face_recognition_threshold=min(max(settings.face_recognition_threshold, 0.2), 1.0),
            recognition_cooldown_seconds=settings.recognition_cooldown_seconds,
            attendance_min_interval_minutes=settings.attendance_min_interval_minutes,
            camera_fps=min(settings.camera_fps, 30),
            max_faces=settings.max_faces,
            camera_id=settings.camera_id,
            save_events=settings.save_events,
        )


class RuntimeConfigStore:
    def __init__(self, defaults: RuntimeConfig) -> None:
        self.defaults = defaults

    def load(self, session: Session) -> RuntimeConfig:
        row = session.get(AppSetting, SETTINGS_KEY)
        if row is None:
            return self.defaults
        merged = {**self.defaults.model_dump(), **row.value}
        try:
            return RuntimeConfig.model_validate(
                {k: v for k, v in merged.items() if k in RuntimeConfig.model_fields}
            )
        except ValidationError:
            # Un valor guardado que ya no es válido (p. ej. cambió un rango) no
            # debe impedir arrancar: se vuelve a los valores del entorno.
            return self.defaults

    def save(self, session: Session, config: RuntimeConfig) -> None:
        row = session.get(AppSetting, SETTINGS_KEY)
        if row is None:
            session.add(AppSetting(key=SETTINGS_KEY, value=config.model_dump()))
        else:
            row.value = config.model_dump()
        session.flush()
