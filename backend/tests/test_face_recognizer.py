"""Tests de la regla de decisión con vectores sintéticos (sin modelos)."""

import numpy as np
import pytest

from app.core.exceptions import InvalidEmbeddingError
from app.services.face_recognizer import FaceRecognizer, KnownEmbedding

DIM = 8
MODEL = "test_model"


def unit(*values: float) -> np.ndarray:
    vector = np.zeros(DIM, dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)


def at_distance(base: np.ndarray, distance: float) -> np.ndarray:
    """Vector unitario cuya distancia coseno a `base` (eje 0) es exactamente `distance`."""
    cos = 1.0 - distance
    return unit(cos, np.sqrt(max(0.0, 1.0 - cos**2)))


@pytest.fixture
def recognizer() -> FaceRecognizer:
    r = FaceRecognizer(threshold=0.4, model_version=MODEL, dimension=DIM)
    r.load(
        [
            KnownEmbedding("id-gian", "Gianfranco", unit(1), MODEL),
            KnownEmbedding("id-juan", "Juan", unit(0, 0, 1), MODEL),
        ]
    )
    return r


def test_known_person(recognizer):
    result = recognizer.recognize(at_distance(unit(1), 0.1))
    assert result.recognized
    assert result.person_id == "id-gian"
    assert result.person_name == "Gianfranco"
    assert result.distance == pytest.approx(0.1, abs=1e-3)
    assert result.confidence == pytest.approx(1 - 0.1 / 0.8, abs=1e-3)


def test_unknown_person(recognizer):
    result = recognizer.recognize(unit(0, 0, 0, 0, 1))
    assert not result.recognized
    assert result.person_id is None and result.person_name is None
    assert result.confidence == 0.0
    assert result.distance == pytest.approx(1.0, abs=1e-3)


def test_closest_is_not_enough_threshold_decides(recognizer):
    # Gianfranco es el candidato más cercano, pero está fuera del threshold.
    query = at_distance(unit(1), 0.45)
    assert not recognizer.recognize(query).recognized
    recognizer.threshold = 0.5
    result = recognizer.recognize(query)
    assert result.recognized and result.person_name == "Gianfranco"


def test_threshold_boundary_is_inclusive(recognizer):
    result = recognizer.recognize(at_distance(unit(1), 0.3999))
    assert result.recognized
    assert result.confidence == pytest.approx(0.5, abs=1e-3)


@pytest.mark.parametrize("value", [0.0, -0.1, 2.5])
def test_invalid_threshold_rejected(recognizer, value):
    with pytest.raises(ValueError):
        recognizer.threshold = value


def test_multiple_samples_per_person_use_the_closest(recognizer):
    profile = unit(0, 1)
    recognizer.add(KnownEmbedding("id-gian", "Gianfranco", profile, MODEL))
    # Lejos de la muestra frontal de Gianfranco, pero muy cerca de su perfil.
    result = recognizer.recognize(unit(0.1, 1))
    assert result.recognized and result.person_id == "id-gian"
    assert recognizer.known_people == 2
    assert recognizer.sample_count == 3


def test_empty_gallery_returns_unknown():
    r = FaceRecognizer(0.4, MODEL, DIM)
    result = r.recognize(unit(1))
    assert not result.recognized and result.distance is None


def test_remove_person(recognizer):
    recognizer.remove_person("id-gian")
    assert not recognizer.recognize(unit(1)).recognized
    assert recognizer.known_people == 1


@pytest.mark.parametrize(
    "embedding",
    [
        np.zeros(DIM, dtype=np.float32),
        np.ones(DIM + 1, dtype=np.float32),
        np.ones((2, DIM), dtype=np.float32),
        np.array([np.nan] * DIM, dtype=np.float32),
        np.array(["a"] * DIM),
        [1.0] * DIM,
    ],
    ids=["zero", "wrong-dim", "2d", "nan", "strings", "list"],
)
def test_invalid_query_embedding_raises(recognizer, embedding):
    with pytest.raises(InvalidEmbeddingError):
        recognizer.recognize(embedding)


def test_embeddings_from_another_model_rejected(recognizer):
    with pytest.raises(InvalidEmbeddingError):
        recognizer.add(KnownEmbedding("id-x", "X", unit(1), "otro_modelo"))


def test_invalid_entry_does_not_replace_gallery(recognizer):
    with pytest.raises(InvalidEmbeddingError):
        recognizer.load([KnownEmbedding("id-x", "X", np.zeros(DIM), MODEL)])
    assert recognizer.sample_count == 2
