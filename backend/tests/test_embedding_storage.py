import numpy as np
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, InvalidEmbeddingError
from app.core.security import EmbeddingCipher
from app.database.models import FaceEmbedding
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.person_repository import PersonRepository
from app.services.face_recognizer import FaceRecognizer


def random_unit(dim: int = 128, seed: int = 0) -> np.ndarray:
    vector = np.random.default_rng(seed).normal(size=dim).astype(np.float32)
    return vector / np.linalg.norm(vector)


def test_embedding_is_stored_encrypted(db_session, cipher):
    person = PersonRepository(db_session).create("Gian")
    vector = random_unit()
    record = EmbeddingRepository(db_session, cipher).add(person.id, vector, "sface_2021dec")

    raw = db_session.scalar(select(FaceEmbedding.embedding).where(FaceEmbedding.id == record.id))
    assert vector.tobytes() not in bytes(raw)
    assert record.dimension == 128
    np.testing.assert_allclose(cipher.decrypt(raw, 128), vector, rtol=1e-6)


def test_other_key_cannot_decrypt(cipher):
    token = cipher.encrypt(random_unit())
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingCipher(Fernet.generate_key()).decrypt(token, 128)


def test_tampered_embedding_detected(cipher):
    token = bytearray(cipher.encrypt(random_unit()))
    token[40] ^= 0x01
    with pytest.raises(InvalidEmbeddingError):
        cipher.decrypt(bytes(token), 128)


def test_wrong_dimension_detected(cipher):
    with pytest.raises(InvalidEmbeddingError):
        cipher.decrypt(cipher.encrypt(random_unit(64)), 128)


def test_invalid_embedding_not_stored(db_session, cipher):
    person = PersonRepository(db_session).create("Gian")
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingRepository(db_session, cipher).add(person.id, np.zeros(128, dtype=np.float32), "sface_2021dec")


def test_cipher_requires_configured_key():
    with pytest.raises(ConfigurationError):
        EmbeddingCipher.from_settings(Settings(_env_file=None, embedding_encryption_key=None))
    with pytest.raises(ConfigurationError):
        EmbeddingCipher("no-es-una-clave")


def test_load_known_only_active_people_and_matching_model(db_session, cipher):
    people = PersonRepository(db_session)
    embeddings = EmbeddingRepository(db_session, cipher)
    active = people.create("Ana", "García")
    inactive = people.create("Pedro")
    people.update(inactive.id, active=False)

    embeddings.add(active.id, random_unit(seed=1), "sface_2021dec")
    embeddings.add(active.id, random_unit(seed=2), "sface_2021dec")
    embeddings.add(active.id, random_unit(seed=3), "otro_modelo")
    embeddings.add(inactive.id, random_unit(seed=4), "sface_2021dec")

    known = embeddings.load_known("sface_2021dec")
    assert len(known) == 2
    assert {k.person_id for k in known} == {str(active.id)}
    assert known[0].person_name == "Ana García"

    recognizer = FaceRecognizer(0.63, "sface_2021dec", 128)
    recognizer.load(known)
    result = recognizer.recognize(random_unit(seed=2))
    assert result.recognized and result.person_id == str(active.id)
    assert not recognizer.recognize(random_unit(seed=4)).recognized
