"""Conversión entre fechas locales (lo que ve el usuario) y rangos UTC (lo que
se guarda en la base)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[inicio, fin) del día local `day`, expresado en UTC."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def local_date(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()
