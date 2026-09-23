"""Fixtures compartidas.

Imágenes de prueba (tests/fixtures/):
- lena.jpg: imagen clásica de ejemplo de OpenCV.
- obama_2012.jpg, obama_2009.jpg, biden.jpg, harris.jpg: retratos oficiales de
  la Casa Blanca, de dominio público (Wikimedia Commons). Dos fotos distintas
  de la misma persona permiten probar "persona conocida" con datos reales.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.config import get_settings
from app.services.detectors.mediapipe_detector import MediaPipeFaceDetector
from app.services.detectors.yunet_detector import YuNetFaceDetector
from app.services.embedding_service import SFaceEmbedder
from app.services.face_recognizer import FaceRecognizer
from app.services.recognition_pipeline import RecognitionPipeline

FIXTURES = Path(__file__).parent / "fixtures"
SFACE_THRESHOLD = 0.63


def load_fixture(name: str) -> np.ndarray:
    image = cv2.imread(str(FIXTURES / name))
    assert image is not None, f"No se pudo leer la fixture {name}"
    return image


def _require(path: Path) -> Path:
    if not path.is_file():
        pytest.skip(f"Modelo no disponible en {path}; ejecutá python -m app.cli.download_models")
    return path


@pytest.fixture(scope="session")
def model_path() -> Path:
    return _require(get_settings().face_detector_model_path)


@pytest.fixture(scope="session")
def yunet_path() -> Path:
    return _require(get_settings().yunet_model_path)


@pytest.fixture(scope="session")
def sface_path() -> Path:
    return _require(get_settings().sface_model_path)


@pytest.fixture(params=["mediapipe", "yunet"])
def detector(request):
    """Ejecuta cada test de detección con ambos backends."""
    if request.param == "mediapipe":
        instance = MediaPipeFaceDetector(request.getfixturevalue("model_path"), min_confidence=0.5)
    else:
        instance = YuNetFaceDetector(request.getfixturevalue("yunet_path"), min_confidence=0.6)
    with instance:
        yield instance


@pytest.fixture(scope="session")
def embedder(sface_path) -> SFaceEmbedder:
    return SFaceEmbedder(sface_path)


@pytest.fixture
def pipeline(yunet_path, embedder) -> RecognitionPipeline:
    recognizer = FaceRecognizer(SFACE_THRESHOLD, embedder.model_version, embedder.dimension)
    with RecognitionPipeline(YuNetFaceDetector(yunet_path), embedder, recognizer) as p:
        yield p


@pytest.fixture
def single_face_image() -> np.ndarray:
    return load_fixture("lena.jpg")


@pytest.fixture
def multi_face_image() -> np.ndarray:
    # Dos rostros lado a lado (recorte de lena y su espejo). El modelo
    # short-range de BlazeFace solo detecta rostros grandes en el encuadre,
    # por eso se recorta alrededor de la cara en vez de usar la foto entera.
    image = load_fixture("lena.jpg")
    crop = image[138:462, 115:439]
    return np.hstack([crop, cv2.flip(crop, 1)])


def side_by_side(*names: str, height: int = 600) -> np.ndarray:
    """Compone varias fotos en una sola imagen horizontal (escena con N personas)."""
    images = []
    for name in names:
        image = load_fixture(name)
        images.append(cv2.resize(image, (int(image.shape[1] * height / image.shape[0]), height)))
    return np.hstack(images)


# Fixtures de base de datos (se saltean si PostgreSQL no está disponible) y de
# la API. Se importan acá para que pytest los registre en todos los tests.
from tests.api_fixtures import anon_client, app, client, engine, operator_client  # noqa: E402, F401
from tests.db_fixtures import (  # noqa: E402, F401
    cipher,
    committing_session_factory,
    db_engine,
    db_session,
    test_database_url,
)


@pytest.fixture(scope="session")
def landmarks():
    from app.services.landmark_service import LandmarkService

    path = _require(get_settings().face_landmarker_model_path)
    service = LandmarkService(path)
    yield service
    service.close()
