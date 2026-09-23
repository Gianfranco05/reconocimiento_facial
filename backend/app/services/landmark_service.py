"""Landmarks faciales con MediaPipe Face Landmarker.

Responsabilidad única: devolver, para cada rostro, los 478 puntos de la malla
facial, la apertura de los ojos (EAR) y la orientación de la cabeza. No
reconoce identidades ni decide si una persona está "viva".

Convenciones (verificadas con fotos reales, ver tests/test_landmarks.py):
- Imagen tal como la entrega la cámara (sin espejar).
- yaw   > 0: la persona gira la cabeza hacia SU derecha.
- pitch > 0: la persona mira hacia arriba.
- roll  > 0: la cabeza aparece rotada en sentido antihorario en la imagen.
Los ángulos son absolutos respecto de la cámara: una foto "de frente" suele
dar pitch de unos -10°. Para detectar movimientos conviene comparar contra
la pose inicial de cada persona, no contra 0.
"""

import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from app.core.exceptions import ModelNotFoundError
from app.services.face_detector import BoundingBox
from app.utils.image import bgr_to_rgb, validate_frame

logger = logging.getLogger(__name__)

# Índices de la malla de MediaPipe para el Eye Aspect Ratio (Soukupová y Čech,
# 2016): [comisura externa, párpado sup. 1, párpado sup. 2, comisura interna,
# párpado inf. 2, párpado inf. 1]. "left"/"right" = ojo izquierdo/derecho de la persona.
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)


@dataclass(frozen=True)
class HeadPose:
    yaw: float
    pitch: float
    roll: float


@dataclass(frozen=True)
class EyeState:
    left_ear: float
    right_ear: float
    # Puntaje de parpadeo del modelo (blendshapes, 0 = abierto, 1 = cerrado).
    # Informativo: la detección de parpadeo usa el EAR, que es explicable.
    left_blink_score: float
    right_blink_score: float

    @property
    def ear(self) -> float:
        return (self.left_ear + self.right_ear) / 2


@dataclass(frozen=True)
class FaceLandmarks:
    bbox: BoundingBox
    points: np.ndarray  # (478, 2) en píxeles
    eyes: EyeState
    head_pose: HeadPose


def eye_aspect_ratio(points: np.ndarray, indices: tuple[int, ...]) -> float:
    """EAR = (|p2-p6| + |p3-p5|) / (2 |p1-p4|). Baja cuando el ojo se cierra.
    Varía mucho entre personas (0.17 a 0.55 en las fotos de los tests): no
    usar un umbral absoluto."""
    p = points[list(indices)]
    horizontal = np.linalg.norm(p[0] - p[3])
    if horizontal < 1e-6:
        return 0.0
    vertical = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    return float(vertical / (2 * horizontal))


def head_pose_from_matrix(matrix: np.ndarray) -> HeadPose:
    """Ángulos a partir de la matriz de transformación facial de MediaPipe.

    La matriz lleva la cara canónica (que mira hacia +z) al espacio de la
    cámara (x a la derecha de la imagen, y hacia arriba, z hacia la cámara).
    """
    rotation = np.asarray(matrix, dtype=float)[:3, :3]
    normal = rotation @ np.array([0.0, 0.0, 1.0])  # hacia dónde apunta la cara
    x_axis = rotation @ np.array([1.0, 0.0, 0.0])  # línea de los ojos
    return HeadPose(
        # Nariz hacia la derecha de la imagen = la persona gira hacia SU izquierda.
        yaw=round(-math.degrees(math.atan2(normal[0], normal[2])), 1),
        pitch=round(math.degrees(math.atan2(normal[1], normal[2])), 1),
        roll=round(math.degrees(math.atan2(x_axis[1], x_axis[0])), 1),
    )


class LandmarkService:
    def __init__(self, model_path: Path, max_faces: int = 5) -> None:
        model_path = Path(model_path)
        if not model_path.is_file():
            raise ModelNotFoundError(
                f"No se encontró el modelo Face Landmarker en '{model_path}'. "
                "Ejecutá 'python -m app.cli.download_models' desde backend/."
            )
        options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=max_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._lock = threading.Lock()
        logger.info("Face landmarker initialized (max_faces=%d)", max_faces)

    def detect(self, frame: np.ndarray) -> list[FaceLandmarks]:
        frame = validate_frame(frame)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=bgr_to_rgb(frame))
        with self._lock:
            result = self._landmarker.detect(image)

        height, width = frame.shape[:2]
        faces = []
        for i, landmarks in enumerate(result.face_landmarks):
            points = np.array([[p.x * width, p.y * height] for p in landmarks], dtype=np.float32)
            blink = {c.category_name: c.score for c in result.face_blendshapes[i]} if result.face_blendshapes else {}
            eyes = EyeState(
                left_ear=round(eye_aspect_ratio(points, LEFT_EYE), 4),
                right_ear=round(eye_aspect_ratio(points, RIGHT_EYE), 4),
                left_blink_score=round(float(blink.get("eyeBlinkLeft", 0.0)), 3),
                right_blink_score=round(float(blink.get("eyeBlinkRight", 0.0)), 3),
            )
            pose = head_pose_from_matrix(result.facial_transformation_matrixes[i])
            x1, y1 = points.min(axis=0)
            x2, y2 = points.max(axis=0)
            faces.append(FaceLandmarks(BoundingBox.clipped(x1, y1, x2, y2, width, height), points, eyes, pose))
        return faces

    def close(self) -> None:
        self._landmarker.close()
