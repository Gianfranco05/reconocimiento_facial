"""Excepciones de dominio de FaceTrack.

Los servicios lanzan estas excepciones; las capas superiores (CLI, API)
deciden cómo presentarlas al usuario.
"""


class FaceTrackError(Exception):
    """Base de todas las excepciones propias."""


class ModelNotFoundError(FaceTrackError):
    """No se encontró el archivo de un modelo de visión."""


class InvalidImageError(FaceTrackError):
    """Los bytes recibidos no son una imagen válida o soportada."""


class InvalidFrameError(FaceTrackError):
    """El frame recibido no es un array de imagen utilizable."""


class CameraUnavailableError(FaceTrackError):
    """La cámara no existe, está desconectada o en uso por otra aplicación."""


class ConfigurationError(FaceTrackError):
    """Combinación de configuración que no permite ejecutar la operación."""


class EmbeddingError(FaceTrackError):
    """No se pudo generar un embedding para un rostro."""


class InvalidEmbeddingError(FaceTrackError):
    """El embedding no tiene la forma o los valores esperados."""


class FaceNotFoundError(FaceTrackError):
    """No se detectó ningún rostro donde se esperaba uno."""


class MultipleFacesError(FaceTrackError):
    """Se detectó más de un rostro donde se esperaba exactamente uno."""


class FaceTooSmallError(FaceTrackError):
    """El rostro es demasiado chico para generar un embedding fiable."""


class NotFoundError(FaceTrackError):
    """El recurso pedido no existe."""


class DuplicateError(FaceTrackError):
    """Ya existe un recurso con ese valor único (por ejemplo, el email)."""


class LowQualityFaceError(FaceTrackError):
    """El rostro no alcanza la calidad mínima para registrarse (tamaño,
    nitidez o iluminación)."""


class UnsupportedMediaError(FaceTrackError):
    """El archivo subido no es de un formato de imagen aceptado."""


class PayloadTooLargeError(FaceTrackError):
    """El archivo supera el tamaño máximo permitido."""


class FaceConflictError(FaceTrackError):
    """La muestra facial no es coherente: no coincide con las muestras previas
    de la persona o coincide con otra persona registrada."""


class AuthenticationError(FaceTrackError):
    """Credenciales inválidas, sesión ausente, vencida o revocada."""


class PermissionDeniedError(FaceTrackError):
    """El usuario no tiene permiso para esta acción."""


class TooManyAttemptsError(FaceTrackError):
    """Demasiados intentos fallidos de inicio de sesión."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
