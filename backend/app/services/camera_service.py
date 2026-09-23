"""Acceso a la cámara (o a un archivo de vídeo) con OpenCV.

Responsabilidad única: abrir la fuente, entregar frames a un ritmo controlado
y liberarla. No detecta ni reconoce rostros.
"""

import logging
import time
from collections.abc import Callable, Iterator

import cv2
import numpy as np

from app.core.exceptions import CameraUnavailableError

logger = logging.getLogger(__name__)

# Una fuente es el índice de una cámara (0, 1, ...) o la ruta de un vídeo.
VideoSource = int | str


class CameraService:
    def __init__(
        self,
        source: VideoSource = 0,
        fps: int = 15,
        capture_factory: Callable[[VideoSource], cv2.VideoCapture] = cv2.VideoCapture,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps debe ser mayor que 0.")
        self.source = source
        self.fps = fps
        self._capture_factory = capture_factory
        self._capture: cv2.VideoCapture | None = None
        self._last_frame_at = 0.0

    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def open(self) -> None:
        if self.is_open:
            return
        capture = self._capture_factory(self.source)
        if capture is None or not capture.isOpened():
            if capture is not None:
                capture.release()
            logger.error("Camera unavailable (source=%s)", self.source)
            raise CameraUnavailableError(
                f"No se pudo abrir la fuente de vídeo '{self.source}'. "
                "Puede que no exista, esté desconectada o en uso por otra aplicación."
            )
        self._capture = capture
        self._last_frame_at = 0.0
        logger.info("Camera initialized (source=%s, fps=%d)", self.source, self.fps)

    def read(self) -> np.ndarray | None:
        """Devuelve el siguiente frame, o None si la fuente dejó de entregar frames
        (vídeo terminado o cámara desconectada). Respeta el límite de FPS."""
        if not self.is_open:
            raise CameraUnavailableError("La cámara no está abierta. Llamá a open() primero.")

        self._throttle()
        ok, frame = self._capture.read()
        if not ok or frame is None or frame.size == 0:
            logger.warning("Could not read frame (source=%s)", self.source)
            return None
        return frame

    def frames(self) -> Iterator[np.ndarray]:
        """Itera frames hasta que la fuente se agote o falle."""
        while True:
            frame = self.read()
            if frame is None:
                return
            yield frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            logger.info("Camera released (source=%s)", self.source)

    def __enter__(self) -> "CameraService":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _throttle(self) -> None:
        min_interval = 1.0 / self.fps
        elapsed = time.monotonic() - self._last_frame_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_frame_at = time.monotonic()
