"""Tests de la API REST con PostgreSQL y modelos reales."""

import uuid

import cv2
import numpy as np
import pytest

from app.database.models import AppSetting
from tests.api_fixtures import jpeg, png, upload
from tests.conftest import load_fixture, side_by_side


@pytest.fixture
def obama(client) -> dict:
    person = client.post("/api/personas", json={"nombre": "Barack", "apellido": "Obama"}).json()
    response = client.post(f"/api/personas/{person['id']}/faces", files=upload(jpeg(load_fixture("obama_2012.jpg"))))
    assert response.status_code == 201, response.text
    return person


def assert_no_embeddings(payload) -> None:
    assert "embedding" not in str(payload).lower()


# --- Salud ---


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


# --- Personas ---


def test_create_person_accepts_spanish_field_names(client):
    response = client.post("/api/personas", json={"nombre": " Gianfranco ", "apellido": "Canciani", "email": "G@X.com"})
    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Gianfranco"
    assert body["full_name"] == "Gianfranco Canciani"
    assert body["email"] == "g@x.com"
    assert body["face_count"] == 0 and body["active"] is True


@pytest.mark.parametrize(
    "payload",
    [{}, {"first_name": ""}, {"first_name": "Ana", "email": "no-es-email"}, {"first_name": "Ana", "rol": "admin"}],
    ids=["missing-name", "empty-name", "bad-email", "unknown-field"],
)
def test_create_person_validation_422(client, payload):
    response = client.post("/api/personas", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_duplicate_email_409(client):
    client.post("/api/personas", json={"first_name": "Ana", "email": "ana@x.com"})
    response = client.post("/api/personas", json={"first_name": "Otra", "email": "ANA@x.com"})
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate"


def test_get_list_update_delete_person(client):
    created = client.post("/api/personas", json={"first_name": "Juan"}).json()
    pid = created["id"]

    assert client.get(f"/api/personas/{pid}").json()["first_name"] == "Juan"
    assert [p["id"] for p in client.get("/api/personas").json()] == [pid]

    updated = client.put(f"/api/personas/{pid}", json={"apellido": "Pérez", "active": False})
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Juan Pérez" and updated.json()["active"] is False
    assert client.get("/api/personas", params={"active": True}).json() == []

    assert client.delete(f"/api/personas/{pid}").status_code == 204
    assert client.get(f"/api/personas/{pid}").status_code == 404


def test_person_404_and_invalid_id_422(client):
    missing = uuid.uuid4()
    for method, url in [
        ("get", f"/api/personas/{missing}"),
        ("put", f"/api/personas/{missing}"),
        ("delete", f"/api/personas/{missing}"),
        ("get", f"/api/personas/{missing}/faces"),
    ]:
        response = client.request(method, url, json={"first_name": "X"} if method == "put" else None)
        assert response.status_code == 404, url
        assert response.json()["code"] == "not_found"
    assert client.get("/api/personas/no-es-un-uuid").status_code == 422


# --- Registro facial ---


def test_enroll_face(client, obama, engine):
    faces = client.get(f"/api/personas/{obama['id']}/faces").json()
    assert len(faces) == 1 and faces[0]["model_version"] == "sface_2021dec"
    assert client.get(f"/api/personas/{obama['id']}").json()["face_count"] == 1
    assert engine.pipeline.recognizer.known_people == 1  # recargado automáticamente
    assert_no_embeddings(faces)


def test_enroll_response_includes_quality(client):
    person = client.post("/api/personas", json={"first_name": "Kamala"}).json()
    body = client.post(f"/api/personas/{person['id']}/faces", files=upload(jpeg(load_fixture("harris.jpg")))).json()
    assert body["face_count"] == 1
    assert body["quality"]["sharpness"] > 100 and 50 < body["quality"]["brightness"] < 210
    assert_no_embeddings(body)


@pytest.mark.parametrize(
    "image_bytes,content_type,status,code",
    [
        (lambda: b"\xff\xd8\xff" + b"basura" * 20, "image/jpeg", 400, "invalid_image"),
        (lambda: b"hola", "text/plain", 415, "unsupported_media_type"),
        (lambda: png(cv2.resize(load_fixture("biden.jpg"), (240, 300))), "image/jpeg", 415, "unsupported_media_type"),
        (lambda: b"\x00" * (1024 * 1024 + 1), "image/jpeg", 413, "payload_too_large"),
        (lambda: jpeg(np.full((480, 640, 3), 127, np.uint8)), "image/jpeg", 422, "face_not_found"),
        (lambda: jpeg(side_by_side("biden.jpg", "harris.jpg", height=400)), "image/jpeg", 422, "multiple_faces"),
        (lambda: jpeg(cv2.GaussianBlur(load_fixture("biden.jpg"), (21, 21), 0)), "image/jpeg", 422, "low_quality"),
        (lambda: jpeg((load_fixture("biden.jpg") * 0.2).astype(np.uint8)), "image/jpeg", 422, "low_quality"),
    ],
    ids=["corrupt", "not-an-image", "mime-mismatch", "too-large", "no-face", "two-faces", "blurry", "dark"],
)
def test_enroll_rejections(client, image_bytes, content_type, status, code):
    person = client.post("/api/personas", json={"first_name": "Joe"}).json()
    response = client.post(f"/api/personas/{person['id']}/faces", files=upload(image_bytes(), content_type))
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert client.get(f"/api/personas/{person['id']}").json()["face_count"] == 0


def test_enroll_conflicting_face_409(client, obama):
    other = client.post("/api/personas", json={"first_name": "Impostor"}).json()
    response = client.post(f"/api/personas/{other['id']}/faces", files=upload(jpeg(load_fixture("obama_2009.jpg"))))
    assert response.status_code == 409
    assert "Barack Obama" in response.json()["detail"]


def test_enroll_unknown_person_404(client):
    response = client.post(f"/api/personas/{uuid.uuid4()}/faces", files=upload(jpeg(load_fixture("biden.jpg"))))
    assert response.status_code == 404


def test_delete_face_sample(client, obama, engine):
    [face] = client.get(f"/api/personas/{obama['id']}/faces").json()
    assert client.delete(f"/api/personas/{obama['id']}/faces/{face['id']}").status_code == 204
    assert engine.pipeline.recognizer.sample_count == 0
    assert client.delete(f"/api/personas/{obama['id']}/faces/{face['id']}").status_code == 404


# --- Reconocimiento, historial y asistencia ---


def test_recognize_multiple_faces(client, obama):
    scene = side_by_side("obama_2009.jpg", "biden.jpg")
    response = client.post("/api/reconocimiento/image", files=upload(jpeg(scene)))
    assert response.status_code == 200
    body = response.json()
    assert body["faces_detected"] == 2 and body["events_recorded"] == 2
    results = sorted(body["results"], key=lambda r: r["bbox"]["x"])
    assert results[0]["recognized"] and results[0]["name"] == "Barack Obama"
    assert results[0]["person_id"] == obama["id"] and results[0]["confidence"] > 0.5
    assert not results[1]["recognized"] and results[1]["name"] == "Desconocido" and results[1]["confidence"] == 0
    assert all(r["attendance"] is None for r in results)
    assert_no_embeddings(body)

    # Mismo frame otra vez: dentro del cooldown no se registran eventos nuevos.
    again = client.post("/api/reconocimiento/image", files=upload(jpeg(scene))).json()
    assert again["faces_detected"] == 2 and again["events_recorded"] == 0


def test_recognize_image_without_faces(client):
    body = client.post("/api/reconocimiento/image", files=upload(png(np.zeros((200, 200, 3), np.uint8)), "image/png")).json()
    assert body == {"faces_detected": 0, "image_width": 200, "image_height": 200, "events_recorded": 0, "results": []}


def test_recognize_invalid_mode_422(client):
    response = client.post(
        "/api/reconocimiento/image", files=upload(jpeg(load_fixture("biden.jpg"))), data={"mode": "liveness"}
    )
    assert response.status_code == 422


def test_attendance_mode_and_queries(client, obama):
    response = client.post(
        "/api/reconocimiento/image",
        files=upload(jpeg(load_fixture("obama_2009.jpg"))),
        data={"mode": "attendance", "camera_id": "entrada"},
    )
    [result] = response.json()["results"]
    assert result["attendance"]["type"] == "ENTRY"

    history = client.get("/api/historial", params={"person_id": obama["id"]}).json()
    assert history["total"] == 1 and history["items"][0]["camera_id"] == "entrada"
    assert history["items"][0]["person_name"] == "Barack Obama"

    attendance = client.get("/api/asistencia", params={"type": "ENTRY"}).json()
    assert attendance["total"] == 1 and attendance["items"][0]["person_name"] == "Barack Obama"
    assert client.get("/api/asistencia", params={"type": "EXIT"}).json()["total"] == 0

    csv_response = client.get("/api/asistencia/export.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    lines = csv_response.content.decode("utf-8-sig").strip().splitlines()
    assert lines[0] == "Persona,Fecha,Hora,Tipo,Confianza"
    assert lines[1].startswith("Barack Obama,") and ",Entrada," in lines[1]


def test_history_filters_unknown(client):
    client.post("/api/reconocimiento/image", files=upload(jpeg(load_fixture("biden.jpg"))))
    body = client.get("/api/historial", params={"recognized": False}).json()
    assert body["total"] == 1 and body["items"][0]["person_name"] == "Desconocido"
    assert client.get("/api/historial", params={"recognized": True}).json()["total"] == 0


@pytest.mark.parametrize(
    "params",
    [{"date": "2026-09-22", "from": "2026-09-01"}, {"from": "2026-09-22", "to": "2026-09-01"}, {"date": "ayer"}, {"limit": 0}],
    ids=["date-and-range", "inverted-range", "bad-date", "bad-limit"],
)
def test_date_filter_validation_422(client, params):
    assert client.get("/api/asistencia", params=params).status_code == 422


# --- Estadísticas ---


def test_statistics(client, obama):
    client.post("/api/reconocimiento/image", files=upload(jpeg(side_by_side("obama_2009.jpg", "biden.jpg"))), data={"mode": "attendance"})

    summary = client.get("/api/estadisticas/resumen").json()
    assert summary["persons_registered"] == 1
    assert summary["recognitions_today"] == 1 and summary["unknown_today"] == 1
    assert summary["people_present"] == 1
    assert {a["person_name"] for a in summary["recent_activity"]} == {"Barack Obama", "Desconocido"}

    stats = client.get("/api/estadisticas").json()
    assert len(stats["by_day"]) == 7
    assert stats["recognized_total"] == 1 and stats["unknown_total"] == 1 and stats["entries"] == 1
    assert stats["by_person"][0]["person_name"] == "Barack Obama"
    assert 0.5 < stats["average_confidence"] <= 1

    assert client.get("/api/estadisticas", params={"from": "2026-09-22", "to": "2026-09-01"}).status_code == 422


# --- Configuración ---


def test_config_get_and_update(client, engine, db_session):
    config = client.get("/api/configuracion").json()
    assert config["privacy"] == {"local_processing": True, "save_images": False, "save_video": False, "embeddings_encrypted": True}

    new = {k: config[k] for k in config if k not in ("privacy", "model_version")}
    new.update(face_recognition_threshold=0.5, max_faces=3, recognition_cooldown_seconds=30)
    response = client.put("/api/configuracion", json=new)
    assert response.status_code == 200
    assert engine.pipeline.recognizer.threshold == 0.5
    assert engine.pipeline.detector.max_faces == 3
    assert engine.cooldown.window.total_seconds() == 30
    assert db_session.get(AppSetting, "runtime").value["face_recognition_threshold"] == 0.5


@pytest.mark.parametrize(
    "change",
    [{"face_recognition_threshold": 5}, {"camera_fps": 0}, {"save_images": True}, {"camera_id": "cam/../x"}],
    ids=["threshold-out-of-range", "fps-zero", "save-images-not-supported", "bad-camera-id"],
)
def test_config_validation_422(client, change):
    config = client.get("/api/configuracion").json()
    body = {k: config[k] for k in config if k not in ("privacy", "model_version")}
    body.update(change)
    assert client.put("/api/configuracion", json=body).status_code == 422
