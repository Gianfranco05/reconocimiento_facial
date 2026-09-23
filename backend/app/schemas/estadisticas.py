import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ActivityOut(BaseModel):
    created_at: datetime
    person_id: uuid.UUID | None
    person_name: str
    recognized: bool
    confidence: float


class SummaryOut(BaseModel):
    date: date
    persons_registered: int
    recognitions_today: int
    people_present: int
    unknown_today: int
    recent_activity: list[ActivityOut]


class DailyCountOut(BaseModel):
    date: date
    recognized: int
    unknown: int
    entries: int
    exits: int


class PersonCountOut(BaseModel):
    person_id: uuid.UUID
    person_name: str
    recognitions: int
    average_confidence: float


class StatisticsOut(BaseModel):
    date_from: date
    date_to: date
    recognized_total: int
    unknown_total: int
    entries: int
    exits: int
    # Promedio de confidence de los reconocimientos (sin desconocidos); None si no hubo.
    average_confidence: float | None
    by_day: list[DailyCountOut]
    by_person: list[PersonCountOut]
