"""Orquesta detección -> embedding -> comparación para cada rostro de un frame.

Cada rostro se procesa de forma independiente: si uno falla (por ejemplo, es
demasiado chico), los demás se reconocen igual.
"""

import logging
from dataclasses import dataclass

import numpy as np

from app.core.config import Settings
from app.core.exceptions import (
    ConfigurationError,
    EmbeddingError,
    FaceNotFoundError,
    FaceTooSmallError,
    MultipleFacesError,
)
from app.services.embedding_service import FaceEmbedder, SFaceEmbedder
from app.services.face_detector import BaseFaceDetector, DetectedFace, DetectionMode, create_face_detector
from app.services.face_recognizer import FaceRecognizer, RecognitionResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaceAnalysis:
    face: DetectedFace
    # None si no se pudo generar el embedding; el motivo queda en `error`.
    recognition: RecognitionResult | None
    error: str | None = None


class RecognitionPipeline:
    def __init__(
        self,
        detector: BaseFaceDetector,
        embedder: FaceEmbedder,
        recognizer: FaceRecognizer,
        min_face_size: int = 40,
    ) -> None:
        if embedder.model_version != recognizer.model_version:
            raise ConfigurationError("El embedder y el recognizer usan versiones de modelo distintas.")
        self.detector = detector
        self.embedder = embedder
        self.recognizer = recognizer
        self.min_face_size = min_face_size

    def process(self, frame: np.ndarray, timestamp_ms: int | None = None) -> list[FaceAnalysis]:
        faces = self.detector.detect(frame, timestamp_ms)
        return [self._analyze(frame, face) for face in faces]

    def detect_single_face(self, frame: np.ndarray) -> DetectedFace:
        """Para el registro de una persona: exige exactamente un rostro utilizable."""
        faces = self.detector.detect(frame)
        if not faces:
            raise FaceNotFoundError("No se detectó ningún rostro en la imagen.")
        if len(faces) > 1:
            raise MultipleFacesError(f"Se detectaron {len(faces)} rostros; el registro requiere exactamente uno.")
        self._check_size(faces[0])
        return faces[0]

    def extract_single_embedding(self, frame: np.ndarray) -> np.ndarray:
        return self.embedder.embed(frame, self.detect_single_face(frame))

    def close(self) -> None:
        self.detector.close()

    def __enter__(self) -> "RecognitionPipeline":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _analyze(self, frame: np.ndarray, face: DetectedFace) -> FaceAnalysis:
        try:
            self._check_size(face)
            embedding = self.embedder.embed(frame, face)
        except (FaceTooSmallError, EmbeddingError) as exc:
            logger.debug("Face skipped: %s", exc)
            return FaceAnalysis(face, None, str(exc))
        return FaceAnalysis(face, self.recognizer.recognize(embedding))

    def _check_size(self, face: DetectedFace) -> None:
        if min(face.bbox.width, face.bbox.height) < self.min_face_size:
            raise FaceTooSmallError(
                f"Rostro de {face.bbox.width}x{face.bbox.height}px; el mínimo es {self.min_face_size}px."
            )


def build_recognition_pipeline(settings: Settings, mode: DetectionMode = DetectionMode.IMAGE) -> RecognitionPipeline:
    if settings.face_detector_backend != "yunet":
        raise ConfigurationError(
            "El reconocimiento requiere FACE_DETECTOR_BACKEND=yunet "
            f"(actual: {settings.face_detector_backend})."
        )
    embedder = SFaceEmbedder(settings.sface_model_path)
    recognizer = FaceRecognizer(settings.face_recognition_threshold, embedder.model_version, embedder.dimension)
    detector = create_face_detector(settings, mode)
    return RecognitionPipeline(detector, embedder, recognizer, settings.min_face_size)
