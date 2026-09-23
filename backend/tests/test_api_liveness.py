"""API de landmarks y liveness con modelos reales, PostgreSQL y fotos reales."""

import uuid
from datetime import timedelta

import pytest

from app.database.models import AttendanceRecord, RecognitionEvent
from app.services.liveness_service import Challenge
from app.utils.dates import utc_now
from tests.api_fixtures import jpeg, upload
from tests.conftest import load_fixture
from tests.liveness_helpers import close_eyes


@pytest.fixture
def harris(client):
    person = client.post("/api/personas", json={"first_name": "Kamala", "last_name": "Harris"}).json()
    assert client.post(f"/api/personas/{person['id']}/faces", files=upload(jpeg(load_fixture("harris.jpg")))).status_code == 201
    return person


@pytest.fixture
def frames(landmarks):
    open_eyes = jpeg(load_fixture("harris.jpg"))
    closed = jpeg(close_eyes(load_fixture("harris.jpg"), landmarks))
    return {"open": open_eyes, "closed": closed, "other": jpeg(load_fixture("obama_2012.jpg"))}


def start(client, engine, *challenges: Challenge, **body) -> dict:
    response = client.post("/api/liveness/sessions", json=body)
    assert response.status_code == 201
    session = response.json()
    if challenges:  # los desafíos son al azar: los tests fijan los que pueden simular
        engine.liveness.get(session["id"], utc_now()).challenges = list(challenges)
    return session


def send(client, session_id: str, frame: bytes, **data) -> dict:
    response = client.post(f"/api/liveness/sessions/{session_id}/frames", files=upload(frame), data=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_landmarks_endpoint(client):
    body = client.post("/api/landmarks/image", files=upload(jpeg(load_fixture("harris.jpg")))).json()
    assert body["faces_detected"] == 1
    face = body["faces"][0]
    assert len(face["points"]) == 478
    assert set(face["head_pose"]) == {"yaw", "pitch", "roll"}
    assert face["eyes"]["left_ear"] > 0.15

    without = client.post(
        "/api/landmarks/image", files=upload(jpeg(load_fixture("harris.jpg"))), data={"include_points": "false"}
    ).json()
    assert without["faces"][0]["points"] == []


def test_new_session(client):
    session = client.post("/api/liveness/sessions").json()
    assert session["status"] == "IN_PROGRESS"
    assert session["challenges"][0] == {"type": "BLINK", "instruction": "Parpadeá", "completed": False}
    assert session["current_instruction"] == "Parpadeá"
    assert "no es un mecanismo de seguridad" in session["disclaimer"]


def test_live_with_blink_recognizes_and_registers_attendance(client, engine, harris, frames, db_session):
    session = start(client, engine, Challenge.BLINK, register_attendance=True, camera_id="puerta")
    for _ in range(4):
        body = send(client, session["id"], frames["open"])
    assert body["face_detected"] and body["session"]["current_instruction"] == "Parpadeá"
    send(client, session["id"], frames["closed"])
    body = send(client, session["id"], frames["open"], include_points="true")

    result = body["session"]
    assert result["status"] == "LIVE"
    assert result["person"]["name"] == "Kamala Harris"
    assert result["attendance"]["type"] == "ENTRY"
    assert len(body["points"]) == 478

    assert db_session.query(AttendanceRecord).count() == 1
    [event] = db_session.query(RecognitionEvent).all()
    assert event.camera_id == "puerta" and str(event.person_id) == harris["id"]

    # Después de terminar, más frames no cambian el resultado.
    after = send(client, session["id"], frames["other"])
    assert after["session"]["status"] == "LIVE" and after["message"] == "La prueba ya terminó."
    assert client.get(f"/api/liveness/sessions/{session['id']}").json()["status"] == "LIVE"


def test_live_without_attendance_does_not_register_it(client, engine, harris, frames, db_session):
    session = start(client, engine, Challenge.BLINK)
    for frame in ["open"] * 4 + ["closed", "open"]:
        body = send(client, session["id"], frames[frame])
    assert body["session"]["status"] == "LIVE" and body["session"]["attendance"] is None
    assert db_session.query(AttendanceRecord).count() == 0


def test_photo_swap_is_suspicious(client, engine, harris, frames):
    session = start(client, engine, Challenge.BLINK)
    for _ in range(4):
        send(client, session["id"], frames["open"])
    body = send(client, session["id"], frames["other"])  # 5.º frame: se verifica la identidad
    assert body["session"]["status"] == "SUSPICIOUS"
    assert "cambió" in body["session"]["reason"]


def test_static_photo_is_suspicious_after_timeout(client, engine, harris, frames):
    session = start(client, engine, Challenge.BLINK)
    for _ in range(6):
        send(client, session["id"], frames["open"])
    live = engine.liveness._sessions[session["id"]]
    live.expires_at -= timedelta(minutes=1)  # simula que pasó el tiempo límite
    result = client.get(f"/api/liveness/sessions/{session['id']}").json()
    assert result["status"] == "SUSPICIOUS"
    assert result["person"]["name"] == "Kamala Harris"  # se sabe quién era, pero no pasó la prueba
    assert result["attendance"] is None


def test_unknown_session_404(client):
    assert client.get(f"/api/liveness/sessions/{uuid.uuid4()}").status_code == 404
    response = client.post(f"/api/liveness/sessions/{uuid.uuid4()}/frames", files=upload(jpeg(load_fixture("harris.jpg"))))
    assert response.status_code == 404


def test_invalid_session_body_422(client):
    assert client.post("/api/liveness/sessions", json={"camera_id": "a/b"}).status_code == 422
    assert client.post("/api/liveness/sessions", json={"otro": 1}).status_code == 422


def test_invalid_frame_400(client):
    session = client.post("/api/liveness/sessions").json()
    response = client.post(
        f"/api/liveness/sessions/{session['id']}/frames", files=upload(b"\xff\xd8\xff" + b"x" * 50)
    )
    assert response.status_code == 400
