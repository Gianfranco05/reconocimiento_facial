"""Validación de imágenes subidas.

Orden de las verificaciones (de la más barata a la más cara):
1. tipo MIME declarado dentro de los permitidos;
2. tamaño máximo (se lee como mucho `max_bytes + 1` bytes: un archivo enorme
   nunca se carga completo en memoria);
3. firma real del archivo (magic bytes) coherente con el tipo declarado;
4. decodificación real con OpenCV y límite de resolución.
"""

import numpy as np
from fastapi import UploadFile

from app.core.exceptions import InvalidImageError, PayloadTooLargeError, UnsupportedMediaError
from app.utils.image import decode_image

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_PIXELS = 4096 * 4096


def sniff_image_type(data: bytes) -> str | None:
    """Tipo MIME según la firma del archivo, o None si no es un formato soportado."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def read_upload_image(upload: UploadFile, max_bytes: int) -> np.ndarray:
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise UnsupportedMediaError(
            f"Tipo de archivo no soportado ({content_type or 'desconocido'}). Usá JPEG, PNG, WebP o BMP."
        )

    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"La imagen supera el máximo de {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise InvalidImageError("El archivo está vacío.")

    real_type = sniff_image_type(data)
    if real_type is None:
        raise InvalidImageError("El contenido del archivo no es una imagen válida.")
    if real_type != content_type:
        raise UnsupportedMediaError(
            f"El contenido del archivo ({real_type}) no coincide con el tipo declarado ({content_type})."
        )

    image = decode_image(data)
    if image.shape[0] * image.shape[1] > MAX_PIXELS:
        raise PayloadTooLargeError("La resolución de la imagen es demasiado grande (máximo 16 megapíxeles).")
    return image
