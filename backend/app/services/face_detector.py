"""Detección de rostros: tipos comunes, interfaz y fábrica.

Responsabilidad única: recibir un frame y devolver los rostros encontrados
(bounding box, score y keypoints). Un detector no reconoce identidades,
no accede a la base de datos y no dibuja nada.

Implementaciones disponibles (en `app/services/detectors/`):
- `yunet`: OpenCV YuNet. Detecta rostros de distintos tamaños y devuelve los
  5 keypoints que necesita el reconocimiento (SFace). Backend por defecto.
- `mediapipe`: MediaPipe BlazeFace short-range. Rápido, pero solo detecta
  rostros que ocupan buena parte del encuadre; no sirve para reconocimiento.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from app.core.config import Settings


class DetectionMode(StrEnum):
    IMAGE = "image"  # imágenes sueltas e independientes
    VIDEO = "video"  # frames consecutivos de webcam o archivo de vídeo


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @classmethod
    def clipped(cls, x1: float, y1: float, x2: float, y2: float, width: int, height: int) -> "BoundingBox":
        """Crea una caja recortada a los límites de la imagen (los detectores
        pueden devolver cajas que se salen parcialmente del frame)."""
        left = min(max(int(x1), 0), width)
        top = min(max(int(y1), 0), height)
        right = min(max(int(x2), 0), width)
        bottom = min(max(int(y2), 0), height)
        return cls(left, top, right - left, bottom - top)


@dataclass(frozen=True)
class Keypoint:
    name: str
    x: float  # coordenadas en píxeles de la imagen original
    y: float


@dataclass(frozen=True)
class DetectedFace:
    bbox: BoundingBox
    score: float
    keypoints: list[Keypoint] = field(default_factory=list)

    def keypoint(self, name: str) -> Keypoint | None:
        return next((kp for kp in self.keypoints if kp.name == name), None)


class BaseFaceDetector(ABC):
    """Interfaz común de todos los detectores."""

    def __init__(self, max_faces: int) -> None:
        self.max_faces = max_faces

    @abstractmethod
    def detect(self, frame: np.ndarray, timestamp_ms: int | None = None) -> list[DetectedFace]:
        """Detecta rostros en un frame BGR. Devuelve como máximo `max_faces`
        rostros, ordenados por score descendente."""

    def close(self) -> None:  # noqa: B027 — no-op por defecto a propósito; opcional en subclases
        """Libera recursos del modelo (si los hay)."""

    def __enter__(self) -> "BaseFaceDetector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _finalize(self, faces: list[DetectedFace]) -> list[DetectedFace]:
        faces = [face for face in faces if face.bbox.width > 0 and face.bbox.height > 0]
        faces.sort(key=lambda face: face.score, reverse=True)
        return faces[: self.max_faces]


def create_face_detector(settings: Settings, mode: DetectionMode = DetectionMode.IMAGE) -> BaseFaceDetector:
    """Crea el detector configurado en `FACE_DETECTOR_BACKEND`."""
    # Imports diferidos: evitan cargar MediaPipe u OpenCV DNN si no se usan.
    if settings.face_detector_backend == "yunet":
        from app.services.detectors.yunet_detector import YuNetFaceDetector

        return YuNetFaceDetector(
            model_path=settings.yunet_model_path,
            min_confidence=settings.detection_min_confidence,
            max_faces=settings.max_faces,
        )

    from app.services.detectors.mediapipe_detector import MediaPipeFaceDetector

    return MediaPipeFaceDetector(
        model_path=settings.face_detector_model_path,
        min_confidence=settings.detection_min_confidence,
        max_faces=settings.max_faces,
        mode=mode,
    )
