"""Acceso a eventos de reconocimiento (historial)."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Person, RecognitionEvent


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        person_id: uuid.UUID | None,
        recognized: bool,
        confidence: float,
        distance: float | None,
        camera_id: str,
        created_at: datetime | None = None,
    ) -> RecognitionEvent:
        event = RecognitionEvent(
            person_id=person_id,
            recognized=recognized,
            confidence=confidence,
            distance=distance,
            camera_id=camera_id,
        )
        if created_at is not None:
            event.created_at = created_at
        self.session.add(event)
        self.session.flush()
        return event

    def latest_between(
        self, *, person_id: uuid.UUID | None, camera_id: str, start: datetime, end: datetime
    ) -> datetime | None:
        """Fecha del último evento en (start, end], o None. Para una persona
        conocida se busca por persona; para desconocidos (`person_id=None`), por cámara."""
        query = select(func.max(RecognitionEvent.created_at)).where(
            RecognitionEvent.created_at > start, RecognitionEvent.created_at <= end
        )
        if person_id is not None:
            query = query.where(RecognitionEvent.person_id == person_id)
        else:
            query = query.where(RecognitionEvent.recognized.is_(False), RecognitionEvent.camera_id == camera_id)
        return self.session.scalar(query)

    def search(
        self,
        *,
        person_id: uuid.UUID | None = None,
        recognized: bool | None = None,
        camera_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[tuple[RecognitionEvent, str | None]], int]:
        """Página de eventos (más recientes primero) con el nombre de la persona
        (None si es desconocido o fue eliminada), y el total sin paginar."""
        conditions = []
        if person_id is not None:
            conditions.append(RecognitionEvent.person_id == person_id)
        if recognized is not None:
            conditions.append(RecognitionEvent.recognized == recognized)
        if camera_id is not None:
            conditions.append(RecognitionEvent.camera_id == camera_id)
        if start is not None:
            conditions.append(RecognitionEvent.created_at >= start)
        if end is not None:
            conditions.append(RecognitionEvent.created_at < end)

        total = self.session.scalar(select(func.count()).select_from(RecognitionEvent).where(*conditions))
        rows = self.session.execute(
            select(RecognitionEvent, Person.first_name, Person.last_name)
            .outerjoin(Person, RecognitionEvent.person_id == Person.id)
            .where(*conditions)
            .order_by(RecognitionEvent.created_at.desc(), RecognitionEvent.id)
            .limit(limit)
            .offset(offset)
        )
        items = [(event, f"{first} {last}".strip() if first is not None else None) for event, first, last in rows]
        return items, total

    def list(
        self,
        *,
        person_id: uuid.UUID | None = None,
        recognized: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[RecognitionEvent]:
        """Eventos más recientes primero. `start` incluido, `end` excluido (UTC)."""
        query = select(RecognitionEvent).order_by(RecognitionEvent.created_at.desc()).limit(limit)
        if person_id is not None:
            query = query.where(RecognitionEvent.person_id == person_id)
        if recognized is not None:
            query = query.where(RecognitionEvent.recognized == recognized)
        if start is not None:
            query = query.where(RecognitionEvent.created_at >= start)
        if end is not None:
            query = query.where(RecognitionEvent.created_at < end)
        return list(self.session.scalars(query))
