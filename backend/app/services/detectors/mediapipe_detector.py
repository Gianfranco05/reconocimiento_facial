"""Detector de rostros con MediaPipe BlazeFace (short-range)."""

import logging
import time
from pathlib import Path

import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from app.core.exceptions import ModelNotFoundError
from app.services.face_detector import BaseFaceDetector, BoundingBox, DetectedFace, DetectionMode, Keypoint
from app.utils.image import bgr_to_rgb, validate_frame

logger = logging.getLogger(__name__)

# Orden de los 6 keypoints que devuelve BlazeFace.
BLAZEFACE_KEYPOINTS = (
    "right_eye",
    "left_eye",
    "nose_tip",
    "mouth_center",
    "right_ear_tragion",
    "left_ear_tragion",
)


class MediaPipeFaceDetector(BaseFaceDetector):
    def __init__(
        self,
        model_path: Path,
        min_confidence: float = 0.5,
        max_faces: int = 10,
        mode: DetectionMode = DetectionMode.IMAGE,
    ) -> None:
        super().__init__(max_faces)
        model_path = Path(model_path)
        if not model_path.is_file():
            raise ModelNotFoundError(
                f"No se encontró el modelo de detección en '{model_path}'. "
                "Ejecutá 'python -m app.cli.download_models' desde backend/."
            )

        self.mode = mode
        self._last_timestamp_ms = -1

        running_mode = (
            vision.RunningMode.VIDEO if mode is DetectionMode.VIDEO else vision.RunningMode.IMAGE
        )
        options = vision.FaceDetectorOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=running_mode,
            min_detection_confidence=min_confidence,
        )
        self._detector = vision.FaceDetector.create_from_options(options)
        logger.info("MediaPipe face detector initialized (mode=%s, min_confidence=%.2f)", mode.value, min_confidence)

    def detect(self, frame: np.ndarray, timestamp_ms: int | None = None) -> list[DetectedFace]:
        """En modo VIDEO MediaPipe exige timestamps estrictamente crecientes; si no
        se indica uno, se usa el reloj monotónico."""
        frame = validate_frame(frame)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=bgr_to_rgb(frame))

        if self.mode is DetectionMode.VIDEO:
            result = self._detector.detect_for_video(image, self._next_timestamp(timestamp_ms))
        else:
            result = self._detector.detect(image)

        height, width = frame.shape[:2]
        return self._finalize([self._to_face(d, width, height) for d in result.detections])

    def close(self) -> None:
        self._detector.close()

    def _next_timestamp(self, timestamp_ms: int | None) -> int:
        if timestamp_ms is None:
            timestamp_ms = int(time.monotonic() * 1000)
        timestamp_ms = max(timestamp_ms, self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        return timestamp_ms

    @staticmethod
    def _to_face(detection, width: int, height: int) -> DetectedFace:
        box = detection.bounding_box
        bbox = BoundingBox.clipped(
            box.origin_x, box.origin_y, box.origin_x + box.width, box.origin_y + box.height, width, height
        )
        keypoints = [
            Keypoint(
                name=BLAZEFACE_KEYPOINTS[i] if i < len(BLAZEFACE_KEYPOINTS) else f"keypoint_{i}",
                x=kp.x * width,
                y=kp.y * height,
            )
            for i, kp in enumerate(detection.keypoints or [])
        ]
        score = float(detection.categories[0].score) if detection.categories else 0.0
        return DetectedFace(bbox, score, keypoints)
