import numpy as np
import pytest

from app.core.config import Settings
from app.core.exceptions import InvalidFrameError, ModelNotFoundError
from app.services.detectors.mediapipe_detector import MediaPipeFaceDetector
from app.services.detectors.yunet_detector import YUNET_KEYPOINTS, YuNetFaceDetector
from app.services.face_detector import DetectionMode, create_face_detector
from tests.conftest import load_fixture, side_by_side


def test_valid_image_detects_one_face(detector, single_face_image):
    faces = detector.detect(single_face_image)

    assert len(faces) == 1
    face = faces[0]
    height, width = single_face_image.shape[:2]
    assert 0 <= face.bbox.x < face.bbox.x2 <= width
    assert 0 <= face.bbox.y < face.bbox.y2 <= height
    assert 0.5 <= face.score <= 1.0
    assert {kp.name for kp in face.keypoints} >= {"right_eye", "left_eye", "nose_tip"}


def test_image_without_face_returns_empty_list(detector):
    blank = np.full((480, 640, 3), 127, dtype=np.uint8)
    assert detector.detect(blank) == []


def test_multiple_faces_are_detected_independently(detector, multi_face_image):
    faces = detector.detect(multi_face_image)

    assert len(faces) == 2
    centers = sorted(face.bbox.center_x for face in faces)
    half = multi_face_image.shape[1] // 2
    assert centers[0] < half < centers[-1]


def test_results_sorted_by_score_and_capped(detector, multi_face_image):
    detector.max_faces = 1
    assert len(detector.detect(multi_face_image)) == 1


@pytest.mark.parametrize(
    "frame",
    [
        None,
        "no soy una imagen",
        np.zeros((0, 0, 3), dtype=np.uint8),
        np.zeros((100, 100), dtype=np.uint8),
        np.zeros((100, 100, 3), dtype=np.float32),
    ],
    ids=["none", "string", "empty", "grayscale", "float"],
)
def test_invalid_frames_raise(detector, frame):
    with pytest.raises(InvalidFrameError):
        detector.detect(frame)


def test_frames_of_different_sizes(detector, single_face_image, multi_face_image):
    # YuNet necesita reconfigurar el tamaño de entrada entre frames.
    assert len(detector.detect(single_face_image)) == 1
    assert len(detector.detect(multi_face_image)) == 2
    assert len(detector.detect(single_face_image)) == 1


def test_yunet_detects_small_faces_that_blazeface_misses(yunet_path, single_face_image):
    # Rostro que ocupa ~16% del ancho: fuera del alcance del modelo short-range.
    canvas = np.full((512, 1024, 3), 127, dtype=np.uint8)
    canvas[:, :512] = single_face_image
    with YuNetFaceDetector(yunet_path) as detector:
        faces = detector.detect(canvas)
    assert len(faces) == 1
    assert [kp.name for kp in faces[0].keypoints] == list(YUNET_KEYPOINTS)


def test_yunet_detects_three_people(yunet_path):
    with YuNetFaceDetector(yunet_path) as detector:
        assert len(detector.detect(side_by_side("obama_2012.jpg", "biden.jpg", "harris.jpg"))) == 3


def test_mediapipe_video_mode_accepts_consecutive_frames(model_path, single_face_image):
    with MediaPipeFaceDetector(model_path, mode=DetectionMode.VIDEO) as detector:
        # Timestamps repetidos o decrecientes no deben romper el detector.
        for timestamp in (100, 100, 50, None):
            assert len(detector.detect(single_face_image, timestamp)) == 1


@pytest.mark.parametrize("detector_class", [MediaPipeFaceDetector, YuNetFaceDetector])
def test_missing_model_raises(tmp_path, detector_class):
    with pytest.raises(ModelNotFoundError):
        detector_class(tmp_path / "no_existe.model")


@pytest.mark.parametrize(
    "backend,expected", [("yunet", YuNetFaceDetector), ("mediapipe", MediaPipeFaceDetector)]
)
def test_factory_respects_backend(model_path, yunet_path, backend, expected):
    settings = Settings(_env_file=None, face_detector_backend=backend)
    with create_face_detector(settings) as detector:
        assert isinstance(detector, expected)
        assert len(detector.detect(load_fixture("lena.jpg"))) == 1
