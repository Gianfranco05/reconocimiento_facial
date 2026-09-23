import cv2
import pytest

from app.core.exceptions import InvalidImageError
from app.utils.image import decode_image


def test_decode_valid_jpeg(single_face_image):
    ok, encoded = cv2.imencode(".jpg", single_face_image)
    assert ok
    image = decode_image(encoded.tobytes())
    assert image.shape == single_face_image.shape


@pytest.mark.parametrize(
    "data",
    [b"", b"esto no es una imagen", b"\xff\xd8\xff\xe0" + b"\x00" * 64],
    ids=["empty", "text", "truncated-jpeg"],
)
def test_decode_corrupt_image_raises(data):
    with pytest.raises(InvalidImageError):
        decode_image(data)
