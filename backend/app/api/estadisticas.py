"""Estadísticas para el dashboard y la página Estadísticas."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Engine, query_error
from app.schemas.estadisticas import ActivityOut, DailyCountOut, PersonCountOut, StatisticsOut, SummaryOut
from app.schemas.reconocimiento import UNKNOWN_NAME
from app.services.statistics_service import StatisticsService
from app.utils.dates import local_date, utc_now

router = APIRouter(prefix="/api/estadisticas", tags=["estadisticas"])

MAX_RANGE_DAYS = 366


@router.get("/resumen", response_model=SummaryOut)
def summary(session: DbSession, engine: Engine) -> SummaryOut:
    """Números del dashboard para hoy (hora local) y la actividad reciente."""
    tz = engine.settings.tz
    data = StatisticsService(session, tz).summary(local_date(utc_now(), tz))
    return SummaryOut(
        date=data.date,
        persons_registered=data.persons_registered,
        recognitions_today=data.recognitions_today,
        people_present=data.people_present,
        unknown_today=data.unknown_today,
        recent_activity=[
            ActivityOut(
                created_at=a.created_at,
                person_id=a.person_id,
                person_name=a.person_name or UNKNOWN_NAME,
                recognized=a.recognized,
                confidence=a.confidence,
            )
            for a in data.recent_activity
        ],
    )


@router.get("", response_model=StatisticsOut)
def statistics(
    session: DbSession,
    engine: Engine,
    date_from: Annotated[date | None, Query(alias="from", description="Por defecto, hace 6 días")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Por defecto, hoy")] = None,
) -> StatisticsOut:
    tz = engine.settings.tz
    date_to = date_to or local_date(utc_now(), tz)
    date_from = date_from or date_to - timedelta(days=6)
    if date_from > date_to:
        raise query_error("from", "'from' es posterior a 'to'.")
    if (date_to - date_from).days >= MAX_RANGE_DAYS:
        raise query_error("from", f"El rango máximo es de {MAX_RANGE_DAYS} días.")

    data = StatisticsService(session, tz).statistics(date_from, date_to)
    return StatisticsOut(
        date_from=data.date_from,
        date_to=data.date_to,
        recognized_total=data.recognized_total,
        unknown_total=data.unknown_total,
        entries=data.entries,
        exits=data.exits,
        average_confidence=data.average_confidence,
        by_day=[DailyCountOut(**vars(d)) for d in data.by_day],
        by_person=[PersonCountOut(**vars(p)) for p in data.by_person],
    )
