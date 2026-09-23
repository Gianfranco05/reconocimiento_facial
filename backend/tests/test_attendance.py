import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.exceptions import NotFoundError
from app.database.models import AttendanceRecord, AttendanceType, Person
from app.database.repositories.attendance_repository import AttendanceRepository
from app.database.repositories.person_repository import PersonRepository
from app.services.attendance_service import AttendanceService
from app.utils.dates import local_day_bounds

TZ = ZoneInfo("America/Argentina/Buenos_Aires")  # UTC-3


def local(day: int, hour: int, minute: int = 0) -> datetime:
    """Hora local de Buenos Aires del 22/09/2026 (+ día) convertida a UTC."""
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ).astimezone(UTC)


@pytest.fixture
def service() -> AttendanceService:
    return AttendanceService(min_interval=timedelta(minutes=10), tz=TZ)


@pytest.fixture
def person(db_session) -> Person:
    return PersonRepository(db_session).create("Gian")


def types(db_session, person) -> list[str]:
    records = AttendanceRepository(db_session).list(person_id=person.id)
    return [r.type.value for r in reversed(records)]


def test_first_recognition_is_entry(db_session, service, person):
    record = service.register(db_session, person.id, 0.95, local(22, 8, 1))
    assert record.type is AttendanceType.ENTRY
    assert record.confidence == 0.95


def test_second_recognition_same_day_is_exit(db_session, service, person):
    service.register(db_session, person.id, 0.9, local(22, 8, 1))
    record = service.register(db_session, person.id, 0.9, local(22, 13, 2))
    assert record.type is AttendanceType.EXIT


def test_full_day_alternates(db_session, service, person):
    for hour, minute in ((8, 1), (13, 2), (14, 3), (18, 1)):
        service.register(db_session, person.id, 0.9, local(22, hour, minute))
    assert types(db_session, person) == ["ENTRY", "EXIT", "ENTRY", "EXIT"]


def test_no_duplicate_entry_while_still_in_front_of_camera(db_session, service, person):
    service.register(db_session, person.id, 0.9, local(22, 8, 0))
    for minute in (0, 1, 5, 9):
        assert service.register(db_session, person.id, 0.9, local(22, 8, minute)) is None
    assert types(db_session, person) == ["ENTRY"]


def test_forgotten_exit_starts_next_day_with_entry(db_session, service, person):
    service.register(db_session, person.id, 0.9, local(22, 9))
    record = service.register(db_session, person.id, 0.9, local(23, 8, 30))
    assert record.type is AttendanceType.ENTRY
    assert types(db_session, person) == ["ENTRY", "ENTRY"]


def test_day_boundary_uses_local_timezone(db_session, service, person):
    # 22/09 23:00 local = 23/09 02:00 UTC: sigue siendo el mismo día local.
    service.register(db_session, person.id, 0.9, local(22, 20))
    record = service.register(db_session, person.id, 0.9, local(22, 23))
    assert record.type is AttendanceType.EXIT


def test_inactive_person_not_registered(db_session, service, person):
    PersonRepository(db_session).update(person.id, active=False)
    assert service.register(db_session, person.id, 0.9, local(22, 8)) is None
    assert types(db_session, person) == []


def test_missing_person_raises(db_session, service):
    with pytest.raises(NotFoundError):
        service.register(db_session, uuid.uuid4(), 0.9, local(22, 8))


def test_list_filters(db_session, service, person):
    other = PersonRepository(db_session).create("Juan")
    service.register(db_session, person.id, 0.9, local(22, 8))
    service.register(db_session, other.id, 0.9, local(22, 8, 5))
    service.register(db_session, person.id, 0.9, local(22, 13))
    service.register(db_session, person.id, 0.9, local(23, 8))

    repo = AttendanceRepository(db_session)
    start, end = local_day_bounds(datetime(2026, 9, 22).date(), TZ)
    assert len(repo.list(start=start, end=end)) == 3
    assert len(repo.list(person_id=person.id, start=start, end=end)) == 2
    assert [r.person_id for r in repo.list(type_=AttendanceType.EXIT)] == [person.id]


class SlowAttendanceService(AttendanceService):
    """Agranda la ventana entre leer el último registro y escribir el nuevo,
    para que una condición de carrera sea reproducible."""

    def next_type(self, last, now):
        time.sleep(0.2)
        return super().next_type(last, now)


def test_concurrent_registrations_do_not_duplicate_entry(committing_session_factory):
    """Reconocimientos simultáneos (p. ej. dos cámaras) de la misma persona:
    el bloqueo de fila debe producir un único ENTRY."""
    service = SlowAttendanceService(min_interval=timedelta(minutes=10), tz=TZ)
    with committing_session_factory() as session:
        person = PersonRepository(session).create("Concurrente")
        session.commit()
        person_id = person.id

    now = datetime.now(UTC)
    barrier = threading.Barrier(4)
    errors = []

    def worker():
        try:
            with committing_session_factory() as session:
                barrier.wait()
                service.register(session, person_id, 0.9, now)
                session.commit()
        except Exception as exc:  # pragma: no cover - se reporta abajo
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert errors == []
        with committing_session_factory() as session:
            assert session.query(AttendanceRecord).filter_by(person_id=person_id).count() == 1
    finally:
        with committing_session_factory() as session:
            session.delete(session.get(Person, person_id))
            session.commit()
