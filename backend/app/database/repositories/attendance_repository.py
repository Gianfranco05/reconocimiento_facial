"""Acceso a registros de asistencia."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, AttendanceType, Person


class AttendanceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def last_for_person(self, person_id: uuid.UUID) -> AttendanceRecord | None:
        return self.session.scalar(
            select(AttendanceRecord)
            .where(AttendanceRecord.person_id == person_id)
            .order_by(AttendanceRecord.created_at.desc())
            .limit(1)
        )

    def add(
        self,
        person_id: uuid.UUID,
        type_: AttendanceType,
        confidence: float,
        created_at: datetime | None = None,
    ) -> AttendanceRecord:
        record = AttendanceRecord(person_id=person_id, type=type_, confidence=confidence)
        if created_at is not None:
            record.created_at = created_at
        self.session.add(record)
        self.session.flush()
        return record

    def search(
        self,
        *,
        person_id: uuid.UUID | None = None,
        type_: AttendanceType | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = 100,
        offset: int = 0,
    ) -> tuple[list[tuple[AttendanceRecord, str]], int]:
        """Página de registros (más recientes primero) con el nombre de la
        persona, y el total sin paginar. `limit=None` devuelve todos (exportación)."""
        conditions = []
        if person_id is not None:
            conditions.append(AttendanceRecord.person_id == person_id)
        if type_ is not None:
            conditions.append(AttendanceRecord.type == type_)
        if start is not None:
            conditions.append(AttendanceRecord.created_at >= start)
        if end is not None:
            conditions.append(AttendanceRecord.created_at < end)

        total = self.session.scalar(select(func.count()).select_from(AttendanceRecord).where(*conditions))
        query = (
            select(AttendanceRecord, Person.first_name, Person.last_name)
            .join(Person, AttendanceRecord.person_id == Person.id)
            .where(*conditions)
            .order_by(AttendanceRecord.created_at.desc(), AttendanceRecord.id)
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        items = [(record, f"{first} {last}".strip()) for record, first, last in self.session.execute(query)]
        return items, total

    def list(
        self,
        *,
        person_id: uuid.UUID | None = None,
        type_: AttendanceType | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[AttendanceRecord]:
        """Registros más recientes primero. `start` incluido, `end` excluido (UTC)."""
        query = select(AttendanceRecord).order_by(AttendanceRecord.created_at.desc()).limit(limit)
        if person_id is not None:
            query = query.where(AttendanceRecord.person_id == person_id)
        if type_ is not None:
            query = query.where(AttendanceRecord.type == type_)
        if start is not None:
            query = query.where(AttendanceRecord.created_at >= start)
        if end is not None:
            query = query.where(AttendanceRecord.created_at < end)
        return list(self.session.scalars(query))
