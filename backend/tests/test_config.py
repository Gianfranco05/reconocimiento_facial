import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_env_overrides_defaults(monkeypatch):
    monkeypatch.setenv("FACE_RECOGNITION_THRESHOLD", "0.35")
    monkeypatch.setenv("RECOGNITION_COOLDOWN_SECONDS", "5")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    settings = Settings(_env_file=None)
    assert settings.face_recognition_threshold == 0.35
    assert settings.recognition_cooldown_seconds == 5
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_privacy_defaults(monkeypatch):
    for var in ("SAVE_IMAGES", "SAVE_VIDEO", "SAVE_EVENTS"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.save_images is False
    assert settings.save_video is False
    assert settings.save_events is True


@pytest.mark.parametrize(
    "var,value",
    [
        ("FACE_RECOGNITION_THRESHOLD", "-0.1"),
        ("CAMERA_FPS", "0"),
        ("MAX_FACES", "0"),
        ("LOG_LEVEL", "VERBOSE"),
    ],
)
def test_invalid_values_rejected(monkeypatch, var, value):
    monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_strong_secret_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", secret_key="corta")
    settings = Settings(_env_file=None, environment="production", secret_key="k" * 40)
    assert settings.cookie_secure is True


def test_cors_wildcard_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins="*")


def test_weak_dev_secret_is_not_used_for_signing():
    from app.core.security import signing_key

    assert signing_key(Settings(_env_file=None)) != "change_me"
    strong = "s" * 40
    assert signing_key(Settings(_env_file=None, secret_key=strong)) == strong


def test_empty_env_values_count_as_unset(monkeypatch):
    for var in ("API_DOCS", "EMBEDDING_ENCRYPTION_KEY", "SECRET_KEY", "FACE_RECOGNITION_THRESHOLD"):
        monkeypatch.setenv(var, "")
    settings = Settings(_env_file=None)
    assert settings.api_docs is None and settings.api_docs_enabled is True
    assert settings.embedding_encryption_key is None
    assert settings.face_recognition_threshold == 0.63


def test_env_example_is_valid():
    from app.core.config import PROJECT_ROOT

    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")
    assert settings.embedding_encryption_key is None  # vacía en el ejemplo: hay que completarla
