"""Reconocimiento: compara un embedding contra los embeddings conocidos.

Regla de decisión (no se asume que "el más parecido" es automáticamente la
persona correcta):

    distancia al más cercano <= threshold  ->  conocido
    distancia al más cercano >  threshold  ->  desconocido

Una persona puede tener varias muestras (frontal, perfil, ...): se usa la
distancia a su muestra más cercana.

`confidence` es una puntuación heurística derivada de la distancia, NO una
probabilidad calibrada:

    confidence = 1 - distance / (2 * threshold)

Vale 1.0 con distancia 0 y 0.5 justo en el threshold, así que un rostro
reconocido siempre tiene confidence en (0.5, 1.0]. Un desconocido tiene 0.
Este módulo no conoce el modelo de embeddings ni la base de datos.
"""

import logging
from dataclasses import dataclass

import numpy as np

from app.core.exceptions import InvalidEmbeddingError
from app.services.embedding_service import validate_embedding

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnownEmbedding:
    person_id: str
    person_name: str
    embedding: np.ndarray
    model_version: str


@dataclass(frozen=True)
class RecognitionResult:
    recognized: bool
    person_id: str | None
    person_name: str | None
    # Distancia al candidato más cercano (None si no hay nadie registrado).
    distance: float | None
    confidence: float

    @classmethod
    def unknown(cls, distance: float | None = None) -> "RecognitionResult":
        return cls(False, None, None, distance, 0.0)


class FaceRecognizer:
    def __init__(self, threshold: float, model_version: str, dimension: int) -> None:
        self.threshold = threshold
        self.model_version = model_version
        self.dimension = dimension
        # (muestras, matriz de embeddings) se reemplazan juntas en una sola
        # asignación, así una recarga concurrente nunca mezcla galerías.
        self._gallery: tuple[tuple[KnownEmbedding, ...], np.ndarray] = (
            (),
            np.empty((0, dimension), dtype=np.float32),
        )

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        if not 0.0 < value <= 2.0:
            raise ValueError("El threshold debe estar en (0, 2].")
        self._threshold = float(value)

    @property
    def known_people(self) -> int:
        return len({entry.person_id for entry in self._gallery[0]})

    @property
    def sample_count(self) -> int:
        return len(self._gallery[0])

    def load(self, entries: list[KnownEmbedding]) -> None:
        """Reemplaza por completo los embeddings conocidos."""
        validated = tuple(self._validate_entry(entry) for entry in entries)
        self._set_entries(validated)
        logger.info("Recognizer loaded %d sample(s) of %d person(s)", self.sample_count, self.known_people)

    def add(self, entry: KnownEmbedding) -> None:
        self._set_entries(self._gallery[0] + (self._validate_entry(entry),))

    def remove_person(self, person_id: str) -> None:
        self._set_entries(tuple(e for e in self._gallery[0] if e.person_id != person_id))

    def recognize(self, embedding: np.ndarray) -> RecognitionResult:
        query = validate_embedding(embedding, self.dimension)
        entries, matrix = self._gallery
        if not entries:
            return RecognitionResult.unknown()

        distances = np.clip(1.0 - matrix @ query, 0.0, 2.0)
        best = int(np.argmin(distances))
        distance = float(distances[best])

        if distance > self._threshold:
            logger.debug("Unknown face (best distance %.3f)", distance)
            return RecognitionResult.unknown(round(distance, 4))

        match = entries[best]
        confidence = max(0.0, min(1.0, 1.0 - distance / (2 * self._threshold)))
        logger.debug("Match: %s (distance %.3f)", match.person_name, distance)
        return RecognitionResult(True, match.person_id, match.person_name, round(distance, 4), round(confidence, 4))

    def _validate_entry(self, entry: KnownEmbedding) -> KnownEmbedding:
        if entry.model_version != self.model_version:
            raise InvalidEmbeddingError(
                f"Embedding generado con '{entry.model_version}', se esperaba '{self.model_version}'. "
                "Los embeddings de modelos distintos no son comparables."
            )
        vector = validate_embedding(entry.embedding, self.dimension)
        return KnownEmbedding(entry.person_id, entry.person_name, vector, entry.model_version)

    def _set_entries(self, entries: tuple[KnownEmbedding, ...]) -> None:
        matrix = (
            np.stack([e.embedding for e in entries])
            if entries
            else np.empty((0, self.dimension), dtype=np.float32)
        )
        self._gallery = (entries, matrix)
