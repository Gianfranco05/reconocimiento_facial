import uuid

import numpy as np
import pytest

from app.core.exceptions import DuplicateError, NotFoundError
from app.database.models import AttendanceRecord, AttendanceType, FaceEmbedding, RecognitionEvent
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.person_repository import PersonRepository


@pytest.fixture
def repo(db_session) -> PersonRepository:
    return PersonRepository(db_session)


def test_create(repo):
    person = repo.create("  Gianfranco ", "Canciani", " Gian@Example.COM ")
    assert isinstance(person.id, uuid.UUID)
    assert person.first_name == "Gianfranco"
    assert person.email == "gian@example.com"
    assert person.active is True
    assert person.created_at is not None and person.updated_at is not None
    assert person.full_name == "Gianfranco Canciani"


def test_get(repo):
    created = repo.create("Juan")
    assert repo.get(created.id).first_name == "Juan"


def test_get_missing_raises(repo):
    with pytest.raises(NotFoundError):
        repo.get(uuid.uuid4())


def test_list_filters_by_active(repo):
    repo.create("Ana")
    inactive = repo.create("Pedro")
    repo.update(inactive.id, active=False)
    assert [p.first_name for p in repo.list()] == ["Ana", "Pedro"]
    assert [p.first_name for p in repo.list(active=True)] == ["Ana"]


def test_update(repo):
    person = repo.create("Gian", email="old@example.com")
    updated = repo.update(person.id, first_name="Gianfranco", email="NEW@example.com", active=False)
    assert updated.first_name == "Gianfranco"
    assert updated.email == "new@example.com"
    assert updated.active is False


def test_update_rejects_unknown_fields(repo):
    person = repo.create("Gian")
    with pytest.raises(ValueError):
        repo.update(person.id, id=uuid.uuid4())


def test_duplicate_email_is_case_insensitive(repo):
    repo.create("Gian", email="gian@example.com")
    with pytest.raises(DuplicateError):
        repo.create("Otro", email="GIAN@example.com")
    # La sesión sigue siendo utilizable después del error.
    assert len(repo.list()) == 1


def test_delete_cascades_but_keeps_event_history(repo, db_session, cipher):
    person = repo.create("Gian")
    EmbeddingRepository(db_session, cipher).add(person.id, np.ones(8, dtype=np.float32), "test")
    db_session.add(AttendanceRecord(person_id=person.id, type=AttendanceType.ENTRY, confidence=0.9))
    event = RecognitionEvent(person_id=person.id, recognized=True, confidence=0.9, distance=0.1, camera_id="c1")
    db_session.add(event)
    db_session.flush()

    repo.delete(person.id)
    db_session.expire_all()

    assert db_session.query(FaceEmbedding).count() == 0
    assert db_session.query(AttendanceRecord).count() == 0
    assert db_session.get(RecognitionEvent, event.id).person_id is None
    with pytest.raises(NotFoundError):
        repo.get(person.id)


def test_embedding_counts(repo, db_session, cipher):
    a, b = repo.create("A"), repo.create("B")
    embeddings = EmbeddingRepository(db_session, cipher)
    for _ in range(3):
        embeddings.add(a.id, np.ones(8, dtype=np.float32), "test")
    assert repo.embedding_counts() == {a.id: 3}
    assert b.id not in repo.embedding_counts()


def test_duplicate_email_on_update_keeps_session_usable(repo):
    repo.create("Gian", email="gian@example.com")
    juan = repo.create("Juan", email="juan@example.com")
    with pytest.raises(DuplicateError):
        repo.update(juan.id, email="gian@example.com")
    assert repo.get(juan.id).email == "juan@example.com"
