"""Herramientas de consola: personas, reconocimiento, detección y descarga de modelos.

No abren ventanas (cv2.imshow se reemplaza) ni usan la red (urlretrieve se
reemplaza). Las que usan la base trabajan sobre la sesión del test.
"""

import json
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
import pytest
from cryptography.fernet import Fernet

from app.cli import detect as detect_cli
from app.cli import download_models
from app.cli import persons as persons_cli
from app.cli import recognize as recognize_cli
from app.core.config import Settings
from app.database.models import FaceEmbedding, Person, RecognitionEvent
from app.services.face_detector import BoundingBox, DetectedFace, Keypoint
from app.utils.drawing import draw_faces, draw_recognition, draw_status
from tests.conftest import FIXTURES


@pytest.fixture
def no_windows(monkeypatch):
    monkeypatch.setattr(cv2, "imshow", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *a, **k: ord("q"))
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)


@pytest.fixture
def cli_db(db_session, monkeypatch, yunet_path, sface_path):
    """Las CLIs usan la sesión del test y una clave de cifrado de prueba."""

    @contextmanager
    def scope():
        yield db_session
        db_session.flush()

    settings = Settings(_env_file=None, embedding_encryption_key=Fernet.generate_key().decode())
    for module in (persons_cli, recognize_cli):
        monkeypatch.setattr(module, "session_scope", scope)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return db_session


# --- persons ---


def test_persons_add_enroll_list_deactivate_delete(cli_db, capsys):
    assert persons_cli.main(["add", "--first-name", "Kamala", "--last-name", "Harris"]) == 0
    person = cli_db.query(Person).one()

    photos = [str(FIXTURES / "harris.jpg"), str(FIXTURES / "biden.jpg"), str(FIXTURES / "no-existe.jpg")]
    assert persons_cli.main(["enroll", str(person.id), *photos]) == 0
    out = capsys.readouterr().out
    # Harris se registra; Biden no coincide con Harris; el archivo inexistente se saltea.
    assert "Muestras registradas: 1/3" in out
    assert cli_db.query(FaceEmbedding).count() == 1

    assert persons_cli.main(["list"]) == 0
    assert "Kamala Harris" in capsys.readouterr().out

    assert persons_cli.main(["deactivate", str(person.id)]) == 0
    assert person.active is False
    assert persons_cli.main(["delete", str(person.id)]) == 0
    assert cli_db.query(Person).count() == 0


def test_persons_errors_return_exit_code_1(cli_db):
    import uuid

    assert persons_cli.main(["delete", str(uuid.uuid4())]) == 1
    persons_cli.main(["add", "--first-name", "Ana", "--email", "ana@x.com"])
    assert persons_cli.main(["add", "--first-name", "Otra", "--email", "ANA@x.com"]) == 1


# --- recognize ---


def test_recognize_gallery_image_headless(tmp_path, no_windows, capsys, yunet_path, sface_path):
    gallery = tmp_path / "gallery"
    (gallery / "Harris").mkdir(parents=True)
    (gallery / "Harris" / "foto.jpg").write_bytes((FIXTURES / "harris.jpg").read_bytes())
    (gallery / "Harris" / "rota.jpg").write_bytes(b"no es una imagen")
    (gallery / "Harris" / "notas.txt").write_text("se ignora")

    scene = tmp_path / "escena.jpg"
    left, right = cv2.imread(str(FIXTURES / "harris.jpg")), cv2.imread(str(FIXTURES / "biden.jpg"))
    cv2.imwrite(str(scene), np.hstack([left, cv2.resize(right, (left.shape[1], left.shape[0]))]))

    assert recognize_cli.main(["--gallery", str(gallery), "--image", str(scene), "--headless"]) == 0
    output = json.loads(capsys.readouterr().out)
    names = sorted(r["name"] for r in output["results"])
    assert output["faces_detected"] == 2 and names == ["Desconocido", "Harris"]


