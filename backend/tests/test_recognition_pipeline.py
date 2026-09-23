"""Tests de extremo a extremo con modelos reales (YuNet + SFace) y fotos reales."""

import numpy as np
import pytest

from app.core.config import Settings
from app.core.exceptions import (
    ConfigurationError,
    EmbeddingError,
    FaceNotFoundError,
    FaceTooSmallError,
    MultipleFacesError,
)
from app.services.embedding_service import cosine_distance
from app.services.face_detector import BoundingBox, DetectedFace
from app.services.face_recognizer import KnownEmbedding
from app.services.recognition_pipeline import build_recognition_pipeline
from tests.conftest import SFACE_THRESHOLD, load_fixture, side_by_side


def enroll(pipeline, person_id: str, name: str, fixture: str) -> None:
    embedding = pipeline.extract_single_embedding(load_fixture(fixture))
    pipeline.recognizer.add(KnownEmbedding(person_id, name, embedding, pipeline.embedder.model_version))


def test_embedding_is_normalized_128d(pipeline):
    embedding = pipeline.extract_single_embedding(load_fixture("obama_2012.jpg"))
    assert embedding.shape == (128,)
    assert embedding.dtype == np.float32
    assert np.linalg.norm(embedding) == pytest.approx(1.0, abs=1e-4)


def test_same_person_closer_than_different_people(pipeline):
    obama_a = pipeline.extract_single_embedding(load_fixture("obama_2012.jpg"))
    obama_b = pipeline.extract_single_embedding(load_fixture("obama_2009.jpg"))
    biden = pipeline.extract_single_embedding(load_fixture("biden.jpg"))
    assert cosine_distance(obama_a, obama_b) < SFACE_THRESHOLD < cosine_distance(obama_a, biden)


def test_known_person_recognized_from_a_different_photo(pipeline):
    enroll(pipeline, "id-obama", "Obama", "obama_2012.jpg")
    [analysis] = pipeline.process(load_fixture("obama_2009.jpg"))
    result = analysis.recognition
    assert result.recognized
    assert result.person_id == "id-obama"
    assert result.distance <= SFACE_THRESHOLD
    assert 0.5 < result.confidence <= 1.0


def test_unknown_person(pipeline):
    enroll(pipeline, "id-obama", "Obama", "obama_2012.jpg")
    [analysis] = pipeline.process(load_fixture("biden.jpg"))
    assert not analysis.recognition.recognized
    assert analysis.recognition.confidence == 0.0
    assert analysis.recognition.distance > SFACE_THRESHOLD


def test_multiple_faces_processed_independently(pipeline):
    enroll(pipeline, "id-obama", "Obama", "obama_2012.jpg")
    enroll(pipeline, "id-harris", "Harris", "harris.jpg")

    scene = side_by_side("obama_2009.jpg", "biden.jpg", "harris.jpg")
    analyses = sorted(pipeline.process(scene), key=lambda a: a.face.bbox.x)

    assert len(analyses) == 3
    names = [a.recognition.person_name if a.recognition.recognized else None for a in analyses]
    assert names == ["Obama", None, "Harris"]


def test_enrollment_requires_exactly_one_face(pipeline):
    with pytest.raises(FaceNotFoundError):
        pipeline.extract_single_embedding(np.full((480, 640, 3), 127, dtype=np.uint8))
    with pytest.raises(MultipleFacesError):
        pipeline.extract_single_embedding(side_by_side("obama_2012.jpg", "biden.jpg"))


def test_small_face_is_skipped_not_fatal(pipeline):
    pipeline.min_face_size = 10_000
    [analysis] = pipeline.process(load_fixture("biden.jpg"))
    assert analysis.recognition is None
    assert "mínimo" in analysis.error
    with pytest.raises(FaceTooSmallError):
        pipeline.extract_single_embedding(load_fixture("biden.jpg"))


def test_embedder_requires_yunet_keypoints(embedder):
    face_without_keypoints = DetectedFace(BoundingBox(0, 0, 100, 100), 0.9, [])
    with pytest.raises(EmbeddingError):
        embedder.embed(load_fixture("lena.jpg"), face_without_keypoints)


def test_recognition_requires_yunet_backend():
    with pytest.raises(ConfigurationError):
        build_recognition_pipeline(Settings(_env_file=None, face_detector_backend="mediapipe"))
