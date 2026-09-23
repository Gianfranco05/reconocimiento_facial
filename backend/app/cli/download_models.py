"""Descarga explícita de los modelos de visión a la carpeta `models/`.

Uso (desde backend/):
    python -m app.cli.download_models

Los modelos no se descargan en tiempo de ejecución: el sistema procesa todo
localmente y falla con un mensaje claro si falta un modelo.
"""

import logging
import sys
import urllib.request

from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger("facetrack.models")

MODELS = {
    "blaze_face_short_range.tflite": (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    ),
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}


def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    failed = False
    for filename, url in MODELS.items():
        target = settings.models_dir / filename
        if target.is_file():
            logger.info("Model already present: %s", filename)
            continue
        if not url.startswith("https://"):
            logger.error("Refusing non-HTTPS model URL for %s", filename)
            failed = True
            continue
        partial = target.with_suffix(target.suffix + ".part")
        try:
            logger.info("Downloading %s ...", filename)
            urllib.request.urlretrieve(url, partial)  # noqa: S310 — esquema https validado arriba
            partial.replace(target)
            logger.info("Model downloaded: %s", filename)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            logger.error("Could not download %s: %s", filename, exc)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
