"""Une el motor de reconocimiento con la base de datos: registrar rostros de
una persona y cargar los embeddings conocidos en el reconocedor."""

import logging
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.core.exceptions import FaceConflictError
from app.core.security import EmbeddingCipher
from app.database.models import FaceEmbedding
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.person_repository import PersonRepository
from app.services.embedding_service import cosine_distance
from app.services.face_quality import FaceQuality, FaceQualityChecker
from app.services.face_recognizer import FaceRecognizer
from app.services.recognition_pipeline import RecognitionPipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrolledFace:
    record: FaceEmbedding
    quality: FaceQuality | None


class GalleryService:
    def __init__(
        self,
        pipeline: RecognitionPipeline,
        cipher: EmbeddingCipher,
        quality_checker: FaceQualityChecker | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.cipher = cipher
        self.quality_checker = quality_checker

    def enroll_face(self, session: Session, person_id: uuid.UUID, frame: np.ndarray) -> EnrolledFace:
        """Genera el embedding de la única cara de `frame` y lo guarda cifrado.
        No guarda la imagen. Llamar a `reload` después del commit para que el
        reconocedor en memoria la tenga en cuenta.

        Rechaza la muestra si no alcanza la calidad mínima (LowQualityFaceError),
        si no coincide con las muestras previas de la persona o si coincide con
        otra persona registrada (FaceConflictError): una foto equivocada
        contaminaría el reconocimiento de ambas.
        """
        person = PersonRepository(session).get(person_id)
        face = self.pipeline.detect_single_face(frame)
        quality = self.quality_checker.check(frame, face) if self.quality_checker else None
        embedding = self.pipeline.embedder.embed(frame, face)
        repository = EmbeddingRepository(session, self.cipher)
        model_version = self.pipeline.embedder.model_version
        threshold = self.pipeline.recognizer.threshold

        own_samples = repository.vectors_for_person(person.id, model_version)
        if own_samples and min(cosine_distance(embedding, v) for v in own_samples) > threshold:
            raise FaceConflictError(
                f"El rostro no coincide con las muestras ya registradas de {person.full_name}."
            )

        others = FaceRecognizer(threshold, model_version, self.pipeline.embedder.dimension)
        others.load([k for k in repository.load_known(model_version) if k.person_id != str(person.id)])
        match = others.recognize(embedding)
        if match.recognized:
            raise FaceConflictError(f"El rostro coincide con otra persona registrada ({match.person_name}).")

        record = repository.add(person.id, embedding, model_version)
        logger.info("Face sample enrolled for %s", person.full_name)
        return EnrolledFace(record, quality)

    def reload(self, session: Session) -> int:
        """Recarga el reconocedor con los embeddings de personas activas.
        Devuelve la cantidad de muestras cargadas."""
        entries = EmbeddingRepository(session, self.cipher).load_known(self.pipeline.embedder.model_version)
        self.pipeline.recognizer.load(entries)
        return len(entries)