def test_recognize_from_database_records_events(cli_db, no_windows, capsys):
    persons_cli.main(["add", "--first-name", "Kamala"])
    person = cli_db.query(Person).one()
    persons_cli.main(["enroll", str(person.id), str(FIXTURES / "harris.jpg")])
    capsys.readouterr()

    args = ["--db", "--attendance", "--image", str(FIXTURES / "harris.jpg"), "--headless"]
    assert recognize_cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["name"] == "Kamala"
    assert cli_db.query(RecognitionEvent).count() == 1


def test_recognize_argument_errors(tmp_path, capsys):
    with pytest.raises(SystemExit):
        recognize_cli.main(["--gallery", str(tmp_path), "--attendance"])  # --attendance requiere --db
    assert recognize_cli.main(["--gallery", str(tmp_path / "no-existe"), "--image", "x.jpg"]) == 1


# --- detect ---


def test_detect_image(no_windows, model_path, yunet_path):
    assert detect_cli.main(["--image", str(FIXTURES / "harris.jpg")]) == 0


def test_detect_missing_video_and_camera(no_windows, yunet_path, tmp_path):
    assert detect_cli.main(["--video", str(tmp_path / "no.mp4")]) == 1
    assert detect_cli.main(["--camera", "9"]) == 1  # no hay cámara 9


def test_detect_video_file(no_windows, yunet_path, tmp_path):
    path = tmp_path / "clip.avi"
    frame = cv2.imread(str(FIXTURES / "lena.jpg"))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (frame.shape[1], frame.shape[0]))
    for _ in range(3):
        writer.write(frame)
    writer.release()
    assert detect_cli.main(["--video", str(path)]) == 0


# --- download_models ---


def test_download_models_skips_existing_and_downloads_missing(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, models_dir=tmp_path)
    monkeypatch.setattr(download_models, "get_settings", lambda: settings)
    names = list(download_models.MODELS)
    (tmp_path / names[0]).write_bytes(b"ya estaba")
    downloaded = []

    def fake_retrieve(url, target):
        assert url.startswith("https://")
        downloaded.append(url)
        Path(target).write_bytes(b"modelo")

    monkeypatch.setattr(download_models.urllib.request, "urlretrieve", fake_retrieve)
    assert download_models.main() == 0
    assert len(downloaded) == len(names) - 1
    assert (tmp_path / names[0]).read_bytes() == b"ya estaba"
    assert all((tmp_path / n).is_file() for n in names)
    assert not list(tmp_path.glob("*.part"))


def test_download_failure_leaves_no_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(download_models, "get_settings", lambda: Settings(_env_file=None, models_dir=tmp_path))

    def failing(url, target):
        Path(target).write_bytes(b"a medias")
        raise OSError("sin red")

    monkeypatch.setattr(download_models.urllib.request, "urlretrieve", failing)
    assert download_models.main() == 1
    assert list(tmp_path.iterdir()) == []


def test_download_refuses_non_https(tmp_path, monkeypatch):
    monkeypatch.setattr(download_models, "get_settings", lambda: Settings(_env_file=None, models_dir=tmp_path))
    monkeypatch.setattr(download_models, "MODELS", {"x.onnx": "file:///etc/passwd"})
    monkeypatch.setattr(download_models.urllib.request, "urlretrieve", lambda *a: pytest.fail("no debe descargar"))
    assert download_models.main() == 1


# --- drawing ---


def test_drawing_marks_the_frame():
    face = DetectedFace(BoundingBox(20, 30, 60, 60), 0.9, [Keypoint("nose_tip", 50, 60)])
    for draw in (
        lambda f: draw_faces(f, [face]),
        lambda f: draw_recognition(f, face, "Ana", 0.9),
        lambda f: draw_recognition(f, face, None, 0.0),
        lambda f: draw_recognition(f, face, None, -1),
        lambda f: draw_status(f, "Rostros: 1"),
    ):
        frame = np.zeros((120, 160, 3), np.uint8)
        assert draw(frame) is frame and frame.any()

