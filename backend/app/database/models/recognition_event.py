import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class RecognitionEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Un reconocimiento registrado (persona conocida o desconocida)."""

    __tablename__ = "recognition_events"
    __table_args__ = (Index("ix_recognition_events_created_at", "created_at"),)

    # NULL para desconocidos, o si la persona se eliminó después del evento.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL"), index=True
    )
    recognized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    distance: Mapped[float | None] = mapped_column(Float)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False)
