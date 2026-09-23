"""Rutas de error: base caída, errores internos, configuración guardada inválida y validación de uploads."""

import io

import pytest
from fastapi import UploadFile
from sqlalchemy.exc import OperationalError

from app.core.exceptions import FaceTrackError, InvalidImageError, PayloadTooLargeError, UnsupportedMediaError
from app.database.models import AppSetting
from app.services.runtime_config import SETTINGS_KEY, RuntimeConfig, RuntimeConfigStore
from app.utils import validators
from tests.api_fixtures import jpeg, upload
from tests.conftest import load_fixture


def test_health_reports_database_down(anon_client, db_session, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    monkeypatch.setattr(db_session, "execute", broken)
    response = anon_client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_database_error_is_503_without_details(client, engine, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT secreto FROM tabla", {}, Exception("password=postgres host=db"))

    monkeypatch.setattr(engine, "recognize", broken)
    response = client.post("/api/reconocimiento/image", files=upload(jpeg(load_fixture("biden.jpg"))))
    assert response.status_code == 503
    body = response.json()
    assert (body["detail"], body["code"]) == ("Error de base de datos.", "database_error")
    assert body["request_id"] == response.headers["x-request-id"]
    # El detalle (que puede incluir la URL o credenciales) no llega al cliente ni al log de nivel ERROR.
    assert "password" not in response.text
    assert not any("password" in r.getMessage() for r in caplog.records if r.levelname == "ERROR")


def test_unexpected_domain_error_is_generic_500(client, engine, monkeypatch):
    def broken(*args, **kwargs):
        raise FaceTrackError("detalle interno que no debe salir")

    monkeypatch.setattr(engine, "recognize", broken)
    response = client.post("/api/reconocimiento/image", files=upload(jpeg(load_fixture("biden.jpg"))))
    assert response.status_code == 500
    body = response.json()
    assert (body["detail"], body["code"]) == ("Error interno.", "internal_error")
    assert "detalle interno" not in response.text


def test_invalid_stored_config_falls_back_to_defaults(db_session):
    defaults = RuntimeConfig(
        face_recognition_threshold=0.63,
        recognition_cooldown_seconds=10,
        attendance_min_interval_minutes=10,
        camera_fps=15,
        max_faces=10,
        camera_id="default",
        save_events=True,
    )
    db_session.add(AppSetting(key=SETTINGS_KEY, value={"face_recognition_threshold": 99, "campo_viejo": 1}))
    db_session.flush()
    assert RuntimeConfigStore(defaults).load(db_session) == defaults


def test_valid_stored_config_ignores_unknown_fields(db_session):
    defaults = RuntimeConfig(
        face_recognition_threshold=0.63,
        recognition_cooldown_seconds=10,
        attendance_min_interval_minutes=10,
        camera_fps=15,
        max_faces=10,
        camera_id="default",
        save_events=True,
    )
    db_session.add(AppSetting(key=SETTINGS_KEY, value={"max_faces": 3, "campo_viejo": 1}))
    db_session.flush()
    assert RuntimeConfigStore(defaults).load(db_session).max_faces == 3


def make_upload(data: bytes, content_type: str | None) -> UploadFile:
    headers = {"content-type": content_type} if content_type else {}
    from starlette.datastructures import Headers

    return UploadFile(io.BytesIO(data), filename="x", headers=Headers(headers))


@pytest.mark.parametrize(
    "data,content_type,error",
    [
        (b"\xff\xd8\xff\xe0", None, UnsupportedMediaError),
        (b"", "image/jpeg", InvalidImageError),
        (b"GIF89a....", "image/jpeg", InvalidImageError),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp", InvalidImageError),
    ],
    ids=["no-content-type", "empty", "gif-not-supported", "webp-corrupt"],
)
def test_upload_validation_branches(data, content_type, error):
    with pytest.raises(error):
        validators.read_upload_image(make_upload(data, content_type), max_bytes=1024)


def test_too_many_pixels_rejected(monkeypatch):
    monkeypatch.setattr(validators, "MAX_PIXELS", 100)
    data = jpeg(load_fixture("lena.jpg"))
    with pytest.raises(PayloadTooLargeError):
        validators.read_upload_image(make_upload(data, "image/jpeg"), max_bytes=len(data) + 1)


def test_bmp_and_png_signatures_accepted():
    import cv2

    image = load_fixture("lena.jpg")[:64, :64]
    for extension, mime in ((".png", "image/png"), (".bmp", "image/bmp")):
        ok, encoded = cv2.imencode(extension, image)
        assert ok
        frame = validators.read_upload_image(make_upload(encoded.tobytes(), mime), max_bytes=10**6)
        assert frame.shape == (64, 64, 3)
