import uuid

from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class FaceEmbedding(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Embedding facial cifrado. Se guarda como bytes para no atar el esquema a
    un modelo concreto: `model_version` y `dimension` indican cómo interpretarlo."""

    __tablename__ = "face_embeddings"

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    person = relationship("Person", back_populates="embeddings")
