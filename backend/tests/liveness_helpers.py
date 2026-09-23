"""Utilidades para probar landmarks y liveness con fotos reales.

`close_eyes` simula ojos cerrados pintando cada ojo con el color de la piel
de debajo y una línea de pestañas. Con las 5 fotos de fixtures, el EAR medido
por el landmarker cae al 24-55 % del valor con ojos abiertos: sirve para probar
la detección de parpadeo de punta a punta sin fotos reales con ojos cerrados.
"""

import cv2
import numpy as np

from app.services.landmark_service import LandmarkService

RIGHT_EYE_CONTOUR = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
LEFT_EYE_CONTOUR = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]


def close_eyes(image: np.ndarray, landmarks: LandmarkService) -> np.ndarray:
    [face] = landmarks.detect(image)
    out = image.copy()
    for contour in (RIGHT_EYE_CONTOUR, LEFT_EYE_CONTOUR):
        polygon = face.points[contour].astype(np.int32)
        x, y, w, h = cv2.boundingRect(polygon)
        skin = image[y + h + 2 : y + h + 2 + max(4, h // 2), x : x + w].reshape(-1, 3).mean(axis=0)
        cv2.fillPoly(out, [cv2.convexHull(polygon)], skin.tolist())
        lash_y = int(polygon[:, 1].mean()) + h // 4
        cv2.line(out, (x, lash_y), (x + w, lash_y), (40, 40, 60), max(2, h // 6))
    return cv2.GaussianBlur(out, (3, 3), 0)


def rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    """Rota la imagen (grados positivos = antihorario)."""
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h))
