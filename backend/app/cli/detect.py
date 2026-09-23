"""Demo de detección facial por consola.

Uso (desde backend/):
    python -m app.cli.detect                    # webcam (CAMERA_INDEX)
    python -m app.cli.detect --camera 1         # otra webcam
    python -m app.cli.detect --video clip.mp4   # archivo de vídeo
    python -m app.cli.detect --image foto.jpg   # imagen suelta

Tecla 'q' o ESC para salir.
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2

from app.core.config import get_settings
from app.core.exceptions import FaceTrackError
from app.core.logging import setup_logging
from app.services.camera_service import CameraService, VideoSource
from app.services.face_detector import BaseFaceDetector, DetectionMode, create_face_detector
from app.utils.drawing import draw_faces, draw_status
from app.utils.image import decode_image

logger = logging.getLogger("facetrack.detect")
WINDOW_TITLE = "FaceTrack - Deteccion facial"


def _build_detector(mode: DetectionMode) -> BaseFaceDetector:
    return create_face_detector(get_settings(), mode)


def should_quit() -> bool:
    key = cv2.waitKey(1) & 0xFF
    return key in (ord("q"), 27)


def run_image(path: Path) -> None:
    image = decode_image(path.read_bytes())
    with _build_detector(DetectionMode.IMAGE) as detector:
        faces = detector.detect(image)
    logger.info("%d face(s) detected in %s", len(faces), path.name)
    draw_faces(image, faces)
    draw_status(image, f"Rostros: {len(faces)}")
    cv2.imshow(WINDOW_TITLE, image)
    cv2.waitKey(0)


def run_stream(source: VideoSource) -> None:
    settings = get_settings()
    previous_count = -1
    with _build_detector(DetectionMode.VIDEO) as detector, CameraService(source, settings.camera_fps) as camera:
        logger.info("Press 'q' to quit")
        for frame in camera.frames():
            faces = detector.detect(frame)
            if len(faces) != previous_count:
                logger.info("%d face(s) detected", len(faces))
                previous_count = len(faces)
            draw_faces(frame, faces)
            draw_status(frame, f"Rostros: {len(faces)}")
            cv2.imshow(WINDOW_TITLE, frame)
            if should_quit():
                break
        else:
            logger.warning("Video source ended or stopped delivering frames")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detección facial en tiempo real (FaceTrack).")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--camera", type=int, help="Índice de la webcam (por defecto CAMERA_INDEX).")
    source.add_argument("--video", type=Path, help="Ruta a un archivo de vídeo.")
    source.add_argument("--image", type=Path, help="Ruta a una imagen.")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level)

    try:
        if args.image:
            run_image(args.image)
        elif args.video:
            if not args.video.is_file():
                raise FileNotFoundError(f"No existe el vídeo '{args.video}'.")
            run_stream(str(args.video))
        else:
            run_stream(args.camera if args.camera is not None else settings.camera_index)
    except (FaceTrackError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
