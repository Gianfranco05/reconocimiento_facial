import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AttendanceType(enum.StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class AttendanceRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (Index("ix_attendance_records_person_id_created_at", "person_id", "created_at"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AttendanceType] = mapped_column(Enum(AttendanceType, name="attendance_type"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
