"""Gestión de usuarios del panel (login).

Uso (desde backend/):
    python -m app.cli.users create admin --role admin
    python -m app.cli.users create operador1 --role operator
    python -m app.cli.users list
    python -m app.cli.users set-password admin
    python -m app.cli.users deactivate operador1
    python -m app.cli.users activate operador1

La contraseña se pide por teclado sin mostrarla. Para automatizar (Docker,
scripts), `--password-stdin` la lee de la entrada estándar:
    echo "$ADMIN_PASSWORD" | python -m app.cli.users create admin --role admin --password-stdin

Nunca se acepta como argumento: quedaría en el historial de la terminal y en
la lista de procesos.
"""

import argparse
import getpass
import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.exceptions import FaceTrackError
from app.core.logging import setup_logging
from app.core.security import MIN_PASSWORD_LENGTH, validate_password_strength
from app.database.connection import session_scope
from app.database.models import UserRole
from app.database.repositories.user_repository import UserRepository

logger = logging.getLogger("facetrack.users")


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass(f"Contraseña (mínimo {MIN_PASSWORD_LENGTH} caracteres): ")
        if getpass.getpass("Repetir contraseña: ") != password:
            raise ValueError("Las contraseñas no coinciden.")
    validate_password_strength(password)
    return password


def cmd_create(args) -> None:
    password = read_password(args.password_stdin)
    with session_scope() as session:
        user = UserRepository(session).create(args.username, password, UserRole(args.role.upper()))
        print(f"Usuario creado: {user.username} ({user.role.value})")


def cmd_list(args) -> None:
    with session_scope() as session:
        print(f"{'Usuario':24}  {'Rol':9}  {'Estado':8}  Último ingreso")
        for user in UserRepository(session).list():
            last = user.last_login_at.strftime("%d/%m/%Y %H:%M") if user.last_login_at else "—"
            print(f"{user.username:24}  {user.role.value:9}  {'Activo' if user.active else 'Inactivo':8}  {last}")


def cmd_set_password(args) -> None:
    password = read_password(args.password_stdin)
    with session_scope() as session:
        UserRepository(session).set_password(args.username, password)
        print("Contraseña actualizada. Las sesiones abiertas de ese usuario se cerraron.")


def cmd_set_active(active: bool):
    def run(args) -> None:
        with session_scope() as session:
            UserRepository(session).set_active(args.username, active)
            print("Usuario activado." if active else "Usuario desactivado y sesiones cerradas.")

    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Usuarios del panel de FaceTrack.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Crear usuario")
    create.add_argument("username")
    create.add_argument("--role", choices=["admin", "operator"], required=True)
    create.add_argument("--password-stdin", action="store_true", help="Leer la contraseña de la entrada estándar")
    create.set_defaults(func=cmd_create)

    sub.add_parser("list", help="Listar usuarios").set_defaults(func=cmd_list)

    password = sub.add_parser("set-password", help="Cambiar contraseña")
    password.add_argument("username")
    password.add_argument("--password-stdin", action="store_true")
    password.set_defaults(func=cmd_set_password)

    for name, active in (("activate", True), ("deactivate", False)):
        command = sub.add_parser(name)
        command.add_argument("username")
        command.set_defaults(func=cmd_set_active(active))

    args = parser.parse_args(argv)
    setup_logging(get_settings().log_level)
    try:
        args.func(args)
    except (FaceTrackError, ValueError) as exc:
        logger.error("%s", exc)
        return 1
    except SQLAlchemyError as exc:
        logger.error("Database error: %s (is PostgreSQL running? docker compose up -d postgres)",
                     exc.__class__.__name__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
