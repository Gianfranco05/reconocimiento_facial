"""Control de asistencia (ENTRY / EXIT).

Reglas, para una persona reconocida en el instante `now`:

1. Si su último registro fue hace menos de `min_interval`, no se registra nada
   (sigue frente a la cámara; evita ENTRY y EXIT a los pocos segundos).
2. Sin registros previos, o si el último fue EXIT            -> ENTRY.
3. Si el último fue ENTRY del mismo día local                  -> EXIT.
4. Si el último fue ENTRY de un día anterior (olvidó marcar la
   salida)                                                     -> ENTRY.
   Así nunca se producen ENTRY, ENTRY dentro de una misma jornada y un día
   nuevo nunca empieza con EXIT.

Las personas inactivas no registran asistencia. Para que dos reconocimientos
simultáneos de la misma persona no generen registros duplicados, se bloquea
la fila de la persona (SELECT ... FOR UPDATE) mientras se decide.
"""

import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.database.models import AttendanceRecord, AttendanceType, Person
from app.database.repositories.attendance_repository import AttendanceRepository
from app.utils.dates import local_date, utc_now

logger = logging.getLogger(__name__)


class AttendanceService:
    def __init__(self, min_interval: timedelta, tz: ZoneInfo) -> None:
        self.min_interval = min_interval
        self.tz = tz

    def register(
        self, session: Session, person_id: uuid.UUID, confidence: float, now: datetime | None = None
    ) -> AttendanceRecord | None:
        """Registra ENTRY o EXIT según las reglas. Devuelve None si no corresponde registrar."""
        now = now or utc_now()
        person = session.get(Person, person_id, with_for_update=True)
        if person is None:
            raise NotFoundError(f"No existe la persona {person_id}.")
        if not person.active:
            logger.info("Attendance ignored: inactive person")
            return None

        repository = AttendanceRepository(session)
        last = repository.last_for_person(person_id)
        next_type = self.next_type(last, now)
        if next_type is None:
            return None

        record = repository.add(person_id, next_type, confidence, created_at=now)
        logger.info("Attendance %s recorded: %s", next_type.value, person.full_name)
        return record

    def next_type(self, last: AttendanceRecord | None, now: datetime) -> AttendanceType | None:
        if last is None:
            return AttendanceType.ENTRY
        # `now < last` (reloj desfasado) también se trata como "demasiado pronto".
        if now - last.created_at < self.min_interval:
            return None
        if last.type is AttendanceType.EXIT:
            return AttendanceType.ENTRY
        if local_date(last.created_at, self.tz) != local_date(now, self.tz):
            return AttendanceType.ENTRY
        return AttendanceType.EXIT
