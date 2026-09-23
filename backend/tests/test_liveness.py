"""Lógica de la prueba de vida con landmarks sintéticos (sin modelos)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.face_detector import BoundingBox
from app.services.face_recognizer import RecognitionResult
from app.services.landmark_service import EyeState, FaceLandmarks, HeadPose
from app.services.liveness_service import (
    BlinkDetector,
    Challenge,
    LivenessSessionStore,
    LivenessSettings,
    LivenessStatus,
)

T0 = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
SETTINGS = LivenessSettings(timeout_seconds=20)


def face(ear: float = 0.3, yaw: float = 0.0, pitch: float = -10.0) -> FaceLandmarks:
    return FaceLandmarks(
        BoundingBox(0, 0, 100, 100),
        np.zeros((478, 2), np.float32),
        EyeState(ear, ear, 0.1, 0.1),
        HeadPose(yaw, pitch, 0.0),
    )


def new_session(*challenges: Challenge):
    session = LivenessSessionStore(SETTINGS).create(T0)
    session.challenges = list(challenges)
    return session


def feed(session, frames, start=T0, step=0.1):
    feedback = None
    for i, f in enumerate(frames):
        feedback = session.process(f if isinstance(f, list) else [f], start + timedelta(seconds=step * (i + 1)))
    return feedback


# --- Parpadeo ---


def test_blink_open_closed_open():
    detector = BlinkDetector(0.65, 0.85)
    results = [detector.update(e) for e in [0.30, 0.31, 0.29, 0.30, 0.12, 0.10, 0.29]]
    assert results == [False] * 6 + [True]


def test_blink_thresholds_adapt_to_narrow_eyes():
    # Ojos naturalmente "chicos" (EAR ~0.18): un umbral absoluto de 0.2 los daría por cerrados siempre.
    detector = BlinkDetector(0.65, 0.85)
    for ear in [0.18, 0.18, 0.17, 0.18, 0.18]:
        assert detector.update(ear) is False
    assert detector.update(0.09) is False
    assert detector.update(0.17) is True


def test_half_closed_eyes_are_not_a_blink():
    detector = BlinkDetector(0.65, 0.85)
    assert not any(detector.update(e) for e in [0.30, 0.30, 0.30, 0.22, 0.30, 0.23, 0.30])


def test_closed_eyes_without_reopening_are_not_a_blink():
    detector = BlinkDetector(0.65, 0.85)
    assert not any(detector.update(e) for e in [0.30, 0.30, 0.30, 0.10, 0.10, 0.10])


# --- Sesión ---


def test_live_after_blink_and_turn():
    session = new_session(Challenge.BLINK, Challenge.TURN_RIGHT)
    feed(session, [face()] * 4)  # referencia
    assert session.current_challenge is Challenge.BLINK
    feed(session, [face(0.1), face(0.3)])
    assert session.completed == 1 and session.status is LivenessStatus.IN_PROGRESS
    feedback = feed(session, [face(yaw=10), face(yaw=25)])
    assert session.status is LivenessStatus.LIVE
    assert feedback.message == "Prueba superada."


@pytest.mark.parametrize(
    "challenge,good,bad",
    [
        (Challenge.TURN_RIGHT, face(yaw=22), face(yaw=-30)),
        (Challenge.TURN_LEFT, face(yaw=-22), face(yaw=30)),
        (Challenge.LOOK_UP, face(pitch=4), face(pitch=-30)),  # referencia pitch -10
    ],
)
def test_pose_challenges_are_relative_to_initial_pose(challenge, good, bad):
    session = new_session(challenge)
    feed(session, [face()] * 3)
    feed(session, [bad])
    assert session.status is LivenessStatus.IN_PROGRESS
    feed(session, [good])
    assert session.status is LivenessStatus.LIVE


def test_initial_pose_is_not_zero():
    # La persona empieza girada 15°: debe girar 20° MÁS desde ahí.
    session = new_session(Challenge.TURN_RIGHT)
    feed(session, [face(yaw=15)] * 3)
    feed(session, [face(yaw=25)])
    assert session.status is LivenessStatus.IN_PROGRESS
    feed(session, [face(yaw=36)])
    assert session.status is LivenessStatus.LIVE


def test_challenges_must_be_done_in_order():
    session = new_session(Challenge.BLINK, Challenge.TURN_RIGHT)
    feed(session, [face()] * 3 + [face(yaw=30)])  # giró antes de parpadear
    assert session.completed == 0


def test_static_photo_times_out_as_suspicious():
    session = new_session(Challenge.BLINK, Challenge.TURN_LEFT)
    feed(session, [face()] * 30, step=0.5)  # 15 s de la misma cara inmóvil
    session.check_timeout(T0 + timedelta(seconds=21))
    assert session.status is LivenessStatus.SUSPICIOUS
    assert "no completó" in session.reason


def test_no_face_times_out_as_unknown():
    session = new_session(Challenge.BLINK)
    feed(session, [[]] * 10)
    feedback = session.process([face()], T0 + timedelta(seconds=25))
    assert session.status is LivenessStatus.UNKNOWN
    assert "tiempo" in feedback.message


def test_multiple_faces_are_not_evaluated():
    session = new_session(Challenge.BLINK)
    feedback = feed(session, [[face(), face()]])
    assert not feedback.face_detected and "una sola persona" in feedback.message
    assert session.frames_with_face == 0


def test_identity_swap_is_suspicious():
    session = new_session(Challenge.BLINK)
    session.add_identity(RecognitionResult(True, "a", "Ana", 0.2, 0.9), False, T0)
    session.add_identity(RecognitionResult(True, "b", "Beto", 0.2, 0.9), True, T0)
    assert session.status is LivenessStatus.SUSPICIOUS
    assert "cambió" in session.reason


def test_person_is_most_frequent_identity():
    session = new_session(Challenge.BLINK)
    for pid, conf in [("a", 0.8), ("a", 0.9), ("b", 0.95)]:
        session.add_identity(RecognitionResult(True, pid, pid.upper(), 0.2, conf), False, T0)
    assert session.person.person_id == "a" and session.person.confidence == 0.9


def test_finished_session_ignores_frames():
    session = new_session(Challenge.BLINK)
    session.check_timeout(T0 + timedelta(seconds=30))
    frames = session.frames
    assert session.process([face()], T0 + timedelta(seconds=31)).message == "La prueba ya terminó."
    assert session.frames == frames


def test_store_random_challenges_and_expiry():
    store = LivenessSessionStore(SETTINGS)
    session = store.create(T0)
    assert session.challenges[0] is Challenge.BLINK
    assert session.challenges[1] in (Challenge.TURN_LEFT, Challenge.TURN_RIGHT, Challenge.LOOK_UP)
    assert store.get(session.id, T0) is session
    # Vencida: queda UNKNOWN y se conserva un rato para consultar el resultado.
    assert store.get(session.id, T0 + timedelta(seconds=25)).status is LivenessStatus.UNKNOWN
    assert store.get(session.id, T0 + timedelta(minutes=10)) is None
