"""Generación de embeddings faciales.

Un embedding es un vector que representa matemáticamente un rostro: rostros de
la misma persona producen vectores cercanos. El resto del sistema solo depende
de `FaceEmbedder` y de `cosine_distance`, así que el modelo concreto (hoy SFace)
se puede reemplazar sin tocar el reconocedor, la base de datos ni la API.

Todos los embeddings se devuelven normalizados (norma L2 = 1) y en float32.
Son datos biométricos sensibles: nunca se loguean ni se devuelven por la API.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

from app.core.exceptions import EmbeddingError, InvalidEmbeddingError, ModelNotFoundError
from app.services.detectors.yunet_detector import YUNET_KEYPOINTS
from app.services.face_detector import DetectedFace
from app.utils.image import validate_frame

logger = logging.getLogger(__name__)


def validate_embedding(embedding: object, dimension: int | None = None) -> np.ndarray:
    """Verifica que sea un vector 1D finito y no nulo; lo devuelve normalizado."""
    if not isinstance(embedding, np.ndarray):
        raise InvalidEmbeddingError(f"Se esperaba numpy.ndarray, se recibió {type(embedding).__name__}.")
    if embedding.ndim != 1 or embedding.size == 0:
        raise InvalidEmbeddingError(f"Se esperaba un vector 1D no vacío, se recibió forma {embedding.shape}.")
    if not np.issubdtype(embedding.dtype, np.number):
        raise InvalidEmbeddingError(f"El embedding debe ser numérico, se recibió {embedding.dtype}.")
    if dimension is not None and embedding.size != dimension:
        raise InvalidEmbeddingError(f"Se esperaban {dimension} dimensiones, se recibieron {embedding.size}.")
    vector = embedding.astype(np.float32)
    if not np.all(np.isfinite(vector)):
        raise InvalidEmbeddingError("El embedding contiene NaN o infinitos.")
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        raise InvalidEmbeddingError("El embedding es un vector nulo.")
    return vector / norm


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Distancia coseno entre dos embeddings normalizados: 0 (idénticos) a 2 (opuestos)."""
    return float(np.clip(1.0 - float(np.dot(a, b)), 0.0, 2.0))


class FaceEmbedder(ABC):
    """Interfaz de cualquier modelo de embeddings faciales."""

    model_version: str
    dimension: int

    @abstractmethod
    def embed(self, frame: np.ndarray, face: DetectedFace) -> np.ndarray:
        """Devuelve el embedding normalizado de `face` dentro de `frame` (BGR)."""


class SFaceEmbedder(FaceEmbedder):
    """OpenCV SFace (128 dimensiones). Requiere los 5 keypoints de YuNet para
    alinear el rostro antes de extraer el embedding."""

    model_version = "sface_2021dec"
    dimension = 128

    def __init__(self, model_path: Path) -> None:
        model_path = Path(model_path)
        if not model_path.is_file():
            raise ModelNotFoundError(
                f"No se encontró el modelo SFace en '{model_path}'. "
                "Ejecutá 'python -m app.cli.download_models' desde backend/."
            )
        self._recognizer = cv2.FaceRecognizerSF.create(str(model_path), "")
        logger.info("SFace embedder initialized (model_version=%s)", self.model_version)

    def embed(self, frame: np.ndarray, face: DetectedFace) -> np.ndarray:
        frame = validate_frame(frame)
        aligned = self._recognizer.alignCrop(frame, self._to_yunet_row(face))
        feature = self._recognizer.feature(aligned)
        try:
            return validate_embedding(np.asarray(feature).flatten(), self.dimension)
        except InvalidEmbeddingError as exc:
            raise EmbeddingError(f"El modelo generó un embedding inválido: {exc}") from exc

    @staticmethod
    def _to_yunet_row(face: DetectedFace) -> np.ndarray:
        """Reconstruye la fila de 15 valores que `alignCrop` espera de YuNet."""
        coords: list[float] = []
        for name in YUNET_KEYPOINTS:
            kp = face.keypoint(name)
            if kp is None:
                raise EmbeddingError(
                    f"Falta el keypoint '{name}'. SFace necesita los 5 keypoints de YuNet "
                    "(FACE_DETECTOR_BACKEND=yunet)."
                )
            coords += [kp.x, kp.y]
        box = face.bbox
        return np.array([box.x, box.y, box.width, box.height, *coords, face.score], dtype=np.float32)
