"""Utilidades para validar y convertir imágenes."""

import cv2
import numpy as np

from app.core.exceptions import InvalidFrameError, InvalidImageError


def decode_image(data: bytes) -> np.ndarray:
    """Decodifica bytes (JPEG, PNG, ...) a un frame BGR de OpenCV.

    Valida el contenido real del archivo, no su extensión ni su MIME declarado.
    """
    if not data:
        raise InvalidImageError("La imagen está vacía.")
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImageError("El archivo no es una imagen válida o está corrupto.")
    return image


def validate_frame(frame: object) -> np.ndarray:
    """Verifica que el frame sea una imagen BGR (alto, ancho, 3) de tipo uint8."""
    if frame is None:
        raise InvalidFrameError("El frame es None.")
    if not isinstance(frame, np.ndarray):
        raise InvalidFrameError(f"Se esperaba numpy.ndarray, se recibió {type(frame).__name__}.")
    if frame.size == 0:
        raise InvalidFrameError("El frame está vacío.")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise InvalidFrameError(f"Se esperaba un frame BGR (alto, ancho, 3), se recibió {frame.shape}.")
    if frame.dtype != np.uint8:
        raise InvalidFrameError(f"Se esperaba dtype uint8, se recibió {frame.dtype}.")
    return frame


def bgr_to_rgb(frame: np.ndarray) -> np.ndarray:
    # MediaPipe exige un buffer contiguo en memoria.
    return np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
