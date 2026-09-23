"""CLI de usuarios contra la base de tests."""

import io

import pytest

from app.cli import users as cli
from app.core.security import verify_password
from app.database.models import User, UserRole
from app.database.repositories.user_repository import UserRepository


@pytest.fixture
def cli_session(db_session, monkeypatch):
    """Hace que la CLI use la sesión del test (y su rollback)."""
    from contextlib import contextmanager

    @contextmanager
    def scope():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(cli, "session_scope", scope)
    return db_session


def run(monkeypatch, argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return cli.main(argv)


def test_create_with_password_from_stdin(cli_session, monkeypatch, capsys):
    assert run(monkeypatch, ["create", "Admin", "--role", "admin", "--password-stdin"], "clave-segura-1\n") == 0
    user = UserRepository(cli_session).get_by_username("admin")
    assert user.role is UserRole.ADMIN
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password("clave-segura-1", user.password_hash)
    assert "clave-segura-1" not in capsys.readouterr().out


@pytest.mark.parametrize("password", ["corta1", "sololetrassinnumeros", "1234567890123"])
def test_weak_passwords_rejected(cli_session, monkeypatch, password):
    assert run(monkeypatch, ["create", "operador", "--role", "operator", "--password-stdin"], password + "\n") == 1
    assert cli_session.query(User).count() == 0


def test_invalid_username_rejected(cli_session, monkeypatch):
    assert run(monkeypatch, ["create", "a b", "--role", "operator", "--password-stdin"], "clave-segura-1\n") == 1


def test_duplicate_username_rejected(cli_session, monkeypatch):
    assert run(monkeypatch, ["create", "operador", "--role", "operator", "--password-stdin"], "clave-segura-1\n") == 0
    assert run(monkeypatch, ["create", "OPERADOR", "--role", "admin", "--password-stdin"], "clave-segura-2\n") == 1


def test_set_password_and_deactivate_invalidate_sessions(cli_session, monkeypatch):
    assert run(monkeypatch, ["create", "operador", "--role", "operator", "--password-stdin"], "clave-segura-1\n") == 0
    user = UserRepository(cli_session).get_by_username("operador")
    version = user.token_version
    assert run(monkeypatch, ["set-password", "operador", "--password-stdin"], "clave-nueva-22\n") == 0
    assert verify_password("clave-nueva-22", user.password_hash)
    assert run(monkeypatch, ["deactivate", "operador"]) == 0
    assert user.active is False and user.token_version == version + 2


def test_interactive_password_mismatch(cli_session, monkeypatch):
    answers = iter(["clave-segura-1", "otra-clave-22"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create", "operador", "--role", "operator"]) == 1
