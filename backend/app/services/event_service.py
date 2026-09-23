"""Registro de eventos de reconocimiento (historial), con cooldown.

Clave de cooldown:
- persona conocida: su id (la misma persona no se registra dos veces dentro de
  la ventana, aunque aparezca en varios frames);
- desconocido: la cámara (como no hay identidad, se registra como máximo un
  "DESCONOCIDO" por cámara dentro de la ventana).

El cooldown tiene dos niveles:
1. En memoria: descarta las repeticiones de frames consecutivos sin tocar la base.
2. En la base (solo con `SAVE_EVENTS=true`): cuando la memoria deja pasar un
   resultado, se verifica que no haya un evento de la misma clave dentro de la
   ventana. Así el cooldown se respeta aunque el proceso se reinicie o haya
   varios workers/cámaras.

El cooldown se aplica aunque `SAVE_EVENTS=false`: los resultados "nuevos" que
devuelve `process` son los que deben disparar acciones (por ejemplo, asistencia).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models import RecognitionEvent
from app.database.repositories.event_repository import EventRepository
from app.services.cooldown import RecognitionCooldown
from app.services.face_recognizer import RecognitionResult
from app.utils.dates import utc_now

logger = logging.getLogger(__name__)


@dataclass
class ProcessedResults:
    # Resultados que superaron el cooldown (los repetidos se descartan).
    fresh: list[RecognitionResult] = field(default_factory=list)
    # Eventos guardados (vacío si SAVE_EVENTS=false).
    events: list[RecognitionEvent] = field(default_factory=list)


class RecognitionEventService:
    def __init__(self, cooldown: RecognitionCooldown, camera_id: str, save_events: bool = True) -> None:
        self.cooldown = cooldown
        self.camera_id = camera_id
        self.save_events = save_events

    def process(
        self, session: Session, results: list[RecognitionResult], now: datetime | None = None
    ) -> ProcessedResults:
        now = now or utc_now()
        repository = EventRepository(session)
        processed = ProcessedResults()
        for result in results:
            key = f"person:{result.person_id}" if result.recognized else f"unknown:{self.camera_id}"
            if not self.cooldown.allow(key, now):
                continue
            person_id = uuid.UUID(result.person_id) if result.recognized else None
            if self.save_events:
                previous = repository.latest_between(
                    person_id=person_id, camera_id=self.camera_id, start=now - self.cooldown.window, end=now
                )
                if previous is not None:
                    # Otro proceso ya lo registró: la ventana corre desde ese evento.
                    self.cooldown.mark(key, previous)
                    continue
            processed.fresh.append(result)

            if result.recognized:
                logger.info("Person recognized: %s", result.person_name)
            else:
                logger.warning("Unknown face detected (camera=%s)", self.camera_id)

            if self.save_events:
                processed.events.append(
                    repository.add(
                        person_id=person_id,
                        recognized=result.recognized,
                        confidence=result.confidence,
                        distance=result.distance,
                        camera_id=self.camera_id,
                        created_at=now,
                    )
                )
        return processed
