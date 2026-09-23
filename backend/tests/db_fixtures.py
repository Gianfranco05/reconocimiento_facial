"""Fixtures de PostgreSQL para los tests.

Usan TEST_DATABASE_URL (por defecto la base `facetrack_test` del contenedor de
docker-compose), nunca la base real. Al inicio de la sesión se aplican las
migraciones de Alembic desde cero; cada test corre dentro de una transacción
que se revierte al terminar.

Si PostgreSQL no responde, los tests de base se saltean (se verifica una sola
vez, con timeout corto). Con FACETRACK_REQUIRE_DB=1 fallan en vez de
saltearse: usarlo en CI para que una base caída no pase desapercibida.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.core.security import EmbeddingCipher
from app.database.connection import normalize_database_url

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return get_settings().test_database_url


_db_unavailable: str | None = None


@pytest.fixture(scope="session")
def db_engine(test_database_url) -> Engine:
    global _db_unavailable
    # pytest reintenta un fixture de sesión que falló en cada test: se recuerda
    # el resultado para no esperar el timeout de conexión una y otra vez.
    if _db_unavailable is None:
        engine = create_engine(
            normalize_database_url(test_database_url), pool_pre_ping=True, connect_args={"connect_timeout": 3}
        )
        try:
            engine.connect().close()
            _db_unavailable = ""
        except OperationalError:
            engine.dispose()
            _db_unavailable = "PostgreSQL de tests no disponible (docker compose up -d postgres)"
    if _db_unavailable:
        if os.environ.get("FACETRACK_REQUIRE_DB") == "1":
            pytest.fail(_db_unavailable)
        pytest.skip(_db_unavailable)
    config = alembic_config(test_database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def committing_session_factory(db_engine):
    """Sesiones que hacen commit de verdad (para probar concurrencia).
    Los tests que la usan deben limpiar lo que crean."""
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def cipher() -> EmbeddingCipher:
    return EmbeddingCipher(Fernet.generate_key())
