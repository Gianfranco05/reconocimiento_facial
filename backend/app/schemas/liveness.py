import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import BoundingBoxOut
from app.schemas.reconocimiento import AttendanceMarkOut
from app.services.liveness_service import Challenge, LivenessStatus

DISCLAIMER = (
    "Prueba de vida básica por desafíos: detecta fotos estáticas, pero no es un mecanismo de "
    "seguridad biométrica de alta garantía (un vídeo o una máscara pueden superarla)."
)


class HeadPoseOut(BaseModel):
    yaw: float = Field(description="Grados; > 0 = la persona gira hacia su derecha")
    pitch: float = Field(description="Grados; > 0 = la persona mira hacia arriba")
    roll: float = Field(description="Grados; > 0 = rotación antihoraria en la imagen")


class EyesOut(BaseModel):
    left_ear: float
    right_ear: float
    left_blink_score: float
    right_blink_score: float


class FaceLandmarksOut(BaseModel):
    bbox: BoundingBoxOut
    head_pose: HeadPoseOut
    eyes: EyesOut
    # [[x, y], ...] en píxeles de la imagen enviada (478 puntos). Vacío si no se pidieron.
    points: list[list[float]] = []


class LandmarksOut(BaseModel):
    faces_detected: int
    image_width: int
    image_height: int
    faces: list[FaceLandmarksOut]


class LivenessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_attendance: bool = False
    camera_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")


class ChallengeOut(BaseModel):
    type: Challenge
    instruction: str
    completed: bool


class LivenessPersonOut(BaseModel):
    person_id: uuid.UUID
    name: str
    confidence: float


class LivenessSessionOut(BaseModel):
    id: uuid.UUID
    status: LivenessStatus
    reason: str | None
    challenges: list[ChallengeOut]
    current_instruction: str | None
    created_at: datetime
    expires_at: datetime
    person: LivenessPersonOut | None
    attendance: AttendanceMarkOut | None
    disclaimer: str = DISCLAIMER


class LivenessFrameOut(BaseModel):
    session: LivenessSessionOut
    face_detected: bool
    message: str
    head_pose: HeadPoseOut | None
    ear: float | None
    image_width: int
    image_height: int
    # Puntos de la malla del rostro evaluado (si se pidieron), para dibujarlos.
    points: list[list[float]] = []
