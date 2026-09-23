import uuid
from datetime import datetime

from pydantic import BaseModel

from app.database.models import AttendanceType


class AttendanceOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID
    person_name: str
    type: AttendanceType
    confidence: float
    created_at: datetime


class AttendancePage(BaseModel):
    total: int
    items: list[AttendanceOut]
