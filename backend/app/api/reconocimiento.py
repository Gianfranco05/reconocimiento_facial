"""Reconocimiento por imagen e historial de reconocimientos."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.deps import DateRange, DbSession, Engine, Pagination
from app.database.repositories.event_repository import EventRepository
from app.schemas.common import BoundingBoxOut, ErrorOut
from app.schemas.reconocimiento import (
    UNKNOWN_NAME,
    AttendanceMarkOut,
    EventOut,
    EventPage,
    FaceResultOut,
    RecognitionMode,
    RecognitionOut,
)
from app.utils.validators import read_upload_image

router = APIRouter(tags=["reconocimiento"])


@router.post(
    "/api/reconocimiento/image",
    response_model=RecognitionOut,
    responses={
        400: {"model": ErrorOut, "description": "Imagen inválida o corrupta"},
        413: {"model": ErrorOut, "description": "Archivo demasiado grande"},
        415: {"model": ErrorOut, "description": "Formato no soportado"},
    },
)
def recognize_image(
    session: DbSession,
    engine: Engine,
    image: Annotated[UploadFile, File(description="Imagen o frame de cámara (JPEG, PNG, WebP o BMP)")],
    mode: Annotated[RecognitionMode, Form()] = RecognitionMode.RECOGNITION,
    camera_id: Annotated[str | None, Form(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")] = None,
) -> RecognitionOut:
    """Detecta y reconoce todos los rostros de la imagen, cada uno de forma
    independiente. Registra eventos (con cooldown) y, en modo `attendance`,
    asistencia. La imagen no se guarda."""
    frame = read_upload_image(image, engine.settings.max_upload_bytes)
    outcome = engine.recognize(
        session, frame, camera_id=camera_id, register_attendance=mode is RecognitionMode.ATTENDANCE
    )
    session.commit()

    results = []
    for analysis in outcome.analyses:
        result = analysis.recognition
        recognized = bool(result and result.recognized)
        mark = outcome.attendance.get(result.person_id) if recognized else None
        results.append(
            FaceResultOut(
                recognized=recognized,
                person_id=uuid.UUID(result.person_id) if recognized else None,
                name=result.person_name if recognized else UNKNOWN_NAME,
                confidence=result.confidence if result else 0.0,
                distance=result.distance if result else None,
                bbox=BoundingBoxOut(**vars(analysis.face.bbox)),
                error=analysis.error,
                attendance=AttendanceMarkOut(type=mark.type, created_at=mark.created_at) if mark else None,
            )
        )
    height, width = frame.shape[:2]
    return RecognitionOut(
        faces_detected=len(results),
        image_width=width,
        image_height=height,
        events_recorded=len(outcome.events),
        results=results,
    )


@router.get("/api/historial", response_model=EventPage)
def history(
    session: DbSession,
    dates: DateRange,
    page: Annotated[Pagination, Depends()],
    person_id: Annotated[uuid.UUID | None, Query()] = None,
    recognized: Annotated[bool | None, Query(description="true = conocidos, false = desconocidos")] = None,
    camera_id: Annotated[str | None, Query(max_length=64)] = None,
) -> EventPage:
    start, end = dates
    items, total = EventRepository(session).search(
        person_id=person_id,
        recognized=recognized,
        camera_id=camera_id,
        start=start,
        end=end,
        limit=page.limit,
        offset=page.offset,
    )
    return EventPage(
        total=total,
        items=[
            EventOut(
                id=event.id,
                person_id=event.person_id,
                person_name=name or UNKNOWN_NAME,
                recognized=event.recognized,
                confidence=event.confidence,
                distance=event.distance,
                camera_id=event.camera_id,
                created_at=event.created_at,
            )
            for event, name in items
        ],
    )
