import time

import cv2
import numpy as np
import pytest

from app.core.exceptions import CameraUnavailableError
from app.services.camera_service import CameraService
from app.services.detectors.mediapipe_detector import MediaPipeFaceDetector
from app.services.face_detector import DetectionMode


class FakeCapture:
    """Sustituto de cv2.VideoCapture para probar sin hardware."""

    def __init__(self, frames, opened=True):
        self._frames = list(frames)
        self._opened = opened
        self.released = False

    def isOpened(self):
        return self._opened and not self.released

    def read(self):
        if not self._frames:
            return False, None
        return True, self._frames.pop(0)

    def release(self):
        self.released = True


def frame():
    return np.zeros((10, 10, 3), dtype=np.uint8)


def test_unavailable_camera_raises():
    capture = FakeCapture([], opened=False)
    service = CameraService(0, capture_factory=lambda _: capture)
    with pytest.raises(CameraUnavailableError):
        service.open()
    assert capture.released


def test_read_before_open_raises():
    with pytest.raises(CameraUnavailableError):
        CameraService(0).read()


def test_frames_stop_when_source_ends_and_camera_is_released():
    capture = FakeCapture([frame(), frame(), frame()])
    with CameraService(0, fps=60, capture_factory=lambda _: capture) as camera:
        assert len(list(camera.frames())) == 3
    assert capture.released
    assert not camera.is_open


def test_fps_is_limited():
    capture = FakeCapture([frame() for _ in range(4)])
    with CameraService(0, fps=20, capture_factory=lambda _: capture) as camera:
        start = time.monotonic()
        list(camera.frames())
        elapsed = time.monotonic() - start
    # 4 frames + 1 lectura final a 20 FPS => al menos ~4 intervalos de 50 ms.
    assert elapsed >= 0.18


def test_invalid_fps_rejected():
    with pytest.raises(ValueError):
        CameraService(0, fps=0)


def test_real_video_file_through_detector(tmp_path, single_face_image, model_path):
    path = tmp_path / "clip.avi"
    height, width = single_face_image.shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (width, height))
    for _ in range(5):
        writer.write(single_face_image)
    writer.release()

    with MediaPipeFaceDetector(model_path, mode=DetectionMode.VIDEO) as video_detector, CameraService(str(path), fps=60) as camera:
        counts = [len(video_detector.detect(f)) for f in camera.frames()]
    assert counts == [1] * 5
