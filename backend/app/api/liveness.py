"""Landmarks faciales y prueba de vida (liveness)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.deps import DbSession, Engine
from app.core.exceptions import NotFoundError
from app.schemas.common import BoundingBoxOut, ErrorOut
from app.schemas.liveness import (
    ChallengeOut,
    EyesOut,
    FaceLandmarksOut,
    HeadPoseOut,
    LandmarksOut,
    LivenessCreate,
    LivenessFrameOut,
    LivenessPersonOut,
    LivenessSessionOut,
)
from app.schemas.reconocimiento import AttendanceMarkOut
from app.services.landmark_service import FaceLandmarks, HeadPose
from app.services.liveness_service import INSTRUCTIONS, LivenessSession
from app.utils.dates import utc_now
from app.utils.validators import read_upload_image

router = APIRouter(tags=["liveness"])

IMAGE_ERRORS = {
    400: {"model": ErrorOut, "description": "Imagen inválida o corrupta"},
    413: {"model": ErrorOut, "description": "Archivo demasiado grande"},
    415: {"model": ErrorOut, "description": "Formato no soportado"},
}


def _points(face: FaceLandmarks) -> list[list[float]]:
    return [[round(float(x), 1), round(float(y), 1)] for x, y in face.points]


def _pose(pose: HeadPose) -> HeadPoseOut:
    return HeadPoseOut(yaw=pose.yaw, pitch=pose.pitch, roll=pose.roll)


def _session_out(session: LivenessSession) -> LivenessSessionOut:
    person = session.person
    record = session.outcome.get("attendance")
    current = session.current_challenge
    return LivenessSessionOut(
        id=uuid.UUID(session.id),
        status=session.status,
        reason=session.reason,
        challenges=[
            ChallengeOut(type=c, instruction=INSTRUCTIONS[c], completed=i < session.completed)
            for i, c in enumerate(session.challenges)
        ],
        current_instruction=INSTRUCTIONS[current] if current and not session.finished else None,
        created_at=session.created_at,
        expires_at=session.expires_at,
        person=(
            LivenessPersonOut(
                person_id=uuid.UUID(person.person_id), name=person.person_name, confidence=person.confidence
            )
            if person
            else None
        ),
        attendance=AttendanceMarkOut(type=record.type, created_at=record.created_at) if record else None,
    )


def _get_session(engine, session_id: uuid.UUID) -> LivenessSession:
    session = engine.liveness.get(str(session_id), utc_now())
    if session is None:
        raise NotFoundError("La sesión de liveness no existe o venció.")
    return session


@router.post("/api/landmarks/image", response_model=LandmarksOut, responses=IMAGE_ERRORS)
def landmarks(
    engine: Engine,
    image: Annotated[UploadFile, File()],
    include_points: Annotated[bool, Form(description="Incluir los 478 puntos de cada rostro")] = True,
) -> LandmarksOut:
    """Malla facial (478 puntos), apertura de ojos (EAR) y orientación de la cabeza de cada rostro."""
    frame = read_upload_image(image, engine.settings.max_upload_bytes)
    faces = engine.detect_landmarks(frame)
    height, width = frame.shape[:2]
    return LandmarksOut(
        faces_detected=len(faces),
        image_width=width,
        image_height=height,
        faces=[
            FaceLandmarksOut(
                bbox=BoundingBoxOut(**vars(face.bbox)),
                head_pose=_pose(face.head_pose),
                eyes=EyesOut(**vars(face.eyes)),
                points=_points(face) if include_points else [],
            )
            for face in faces
        ],
    )


@router.post("/api/liveness/sessions", status_code=status.HTTP_201_CREATED, response_model=LivenessSessionOut)
def create_session(engine: Engine, body: LivenessCreate | None = None) -> LivenessSessionOut:
    """Inicia una prueba de vida con desafíos al azar. El cliente debe enviar
    frames a `/api/liveness/sessions/{id}/frames` hasta que el estado deje de
    ser IN_PROGRESS (o venza el tiempo)."""
    body = body or LivenessCreate()
    session = engine.liveness.create(utc_now(), camera_id=body.camera_id, register_attendance=body.register_attendance)
    return _session_out(session)


@router.get(
    "/api/liveness/sessions/{session_id}",
    response_model=LivenessSessionOut,
    responses={404: {"model": ErrorOut}},
)
def get_session(session_id: uuid.UUID, engine: Engine) -> LivenessSessionOut:
    return _session_out(_get_session(engine, session_id))


@router.post(
    "/api/liveness/sessions/{session_id}/frames",
    response_model=LivenessFrameOut,
    responses={404: {"model": ErrorOut}, **IMAGE_ERRORS},
)
def submit_frame(
    session_id: uuid.UUID,
    session: DbSession,
    engine: Engine,
    image: Annotated[UploadFile, File()],
    include_points: Annotated[bool, Form()] = False,
) -> LivenessFrameOut:
    liveness = _get_session(engine, session_id)
    frame = read_upload_image(image, engine.settings.max_upload_bytes)
    outcome = engine.liveness_frame(session, liveness, frame)
    session.commit()

    face = outcome.faces[0] if len(outcome.faces) == 1 else None
    height, width = frame.shape[:2]
    return LivenessFrameOut(
        session=_session_out(outcome.session),
        face_detected=outcome.feedback.face_detected,
        message=outcome.feedback.message,
        head_pose=_pose(outcome.feedback.head_pose) if outcome.feedback.head_pose else None,
        ear=outcome.feedback.ear,
        image_width=width,
        image_height=height,
        points=_points(face) if face is not None and include_points else [],
    )
