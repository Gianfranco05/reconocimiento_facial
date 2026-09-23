from datetime import UTC, datetime, timedelta

import pytest

from app.database.models import RecognitionEvent
from app.database.repositories.event_repository import EventRepository
from app.database.repositories.person_repository import PersonRepository
from app.services.cooldown import RecognitionCooldown
from app.services.event_service import RecognitionEventService
from app.services.face_recognizer import RecognitionResult

T0 = datetime(2026, 9, 22, 15, 40, tzinfo=UTC)


def known(person_id, name="Gian", confidence=0.9) -> RecognitionResult:
    return RecognitionResult(True, str(person_id), name, 0.2, confidence)


# --- Cooldown (sin base de datos) ---


def test_cooldown_blocks_repeats_inside_window():
    cooldown = RecognitionCooldown(10)
    assert cooldown.allow("gian", T0)
    assert not cooldown.allow("gian", T0 + timedelta(seconds=5))
    assert not cooldown.allow("gian", T0 + timedelta(seconds=9.9))
    assert cooldown.allow("gian", T0 + timedelta(seconds=10))


def test_cooldown_keys_are_independent():
    cooldown = RecognitionCooldown(10)
    assert cooldown.allow("gian", T0)
    assert cooldown.allow("juan", T0)


def test_cooldown_window_restarts_only_when_accepted():
    cooldown = RecognitionCooldown(10)
    cooldown.allow("gian", T0)
    cooldown.allow("gian", T0 + timedelta(seconds=8))  # rechazado: no reinicia la ventana
    assert cooldown.allow("gian", T0 + timedelta(seconds=10))


def test_zero_cooldown_allows_everything():
    cooldown = RecognitionCooldown(0)
    assert cooldown.allow("gian", T0) and cooldown.allow("gian", T0)


def test_negative_cooldown_rejected():
    with pytest.raises(ValueError):
        RecognitionCooldown(-1)


# --- Eventos en la base ---


@pytest.fixture
def person(db_session):
    return PersonRepository(db_session).create("Gian")


def service(save_events=True) -> RecognitionEventService:
    return RecognitionEventService(RecognitionCooldown(10), camera_id="entrada", save_events=save_events)


def test_repeated_frames_record_a_single_event(db_session, person):
    events = service()
    for second in range(0, 10, 1):  # 10 frames en 10 segundos
        events.process(db_session, [known(person.id)], T0 + timedelta(seconds=second))
    events.process(db_session, [known(person.id)], T0 + timedelta(seconds=10))

    stored = EventRepository(db_session).list()
    assert len(stored) == 2
    assert all(e.person_id == person.id and e.recognized for e in stored)
    assert stored[0].camera_id == "entrada"


def test_unknown_faces_recorded_once_per_camera_window(db_session, person):
    events = service()
    unknown = RecognitionResult.unknown(0.9)
    processed = events.process(db_session, [unknown, unknown, known(person.id)], T0)

    assert len(processed.fresh) == 2
    stored = EventRepository(db_session).list(recognized=False)
    assert len(stored) == 1
    assert stored[0].person_id is None
    assert stored[0].confidence == 0.0
    assert stored[0].distance == pytest.approx(0.9)


def test_save_events_disabled_still_applies_cooldown(db_session, person):
    events = service(save_events=False)
    first = events.process(db_session, [known(person.id)], T0)
    second = events.process(db_session, [known(person.id)], T0 + timedelta(seconds=1))

    assert len(first.fresh) == 1 and first.events == []
    assert second.fresh == []
    assert db_session.query(RecognitionEvent).count() == 0


def test_list_events_by_range_and_person(db_session, person):
    repo = EventRepository(db_session)
    other = PersonRepository(db_session).create("Juan")
    for hours, who in ((0, person.id), (1, other.id), (2, person.id)):
        repo.add(person_id=who, recognized=True, confidence=0.9, distance=0.2, camera_id="c", created_at=T0 + timedelta(hours=hours))

    assert len(repo.list(person_id=person.id)) == 2
    in_range = repo.list(start=T0 + timedelta(hours=1), end=T0 + timedelta(hours=2))
    assert [e.person_id for e in in_range] == [other.id]
    newest_first = repo.list()
    assert newest_first[0].created_at > newest_first[-1].created_at


def test_cooldown_survives_process_restart(db_session, person):
    """Un servicio nuevo (otro proceso o worker) respeta los eventos ya guardados."""
    service().process(db_session, [known(person.id), RecognitionResult.unknown(0.9)], T0)
    restarted = service()
    again = restarted.process(db_session, [known(person.id), RecognitionResult.unknown(0.9)], T0 + timedelta(seconds=3))
    assert again.fresh == []
    later = restarted.process(db_session, [known(person.id)], T0 + timedelta(seconds=11))
    assert len(later.fresh) == 1
    assert len(EventRepository(db_session).list()) == 3


def test_unknown_cooldown_is_per_camera_in_database(db_session):
    RecognitionEventService(RecognitionCooldown(10), "entrada").process(db_session, [RecognitionResult.unknown(0.9)], T0)
    other_camera = RecognitionEventService(RecognitionCooldown(10), "salida")
    assert len(other_camera.process(db_session, [RecognitionResult.unknown(0.9)], T0).fresh) == 1
