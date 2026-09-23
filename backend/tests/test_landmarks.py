"""Landmarks con el modelo real: malla, apertura de ojos y orientación de la cabeza."""

import cv2
import numpy as np
import pytest

from app.core.exceptions import InvalidFrameError, ModelNotFoundError
from app.services.landmark_service import LandmarkService, eye_aspect_ratio, head_pose_from_matrix
from tests.conftest import load_fixture, side_by_side
from tests.liveness_helpers import close_eyes, rotate

PORTRAITS = ["obama_2012.jpg", "obama_2009.jpg", "biden.jpg", "harris.jpg", "lena.jpg"]


def single(landmarks, image):
    faces = landmarks.detect(image)
    assert len(faces) == 1
    return faces[0]


def test_mesh_has_478_points_inside_the_face(landmarks):
    image = load_fixture("harris.jpg")
    face = single(landmarks, image)
    assert face.points.shape == (478, 2)
    h, w = image.shape[:2]
    assert (face.points[:, 0] >= 0).all() and (face.points[:, 0] <= w).all()
    assert 0 < face.bbox.width < w and 0 < face.bbox.height < h


def test_multiple_close_faces(landmarks, multi_face_image):
    assert len(landmarks.detect(multi_face_image)) == 2


def test_distant_faces_are_missed_known_limitation(landmarks):
    # Face Landmarker usa internamente el detector short-range de BlazeFace: en
    # una escena amplia con rostros chicos solo ve alguno. Para liveness (una
    # persona cerca de la cámara) alcanza; para escenas usar YuNet.
    assert len(landmarks.detect(side_by_side("obama_2012.jpg", "biden.jpg", "harris.jpg"))) < 3


def test_no_face(landmarks):
    assert landmarks.detect(np.full((480, 640, 3), 127, np.uint8)) == []


def test_invalid_frame(landmarks):
    with pytest.raises(InvalidFrameError):
        landmarks.detect(np.zeros((10, 10), np.uint8))


def test_missing_model(tmp_path):
    with pytest.raises(ModelNotFoundError):
        LandmarkService(tmp_path / "no.task")


@pytest.mark.parametrize("name", PORTRAITS)
def test_closed_eyes_lower_ear(landmarks, name):
    image = load_fixture(name)
    open_ear = single(landmarks, image).eyes.ear
    closed_ear = single(landmarks, close_eyes(image, landmarks)).eyes.ear
    assert open_ear > 0.15
    # Por debajo del umbral de "cerrado" del detector de parpadeo (65 % de lo normal).
    assert closed_ear < 0.65 * open_ear


def test_frontal_portraits_have_small_yaw_and_roll(landmarks):
    for name in ["obama_2012.jpg", "obama_2009.jpg", "biden.jpg", "harris.jpg"]:
        pose = single(landmarks, load_fixture(name)).head_pose
        assert abs(pose.yaw) < 8 and abs(pose.roll) < 8, name


def test_yaw_sign_follows_head_direction(landmarks):
    # En la foto de Lena la nariz apunta hacia la derecha de la imagen: ella gira
    # hacia SU izquierda, así que el yaw es negativo. Espejada, se invierte.
    image = load_fixture("lena.jpg")
    yaw = single(landmarks, image).head_pose.yaw
    mirrored_yaw = single(landmarks, cv2.flip(image, 1)).head_pose.yaw
    assert yaw < -12
    assert mirrored_yaw > 12
    assert abs(yaw + mirrored_yaw) < 3


@pytest.mark.parametrize("degrees", [20, -20])
def test_roll_follows_image_rotation(landmarks, degrees):
    base = single(landmarks, load_fixture("harris.jpg")).head_pose.roll
    rotated = single(landmarks, rotate(load_fixture("harris.jpg"), degrees)).head_pose.roll
    assert rotated - base == pytest.approx(degrees, abs=5)


def test_ear_formula():
    points = np.zeros((478, 2), np.float32)
    idx = (33, 160, 158, 133, 153, 144)
    points[33], points[133] = (0, 0), (10, 0)  # ancho 10
    points[160], points[144] = (3, -2), (3, 2)  # alto 4
    points[158], points[153] = (7, -2), (7, 2)  # alto 4
    assert eye_aspect_ratio(points, idx) == pytest.approx(0.4)


def test_head_pose_from_identity_matrix_is_frontal():
    pose = head_pose_from_matrix(np.eye(4))
    assert (pose.yaw, pose.pitch, pose.roll) == (0, 0, 0)
