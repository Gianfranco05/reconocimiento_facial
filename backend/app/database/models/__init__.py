"""Importar todos los modelos acá para que Alembic y SQLAlchemy los registren."""

from app.database.models.app_setting import AppSetting
from app.database.models.attendance_record import AttendanceRecord, AttendanceType
from app.database.models.face_embedding import FaceEmbedding
from app.database.models.person import Person
from app.database.models.recognition_event import RecognitionEvent
from app.database.models.revoked_token import RevokedToken
from app.database.models.user import User, UserRole

__all__ = [
    "AppSetting",
    "AttendanceRecord",
    "AttendanceType",
    "FaceEmbedding",
    "Person",
    "RecognitionEvent",
    "RevokedToken",
    "User",
    "UserRole",
]
