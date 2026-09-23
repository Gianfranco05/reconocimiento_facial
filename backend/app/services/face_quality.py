"""Control de calidad de una muestra facial para el registro.

Mide sobre el recorte del rostro (normalizado a 112x112 px, así las medidas
no dependen de la resolución de la foto):
- tamaño del rostro en la imagen original;
- score del detector (rostros tapados o de perfil puntúan bajo);
- nitidez: varianza del Laplaciano (baja = foto movida o desenfocada);
- iluminación: brillo medio en escala de grises (muy bajo = oscura,
  muy alto = sobreexpuesta).

Son heurísticas simples y explicables, no una garantía de calidad biométrica.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core.config import Settings
from app.core.exceptions import LowQualityFaceError
from app.services.face_detector import DetectedFace

NORMALIZED_SIZE = (112, 112)


@dataclass(frozen=True)
class FaceQuality:
    face_size: int
    detection_score: float
    sharpness: float
    brightness: float
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class FaceQualityChecker:
    min_face_size: int = 80
    min_detection_score: float = 0.8
    min_sharpness: float = 100.0
    min_brightness: float = 50.0
    max_brightness: float = 210.0

    @classmethod
    def from_settings(cls, settings: Settings) -> "FaceQualityChecker":
        return cls(
            min_face_size=settings.enrollment_min_face_size,
            min_detection_score=settings.enrollment_min_detection_score,
            min_sharpness=settings.enrollment_min_sharpness,
            min_brightness=settings.enrollment_min_brightness,
            max_brightness=settings.enrollment_max_brightness,
        )

    def assess(self, frame: np.ndarray, face: DetectedFace) -> FaceQuality:
        box = face.bbox
        crop = frame[box.y : box.y2, box.x : box.x2]
        gray = cv2.cvtColor(cv2.resize(crop, NORMALIZED_SIZE), cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())
        face_size = min(box.width, box.height)

        issues = []
        if face_size < self.min_face_size:
            issues.append(
                f"rostro demasiado chico ({face_size}px, mínimo {self.min_face_size}px): acercate a la cámara"
            )
        if face.score < self.min_detection_score:
            issues.append("rostro poco claro (tapado, de perfil o parcialmente fuera de la imagen)")
        if sharpness < self.min_sharpness:
            issues.append("imagen borrosa: mantené la cámara quieta")
        if brightness < self.min_brightness:
            issues.append("imagen demasiado oscura")
        elif brightness > self.max_brightness:
            issues.append("imagen sobreexpuesta")

        return FaceQuality(face_size, round(face.score, 3), round(sharpness, 1), round(brightness, 1), issues)

    def check(self, frame: np.ndarray, face: DetectedFace) -> FaceQuality:
        quality = self.assess(frame, face)
        if not quality.ok:
            raise LowQualityFaceError("Calidad insuficiente: " + "; ".join(quality.issues) + ".")
        return quality
