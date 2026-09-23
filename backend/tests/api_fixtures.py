"""Fixtures y utilidades compartidas por los tests de la API.

Se registran en conftest.py: cualquier test puede pedir `client` (sesión de
administrador), `operator_client`, `anon_client`, `app` o `engine`.
"""

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.database.models import UserRole
from app.database.repositories.user_repository import UserRepository
from app.main import create_app
from app.services.engine import FaceTrackEngine


def jpeg(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".jpg", image)
    assert ok
    return data.tobytes()


def png(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image)
    assert ok
    return data.tobytes()


def upload(data: bytes, content_type: str = "image/jpeg", name: str = "foto.jpg") -> dict:
    return {"image": (name, data, content_type)}


ADMIN_PASSWORD = "admin-clave-123"
OPERATOR_PASSWORD = "operador-clave-123"


@pytest.fixture
def engine(pipeline, cipher, db_session, landmarks) -> FaceTrackEngine:
    settings = Settings(_env_file=None, max_upload_mb=1, timezone="UTC", secret_key="t" * 48)
    engine = FaceTrackEngine(settings, pipeline, cipher, landmarks)
    engine.start(db_session)
    return engine


@pytest.fixture
def app(engine, db_session):
    UserRepository(db_session).create("admin", ADMIN_PASSWORD, UserRole.ADMIN)
    UserRepository(db_session).create("operador", OPERATOR_PASSWORD, UserRole.OPERATOR)
    # Confirmar: si no, el rollback que hace la API ante un error (dentro de
    # la transacción del test) también desharía los usuarios. Igual se
    # revierten al terminar el test.
    db_session.commit()
    return create_app(engine.settings, engine=engine, session_factory=lambda: db_session)


def login(test_client: TestClient, username: str, password: str) -> None:
    response = test_client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text


@pytest.fixture
def anon_client(app):
    """Cliente sin sesión."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(app):
    """Cliente con sesión de administrador (la mayoría de los tests)."""
    with TestClient(app) as test_client:
        login(test_client, "admin", ADMIN_PASSWORD)
        yield test_client


@pytest.fixture
def operator_client(app):
    with TestClient(app) as test_client:
        login(test_client, "operador", OPERATOR_PASSWORD)
        yield test_client
