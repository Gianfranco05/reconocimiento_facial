from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Person(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "persons"

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    # Las personas inactivas no se reconocen, pero se conserva su historial.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    embeddings = relationship("FaceEmbedding", back_populates="person", passive_deletes=True)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
