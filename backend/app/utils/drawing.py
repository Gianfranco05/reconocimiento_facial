"""Dibujo de resultados sobre frames (solo presentación, sin lógica de visión)."""

import cv2
import numpy as np

from app.services.face_detector import DetectedFace

GREEN = (0, 200, 0)
RED = (0, 0, 230)
GRAY = (160, 160, 160)
YELLOW = (0, 220, 255)


def _label(frame: np.ndarray, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    cv2.putText(frame, text, (x, max(y - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)


def _keypoints(frame: np.ndarray, face: DetectedFace) -> None:
    for kp in face.keypoints:
        cv2.circle(frame, (int(kp.x), int(kp.y)), 2, YELLOW, -1)


def draw_faces(frame: np.ndarray, faces: list[DetectedFace], show_keypoints: bool = True) -> np.ndarray:
    for face in faces:
        box = face.bbox
        cv2.rectangle(frame, (box.x, box.y), (box.x2, box.y2), GREEN, 2)
        _label(frame, f"{face.score:.0%}", box.x, box.y, GREEN)
        if show_keypoints:
            _keypoints(frame, face)
    return frame


def draw_recognition(frame: np.ndarray, face: DetectedFace, name: str | None, confidence: float) -> np.ndarray:
    """Dibuja un rostro reconocido (verde, nombre y confianza), desconocido (rojo)
    o no evaluable (gris, `confidence` < 0)."""
    box = face.bbox
    if confidence < 0:
        color, text = GRAY, "?"
    elif name:
        color, text = GREEN, f"{name} {confidence:.0%}"
    else:
        color, text = RED, "Desconocido"
    cv2.rectangle(frame, (box.x, box.y), (box.x2, box.y2), color, 2)
    _label(frame, text, box.x, box.y, color)
    return frame


def draw_status(frame: np.ndarray, text: str) -> np.ndarray:
    cv2.putText(frame, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2, cv2.LINE_AA)
    return frame
