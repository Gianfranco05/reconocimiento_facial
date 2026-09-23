"""Consulta y exportación de asistencia."""

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import DateRange, DbSession, Engine, Pagination
from app.database.models import AttendanceType
from app.database.repositories.attendance_repository import AttendanceRepository
from app.schemas.asistencia import AttendanceOut, AttendancePage

router = APIRouter(prefix="/api/asistencia", tags=["asistencia"])

TYPE_LABELS = {AttendanceType.ENTRY: "Entrada", AttendanceType.EXIT: "Salida"}


@router.get("", response_model=AttendancePage)
def list_attendance(
    session: DbSession,
    dates: DateRange,
    page: Annotated[Pagination, Depends()],
    person_id: Annotated[uuid.UUID | None, Query()] = None,
    type_: Annotated[AttendanceType | None, Query(alias="type")] = None,
) -> AttendancePage:
    """Filtros: `person_id`, `type` (ENTRY/EXIT), y `date` o `from`/`to` (días locales, incluidos)."""
    start, end = dates
    items, total = AttendanceRepository(session).search(
        person_id=person_id, type_=type_, start=start, end=end, limit=page.limit, offset=page.offset
    )
    return AttendancePage(
        total=total,
        items=[
            AttendanceOut(
                id=record.id,
                person_id=record.person_id,
                person_name=name,
                type=record.type,
                confidence=record.confidence,
                created_at=record.created_at,
            )
            for record, name in items
        ],
    )


@router.get("/export.csv", response_class=StreamingResponse)
def export_attendance_csv(
    session: DbSession,
    engine: Engine,
    dates: DateRange,
    person_id: Annotated[uuid.UUID | None, Query()] = None,
    type_: Annotated[AttendanceType | None, Query(alias="type")] = None,
) -> StreamingResponse:
    """Mismos filtros que el listado, sin paginar. Fechas y horas en hora local."""
    start, end = dates
    items, _ = AttendanceRepository(session).search(
        person_id=person_id, type_=type_, start=start, end=end, limit=None
    )
    tz = engine.settings.tz

    buffer = io.StringIO()
    buffer.write("﻿")  # BOM: Excel abre bien los acentos
    writer = csv.writer(buffer)
    writer.writerow(["Persona", "Fecha", "Hora", "Tipo", "Confianza"])
    for record, name in items:
        local = record.created_at.astimezone(tz)
        writer.writerow(
            [
                name,
                local.strftime("%d/%m/%Y"),
                local.strftime("%H:%M"),
                TYPE_LABELS[record.type],
                f"{record.confidence:.2f}",
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="asistencia.csv"'},
    )
