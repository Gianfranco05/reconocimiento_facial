"""Detector de rostros con OpenCV YuNet."""

import logging
from pathlib import Path

import cv2
import numpy as np

from app.core.exceptions import ModelNotFoundError
from app.services.face_detector import BaseFaceDetector, BoundingBox, DetectedFace, Keypoint
from app.utils.image import validate_frame

logger = logging.getLogger(__name__)

# Orden de los 5 keypoints de YuNet (columnas 4..13 de cada fila de salida).
YUNET_KEYPOINTS = (
    "right_eye",
    "left_eye",
    "nose_tip",
    "right_mouth_corner",
    "left_mouth_corner",
)


class YuNetFaceDetector(BaseFaceDetector):
    def __init__(
        self,
        model_path: Path,
        min_confidence: float = 0.6,
        max_faces: int = 10,
        nms_threshold: float = 0.3,
    ) -> None:
        super().__init__(max_faces)
        model_path = Path(model_path)
        if not model_path.is_file():
            raise ModelNotFoundError(
                f"No se encontró el modelo YuNet en '{model_path}'. "
                "Ejecutá 'python -m app.cli.download_models' desde backend/."
            )
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), min_confidence, nms_threshold, 5000
        )
        self._input_size: tuple[int, int] = (320, 320)
        logger.info("YuNet face detector initialized (min_confidence=%.2f)", min_confidence)

    def detect(self, frame: np.ndarray, timestamp_ms: int | None = None) -> list[DetectedFace]:
        # YuNet no usa tracking: cada frame se procesa de forma independiente,
        # por eso `timestamp_ms` se ignora.
        frame = validate_frame(frame)
        height, width = frame.shape[:2]
        if self._input_size != (width, height):
            self._detector.setInputSize((width, height))
            self._input_size = (width, height)

        _, rows = self._detector.detect(frame)
        if rows is None:
            return []
        return self._finalize([self._to_face(row, width, height) for row in rows])

    @staticmethod
    def _to_face(row: np.ndarray, width: int, height: int) -> DetectedFace:
        x, y, w, h = (float(v) for v in row[:4])
        keypoints = [
            Keypoint(name, float(row[4 + 2 * i]), float(row[5 + 2 * i]))
            for i, name in enumerate(YUNET_KEYPOINTS)
        ]
        return DetectedFace(BoundingBox.clipped(x, y, x + w, y + h, width, height), float(row[14]), keypoints)
