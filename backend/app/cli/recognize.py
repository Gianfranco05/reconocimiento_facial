"""Demo de reconocimiento facial por consola.

Las personas conocidas se cargan de PostgreSQL (`--db`, registradas con
`python -m app.cli.persons`) o de una carpeta con una subcarpeta por persona:

    data/gallery/
    ├── Gianfranco/   frontal.jpg, izquierda.jpg, ...
    └── Juan/         foto1.jpg, ...

Con `--gallery` cada foto debe contener exactamente un rostro; los embeddings
se calculan al arrancar y viven solo en memoria.

Con `--db` los reconocimientos se registran como eventos (con cooldown) y,
con `--attendance`, además se registra la asistencia (ENTRY / EXIT).

Uso (desde backend/):
    python -m app.cli.recognize --db
    python -m app.cli.recognize --db --attendance
    python -m app.cli.recognize --gallery ../data/gallery
    python -m app.cli.recognize --gallery ../data/gallery --video clip.mp4
    python -m app.cli.recognize --gallery ../data/gallery --image grupo.jpg
"""

import argparse
import json
import logging
import sys
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import cv2
from sqlalchemy.exc import SQLAlchemyError

from app.cli.detect import WINDOW_TITLE, should_quit
from app.core.config import get_settings
from app.core.exceptions import FaceTrackError
from app.core.logging import setup_logging
from app.core.security import EmbeddingCipher
from app.database.connection import session_scope
from app.services.attendance_service import AttendanceService
from app.services.camera_service import CameraService, VideoSource
from app.services.cooldown import RecognitionCooldown
from app.services.event_service import RecognitionEventService
from app.services.face_detector import DetectionMode
from app.services.face_recognizer import KnownEmbedding, RecognitionResult
from app.services.gallery_service import GalleryService
from app.services.recognition_pipeline import FaceAnalysis, RecognitionPipeline, build_recognition_pipeline
from app.utils.drawing import draw_recognition, draw_status
from app.utils.image import decode_image

logger = logging.getLogger("facetrack.recognize")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ResultsHandler = Callable[[list[RecognitionResult]], None]


def load_gallery_from_db(pipeline: RecognitionPipeline) -> None:
    gallery = GalleryService(pipeline, EmbeddingCipher.from_settings(get_settings()))
    with session_scope() as session:
        if gallery.reload(session) == 0:
            logger.warning("No enrolled faces in the database: every face will be reported as unknown")


def build_db_handler(record_attendance: bool) -> ResultsHandler:
    """Registra eventos (con cooldown) y, opcionalmente, asistencia."""
    settings = get_settings()
    events = RecognitionEventService(
        RecognitionCooldown(settings.recognition_cooldown_seconds), settings.camera_id, settings.save_events
    )
    attendance = AttendanceService(timedelta(minutes=settings.attendance_min_interval_minutes), settings.tz)

    def handle(results: list[RecognitionResult]) -> None:
        with session_scope() as session:
            processed = events.process(session, results)
            if record_attendance:
                for result in processed.fresh:
                    if result.recognized:
                        attendance.register(session, uuid.UUID(result.person_id), result.confidence)

    return handle


