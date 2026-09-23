"""Gestión de personas y registro facial por consola (hasta que exista la API).

Uso (desde backend/):
    python -m app.cli.persons add --first-name Gianfranco --last-name Canciani --email g@x.com
    python -m app.cli.persons enroll <person_id> foto1.jpg foto2.jpg ...
    python -m app.cli.persons list
    python -m app.cli.persons deactivate <person_id>
    python -m app.cli.persons delete <person_id>

`enroll` solo guarda el embedding cifrado de cada foto, nunca la imagen.
"""

import argparse
import logging
import sys
import uuid
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.exceptions import FaceTrackError
from app.core.logging import setup_logging
from app.core.security import EmbeddingCipher
from app.database.connection import session_scope
from app.database.repositories.person_repository import PersonRepository
from app.services.face_quality import FaceQualityChecker
from app.services.gallery_service import GalleryService
from app.services.recognition_pipeline import build_recognition_pipeline
from app.utils.image import decode_image

logger = logging.getLogger("facetrack.persons")


def cmd_add(args) -> None:
    with session_scope() as session:
        person = PersonRepository(session).create(args.first_name, args.last_name, args.email)
        print(f"Persona creada: {person.id}  {person.full_name}")


def cmd_list(args) -> None:
    with session_scope() as session:
        repository = PersonRepository(session)
        counts = repository.embedding_counts()
        print(f"{'ID':36}  {'Nombre':30}  {'Estado':8}  Muestras")
        for person in repository.list():
            state = "Activo" if person.active else "Inactivo"
            print(f"{person.id}  {person.full_name:30}  {state:8}  {counts.get(person.id, 0)}")


def cmd_enroll(args) -> None:
    settings = get_settings()
    cipher = EmbeddingCipher.from_settings(settings)
    with build_recognition_pipeline(settings) as pipeline:
        gallery = GalleryService(pipeline, cipher, FaceQualityChecker.from_settings(settings))
        enrolled = 0
        for path in args.photos:
            # Una sesión por foto: una foto inválida no descarta las anteriores.
            try:
                with session_scope() as session:
                    gallery.enroll_face(session, args.person_id, decode_image(path.read_bytes()))
                enrolled += 1
            except (FaceTrackError, OSError) as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
        print(f"Muestras registradas: {enrolled}/{len(args.photos)}")


def cmd_deactivate(args) -> None:
    with session_scope() as session:
        person = PersonRepository(session).update(args.person_id, active=False)
        print(f"Persona desactivada: {person.full_name}")


def cmd_delete(args) -> None:
    with session_scope() as session:
        PersonRepository(session).delete(args.person_id)
        print("Persona eliminada (con sus embeddings y asistencias).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gestión de personas (FaceTrack).")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Crear persona")
    add.add_argument("--first-name", required=True)
    add.add_argument("--last-name", default="")
    add.add_argument("--email")
    add.set_defaults(func=cmd_add)

    sub.add_parser("list", help="Listar personas").set_defaults(func=cmd_list)

    enroll = sub.add_parser("enroll", help="Registrar fotos de una persona")
    enroll.add_argument("person_id", type=uuid.UUID)
    enroll.add_argument("photos", type=Path, nargs="+")
    enroll.set_defaults(func=cmd_enroll)

    for name, func in (("deactivate", cmd_deactivate), ("delete", cmd_delete)):
        command = sub.add_parser(name)
        command.add_argument("person_id", type=uuid.UUID)
        command.set_defaults(func=func)

    args = parser.parse_args(argv)
    setup_logging(get_settings().log_level)
    try:
        args.func(args)
    except FaceTrackError as exc:
        logger.error("%s", exc)
        return 1
    except SQLAlchemyError as exc:
        # No se muestra el detalle: puede incluir la URL de conexión.
        logger.error("Database error: %s (is PostgreSQL running? docker compose up -d postgres)",
                     exc.__class__.__name__)
        logger.debug("Database error detail", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
