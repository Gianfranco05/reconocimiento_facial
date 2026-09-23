from pydantic import BaseModel

from app.services.runtime_config import RuntimeConfig


class PrivacyOut(BaseModel):
    """Garantías fijas de privacidad. No son configurables: el sistema no tiene
    ningún código que guarde imágenes o vídeo, ni envía datos fuera del equipo."""

    local_processing: bool = True
    save_images: bool = False
    save_video: bool = False
    embeddings_encrypted: bool = True


class ConfigOut(RuntimeConfig):
    privacy: PrivacyOut = PrivacyOut()
    model_version: str
