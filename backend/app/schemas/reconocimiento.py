import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.database.models import AttendanceType
from app.schemas.common import BoundingBoxOut

UNKNOWN_NAME = "Desconocido"


class RecognitionMode(StrEnum):
    RECOGNITION = "recognition"  # solo reconocer (y registrar eventos)
    ATTENDANCE = "attendance"  # además registrar ENTRY / EXIT


class AttendanceMarkOut(BaseModel):
    type: AttendanceType
    created_at: datetime


class FaceResultOut(BaseModel):
    recognized: bool
    person_id: uuid.UUID | None
    name: str
    confidence: float
    distance: float | None
    bbox: BoundingBoxOut
    # Motivo si el rostro no se pudo evaluar (p. ej. demasiado chico).
    error: str | None = None
    attendance: AttendanceMarkOut | None = None


class RecognitionOut(BaseModel):
    faces_detected: int
    image_width: int
    image_height: int
    events_recorded: int
    results: list[FaceResultOut]


class EventOut(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID | None
    person_name: str
    recognized: bool
    confidence: float
    distance: float | None
    camera_id: str
    created_at: datetime


class EventPage(BaseModel):
    total: int
    items: list[EventOut]