def load_gallery(pipeline: RecognitionPipeline, gallery_dir: Path) -> None:
    if not gallery_dir.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de galería '{gallery_dir}'.")

    entries: list[KnownEmbedding] = []
    for person_dir in sorted(p for p in gallery_dir.iterdir() if p.is_dir()):
        for image_path in sorted(person_dir.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                embedding = pipeline.extract_single_embedding(decode_image(image_path.read_bytes()))
            except FaceTrackError as exc:
                logger.warning("Skipping %s/%s: %s", person_dir.name, image_path.name, exc)
                continue
            entries.append(
                KnownEmbedding(person_dir.name, person_dir.name, embedding, pipeline.embedder.model_version)
            )
    if not entries:
        logger.warning("Gallery is empty: every face will be reported as unknown")
    pipeline.recognizer.load(entries)


def to_json(analyses: list[FaceAnalysis]) -> dict:
    """Formato equivalente al que devolverá POST /api/reconocimiento/image."""
    results = []
    for analysis in analyses:
        result = analysis.recognition
        results.append(
            {
                "recognized": bool(result and result.recognized),
                "person_id": result.person_id if result else None,
                "name": result.person_name if result and result.recognized else "Desconocido",
                "confidence": result.confidence if result else 0.0,
                "distance": result.distance if result else None,
                "bbox": vars(analysis.face.bbox),
                "error": analysis.error,
            }
        )
    return {"faces_detected": len(analyses), "results": results}


def draw(frame, analyses: list[FaceAnalysis]) -> None:
    for analysis in analyses:
        result = analysis.recognition
        if result is None:
            draw_recognition(frame, analysis.face, None, -1)
        else:
            draw_recognition(frame, analysis.face, result.person_name, result.confidence)
    draw_status(frame, f"Rostros: {len(analyses)}")


def _results(analyses: list[FaceAnalysis]) -> list[RecognitionResult]:
    return [a.recognition for a in analyses if a.recognition is not None]


def run_image(
    pipeline: RecognitionPipeline, path: Path, on_results: ResultsHandler | None, headless: bool = False
) -> None:
    image = decode_image(path.read_bytes())
    analyses = pipeline.process(image)
    if on_results:
        on_results(_results(analyses))
    print(json.dumps(to_json(analyses), ensure_ascii=False, indent=2))
    if headless:
        return
    draw(image, analyses)
    cv2.imshow(WINDOW_TITLE, image)
    cv2.waitKey(0)


def run_stream(
    pipeline: RecognitionPipeline, source: VideoSource, on_results: ResultsHandler | None, headless: bool = False
) -> None:
    settings = get_settings()
    previous: list[str] = []
    with CameraService(source, settings.camera_fps) as camera:
        logger.info("Press 'q' to quit")
        for frame in camera.frames():
            analyses = pipeline.process(frame)
            if on_results:
                on_results(_results(analyses))
            if not headless:
                draw(frame, analyses)
                cv2.imshow(WINDOW_TITLE, frame)
                if should_quit():
                    break
            if on_results:
                continue
            # Sin base de datos: loguear solo cuando cambia quién está en cuadro.
            current = sorted(
                a.recognition.person_name if a.recognition and a.recognition.recognized else "?"
                for a in analyses
            )
            if current != previous:
                for name in current:
                    if name == "?":
                        logger.warning("Unknown face detected")
                    else:
                        logger.info("Person recognized: %s", name)
                previous = current


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconocimiento facial (FaceTrack).")
    known = parser.add_mutually_exclusive_group(required=True)
    known.add_argument("--db", action="store_true", help="Cargar personas de PostgreSQL y registrar eventos.")
    known.add_argument("--gallery", type=Path, help="Carpeta con una subcarpeta por persona.")
    parser.add_argument("--attendance", action="store_true", help="Registrar asistencia (requiere --db).")
    parser.add_argument("--headless", action="store_true", help="Sin ventana (servidores o pruebas).")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--camera", type=int, help="Índice de la webcam (por defecto CAMERA_INDEX).")
    source.add_argument("--video", type=Path, help="Ruta a un archivo de vídeo.")
    source.add_argument("--image", type=Path, help="Ruta a una imagen.")
    args = parser.parse_args(argv)
    if args.attendance and not args.db:
        parser.error("--attendance requiere --db")

    settings = get_settings()
    setup_logging(settings.log_level)

    try:
        mode = DetectionMode.IMAGE if args.image else DetectionMode.VIDEO
        with build_recognition_pipeline(settings, mode) as pipeline:
            if args.db:
                load_gallery_from_db(pipeline)
                on_results = build_db_handler(args.attendance)
            else:
                load_gallery(pipeline, args.gallery)
                on_results = None
            if args.image:
                run_image(pipeline, args.image, on_results, args.headless)
            elif args.video:
                if not args.video.is_file():
                    raise FileNotFoundError(f"No existe el vídeo '{args.video}'.")
                run_stream(pipeline, str(args.video), on_results, args.headless)
            else:
                source = args.camera if args.camera is not None else settings.camera_index
                run_stream(pipeline, source, on_results, args.headless)
    except (FaceTrackError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        return 1
    except SQLAlchemyError as exc:
        # No se muestra el detalle: puede incluir la URL de conexión.
        logger.error("Database error: %s (is PostgreSQL running? docker compose up -d postgres)",
                     exc.__class__.__name__)
        logger.debug("Database error detail", exc_info=True)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
