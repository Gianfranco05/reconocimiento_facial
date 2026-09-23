"""Configuración central de FaceTrack.

Todos los valores se leen de variables de entorno (o de un archivo `.env`).
Ningún módulo debe leer `os.environ` directamente: siempre usar `get_settings()`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor de ejemplo de SECRET_KEY (no es un secreto): se rechaza en producción.
PLACEHOLDER_SECRET = "change_me"  # noqa: S105

# backend/app/core/config.py -> raíz del repositorio
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # "VAR=" vacía cuenta como no definida (usa el default): así .env.example
        # puede listar variables sin valor, y una clave vacía da "falta la clave"
        # en vez de un error confuso.
        env_ignore_empty=True,
    )

    # --- General ---
    app_name: str = "FaceTrack"
    # "production" exige SECRET_KEY fuerte y cookies Secure (solo HTTPS).
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    # "text" para consola; "json" (una línea JSON por registro) para producción.
    log_format: Literal["text", "json"] = "text"
    # Zona horaria para decidir qué es "hoy" (asistencia, estadísticas).
    # En la base todas las fechas se guardan en UTC.
    timezone: str = "America/Argentina/Buenos_Aires"

    # --- Modelos ---
    models_dir: Path = PROJECT_ROOT / "models"
    face_detector_model: str = "blaze_face_short_range.tflite"
    yunet_model: str = "face_detection_yunet_2023mar.onnx"
    sface_model: str = "face_recognition_sface_2021dec.onnx"
    face_landmarker_model: str = "face_landmarker.task"

    # --- Detección ---
    # "yunet" es obligatorio para reconocimiento (aporta los 5 keypoints que usa SFace).
    face_detector_backend: Literal["yunet", "mediapipe"] = "yunet"
    detection_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    max_faces: int = Field(default=10, ge=1, le=50)

    # --- Reconocimiento ---
    # Distancia coseno máxima (0 = idénticos, 2 = opuestos) para aceptar una
    # coincidencia. 0.63 equivale a la similitud coseno 0.363 recomendada por
    # OpenCV para SFace. Más bajo = más estricto (menos falsos positivos).
    face_recognition_threshold: float = Field(default=0.63, ge=0.0, le=2.0)
    # Rostros más chicos (en píxeles) no generan embeddings fiables.
    min_face_size: int = Field(default=40, ge=10, le=1000)
    # Ventana en la que no se vuelve a registrar un evento de la misma persona
    # (o, para desconocidos, de la misma cámara).
    recognition_cooldown_seconds: int = Field(default=10, ge=0, le=3600)

    # --- Registro facial (calidad mínima de cada muestra) ---
    # Valores calibrados con las fotos de tests/fixtures: fotos nítidas dan
    # nitidez >= 800 y un desenfoque fuerte (Gauss 21x21) <= 90.
    enrollment_min_face_size: int = Field(default=80, ge=40, le=2000)
    enrollment_min_detection_score: float = Field(default=0.8, ge=0.0, le=1.0)
    enrollment_min_sharpness: float = Field(default=100.0, ge=0.0)
    enrollment_min_brightness: float = Field(default=50.0, ge=0.0, le=255.0)
    enrollment_max_brightness: float = Field(default=210.0, ge=0.0, le=255.0)

    # --- Liveness (prueba de vida básica por desafíos) ---
    liveness_timeout_seconds: int = Field(default=20, ge=5, le=120)
    liveness_yaw_degrees: float = Field(default=20.0, ge=5.0, le=60.0)
    liveness_pitch_degrees: float = Field(default=12.0, ge=5.0, le=45.0)
    liveness_blink_close_ratio: float = Field(default=0.65, gt=0.0, lt=1.0)
    liveness_blink_open_ratio: float = Field(default=0.85, gt=0.0, lt=1.0)

    # --- Asistencia ---
    # Tiempo mínimo entre dos registros de asistencia de la misma persona. Evita
    # que alguien que sigue frente a la cámara marque ENTRY y EXIT seguidos.
    attendance_min_interval_minutes: int = Field(default=10, ge=0, le=24 * 60)

    # --- Cámara ---
    camera_index: int = Field(default=0, ge=0)
    camera_fps: int = Field(default=15, ge=1, le=60)
    # Identificador de la cámara que se guarda en cada evento de reconocimiento.
    camera_id: str = Field(default="default", min_length=1, max_length=64)

    # --- Privacidad ---
    save_images: bool = False
    save_video: bool = False
    save_events: bool = True

    # --- Base de datos ---
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5433/facetrack"
    test_database_url: str = "postgresql://postgres:postgres@127.0.0.1:5433/facetrack_test"
    # Clave Fernet para cifrar los embeddings en la base. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Si se pierde, los embeddings guardados no se pueden recuperar.
    embedding_encryption_key: SecretStr | None = None

    # --- API ---
    max_upload_mb: float = Field(default=5.0, gt=0, le=50)
    # Documentación interactiva en /api/docs. Por defecto: activa en
    # desarrollo, desactivada en producción (describe toda la superficie de la API).
    api_docs: bool | None = None

    # --- Seguridad ---
    # Firma los JWT de sesión. En producción: al menos 32 caracteres aleatorios,
    # p. ej. python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: SecretStr = SecretStr(PLACEHOLDER_SECRET)
    access_token_minutes: int = Field(default=480, ge=5, le=7 * 24 * 60)
    login_max_attempts: int = Field(default=5, ge=1, le=100)
    login_lockout_minutes: int = Field(default=5, ge=1, le=24 * 60)
    cors_origins: str = "http://localhost:5173"

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"LOG_LEVEL inválido: {value}")
        return value

    @model_validator(mode="after")
    def _validate_security(self) -> "Settings":
        if "*" in self.cors_origin_list:
            # Con cookies de sesión (credentials) el comodín es inseguro y los navegadores lo rechazan.
            raise ValueError("CORS_ORIGINS no admite '*': listá los orígenes permitidos.")
        if self.environment == "production":
            secret = self.secret_key.get_secret_value()
            if secret == PLACEHOLDER_SECRET or len(secret) < 32:
                raise ValueError(
                    "En producción SECRET_KEY debe tener al menos 32 caracteres y no ser el valor de ejemplo."
                )
        return self

    @property
    def api_docs_enabled(self) -> bool:
        return self.api_docs if self.api_docs is not None else self.environment == "development"

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    @field_validator("save_images", "save_video")
    @classmethod
    def _reject_media_storage(cls, value: bool) -> bool:
        # No existe código que guarde imágenes o vídeo: activarlo sería una
        # opción falsa. Se rechaza explícitamente en vez de ignorarla.
        if value:
            raise ValueError("Guardar imágenes o vídeo no está soportado (privacidad por diseño).")
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"TIMEZONE inválida: {value}") from exc
        return value

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def face_detector_model_path(self) -> Path:
        return self.models_dir / self.face_detector_model

    @property
    def yunet_model_path(self) -> Path:
        return self.models_dir / self.yunet_model

    @property
    def sface_model_path(self) -> Path:
        return self.models_dir / self.sface_model

    @property
    def face_landmarker_model_path(self) -> Path:
        return self.models_dir / self.face_landmarker_model

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
