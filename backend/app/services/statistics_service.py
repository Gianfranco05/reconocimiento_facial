"""Estadísticas para el dashboard y la página Estadísticas.

Los días se cuentan en la zona horaria configurada (TIMEZONE), no en UTC: un
reconocimiento a las 22:30 de Buenos Aires cuenta para ese día aunque en UTC
ya sea el siguiente.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, func, select
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, AttendanceType, Person, RecognitionEvent
from app.utils.dates import local_day_bounds


@dataclass(frozen=True)
class Activity:
    created_at: datetime
    person_id: uuid.UUID | None
    person_name: str | None
    recognized: bool
    confidence: float


@dataclass(frozen=True)
class Summary:
    date: date
    persons_registered: int
    recognitions_today: int
    people_present: int
    unknown_today: int
    recent_activity: list[Activity]


@dataclass(frozen=True)
class DailyCount:
    date: date
    recognized: int
    unknown: int
    entries: int
    exits: int


@dataclass(frozen=True)
class PersonCount:
    person_id: uuid.UUID
    person_name: str
    recognitions: int
    average_confidence: float


@dataclass(frozen=True)
class Statistics:
    date_from: date
    date_to: date
    recognized_total: int
    unknown_total: int
    entries: int
    exits: int
    average_confidence: float | None
    by_day: list[DailyCount]
    by_person: list[PersonCount]


class StatisticsService:
    def __init__(self, session: Session, tz: ZoneInfo) -> None:
        self.session = session
        self.tz = tz

    def summary(self, day: date, recent_limit: int = 10) -> Summary:
        start, end = local_day_bounds(day, self.tz)
        in_day = and_(RecognitionEvent.created_at >= start, RecognitionEvent.created_at < end)

        persons = self.session.scalar(select(func.count()).select_from(Person).where(Person.active.is_(True)))
        recognized, unknown = self.session.execute(
            select(
                func.count().filter(RecognitionEvent.recognized.is_(True)),
                func.count().filter(RecognitionEvent.recognized.is_(False)),
            ).where(in_day)
        ).one()

        # Presentes: personas cuyo último registro del día es ENTRY.
        last_of_day = (
            select(AttendanceRecord.person_id, AttendanceRecord.type)
            .where(AttendanceRecord.created_at >= start, AttendanceRecord.created_at < end)
            .distinct(AttendanceRecord.person_id)
            .order_by(AttendanceRecord.person_id, AttendanceRecord.created_at.desc())
            .subquery()
        )
        present = self.session.scalar(
            select(func.count()).select_from(last_of_day).where(last_of_day.c.type == AttendanceType.ENTRY)
        )

        return Summary(day, persons, recognized, present, unknown, self.recent_activity(recent_limit))

    def recent_activity(self, limit: int = 10) -> list[Activity]:
        rows = self.session.execute(
            select(RecognitionEvent, Person.first_name, Person.last_name)
            .outerjoin(Person, RecognitionEvent.person_id == Person.id)
            .order_by(RecognitionEvent.created_at.desc())
            .limit(limit)
        )
        return [
            Activity(
                event.created_at,
                event.person_id,
                f"{first} {last}".strip() if first is not None else None,
                event.recognized,
                event.confidence,
            )
            for event, first, last in rows
        ]

    def statistics(self, date_from: date, date_to: date) -> Statistics:
        """Estadísticas entre dos días locales, ambos incluidos."""
        start, _ = local_day_bounds(date_from, self.tz)
        _, end = local_day_bounds(date_to, self.tz)

        event_day = cast(func.timezone(self.tz.key, RecognitionEvent.created_at), Date).label("day")
        events_by_day = self.session.execute(
            select(
                event_day,
                func.count().filter(RecognitionEvent.recognized.is_(True)),
                func.count().filter(RecognitionEvent.recognized.is_(False)),
            )
            .where(RecognitionEvent.created_at >= start, RecognitionEvent.created_at < end)
            .group_by(event_day)
        ).all()

        record_day = cast(func.timezone(self.tz.key, AttendanceRecord.created_at), Date).label("day")
        attendance_by_day = self.session.execute(
            select(
                record_day,
                func.count().filter(AttendanceRecord.type == AttendanceType.ENTRY),
                func.count().filter(AttendanceRecord.type == AttendanceType.EXIT),
            )
            .where(AttendanceRecord.created_at >= start, AttendanceRecord.created_at < end)
            .group_by(record_day)
        ).all()

        events = {day: (rec, unk) for day, rec, unk in events_by_day}
        attendance = {day: (ent, ext) for day, ent, ext in attendance_by_day}
        by_day = []
        day = date_from
        while day <= date_to:  # incluye los días sin actividad, con 0
            rec, unk = events.get(day, (0, 0))
            ent, ext = attendance.get(day, (0, 0))
            by_day.append(DailyCount(day, rec, unk, ent, ext))
            day += timedelta(days=1)

        by_person_rows = self.session.execute(
            select(
                Person.id,
                Person.first_name,
                Person.last_name,
                func.count(RecognitionEvent.id),
                func.avg(RecognitionEvent.confidence),
            )
            .join(RecognitionEvent, RecognitionEvent.person_id == Person.id)
            .where(
                RecognitionEvent.recognized.is_(True),
                RecognitionEvent.created_at >= start,
                RecognitionEvent.created_at < end,
            )
            .group_by(Person.id, Person.first_name, Person.last_name)
            .order_by(func.count(RecognitionEvent.id).desc(), Person.first_name)
        ).all()
        by_person = [
            PersonCount(pid, f"{first} {last}".strip(), count, round(float(avg), 4))
            for pid, first, last, count, avg in by_person_rows
        ]

        average = self.session.scalar(
            select(func.avg(RecognitionEvent.confidence)).where(
                RecognitionEvent.recognized.is_(True),
                RecognitionEvent.created_at >= start,
                RecognitionEvent.created_at < end,
            )
        )
        return Statistics(
            date_from=date_from,
            date_to=date_to,
            recognized_total=sum(d.recognized for d in by_day),
            unknown_total=sum(d.unknown for d in by_day),
            entries=sum(d.entries for d in by_day),
            exits=sum(d.exits for d in by_day),
            average_confidence=round(float(average), 4) if average is not None else None,
            by_day=by_day,
            by_person=by_person,
        )
