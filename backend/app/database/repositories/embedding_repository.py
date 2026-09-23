"""Acceso a embeddings faciales. Cifra al guardar y descifra al leer: fuera de
este módulo los embeddings nunca existen en su forma almacenada."""

import uuid

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConfigurationError
from app.core.security import EmbeddingCipher
from app.database.models import FaceEmbedding, Person
from app.services.embedding_service import validate_embedding
from app.services.face_recognizer import KnownEmbedding


class EmbeddingRepository:
    def __init__(self, session: Session, cipher: EmbeddingCipher | None = None) -> None:
        """`cipher` solo es necesario para guardar o leer embeddings; las
        operaciones de metadatos (contar, listar, borrar) no lo usan."""
        self.session = session
        self._cipher = cipher

    @property
    def cipher(self) -> EmbeddingCipher:
        if self._cipher is None:
            raise ConfigurationError("Esta operación necesita la clave de cifrado de embeddings.")
        return self._cipher

    def add(self, person_id: uuid.UUID, embedding: np.ndarray, model_version: str) -> FaceEmbedding:
        vector = validate_embedding(embedding)
        record = FaceEmbedding(
            person_id=person_id,
            embedding=self.cipher.encrypt(vector),
            dimension=int(vector.size),
            model_version=model_version,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def list_for_person(self, person_id: uuid.UUID) -> list[FaceEmbedding]:
        """Metadatos de las muestras (el embedding sigue cifrado; no exponerlo)."""
        return list(
            self.session.scalars(
                select(FaceEmbedding)
                .where(FaceEmbedding.person_id == person_id)
                .order_by(FaceEmbedding.created_at)
            )
        )

    def delete_sample(self, person_id: uuid.UUID, sample_id: uuid.UUID) -> bool:
        result = self.session.execute(
            delete(FaceEmbedding).where(FaceEmbedding.id == sample_id, FaceEmbedding.person_id == person_id)
        )
        return result.rowcount > 0

    def count_for_person(self, person_id: uuid.UUID) -> int:
        return self.session.scalar(
            select(func.count()).select_from(FaceEmbedding).where(FaceEmbedding.person_id == person_id)
        )

    def vectors_for_person(self, person_id: uuid.UUID, model_version: str) -> list[np.ndarray]:
        records = self.session.scalars(
            select(FaceEmbedding).where(
                FaceEmbedding.person_id == person_id, FaceEmbedding.model_version == model_version
            )
        )
        return [self.cipher.decrypt(r.embedding, r.dimension) for r in records]

    def delete_for_person(self, person_id: uuid.UUID) -> int:
        result = self.session.execute(delete(FaceEmbedding).where(FaceEmbedding.person_id == person_id))
        return result.rowcount

    def load_known(self, model_version: str) -> list[KnownEmbedding]:
        """Embeddings de personas activas generados con `model_version`, listos
        para cargar en `FaceRecognizer`."""
        rows = self.session.execute(
            select(FaceEmbedding, Person)
            .join(Person, FaceEmbedding.person_id == Person.id)
            .where(Person.active.is_(True), FaceEmbedding.model_version == model_version)
        )
        return [
            KnownEmbedding(
                person_id=str(person.id),
                person_name=person.full_name,
                embedding=self.cipher.decrypt(record.embedding, record.dimension),
                model_version=record.model_version,
            )
            for record, person in rows
        ]
