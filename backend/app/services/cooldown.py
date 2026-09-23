"""Ventana temporal anti-duplicados.

Evita registrar "Gian, Gian, Gian..." en cada frame: después de aceptar una
clave, las repeticiones dentro de la ventana se ignoran.

El estado vive en memoria del proceso (primer filtro, barato). La
persistencia entre procesos la garantiza `RecognitionEventService`
consultando los eventos guardados.
"""

import threading
from datetime import datetime, timedelta


class RecognitionCooldown:
    def __init__(self, seconds: int) -> None:
        if seconds < 0:
            raise ValueError("El cooldown no puede ser negativo.")
        self.window = timedelta(seconds=seconds)
        self._last_seen: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: datetime) -> bool:
        """True si `key` no se aceptó dentro de la ventana (y la marca como aceptada)."""
        with self._lock:
            last = self._last_seen.get(key)
            if last is not None and timedelta(0) <= now - last < self.window:
                return False
            self._last_seen[key] = now
            self._prune(now)
            return True

    def mark(self, key: str, when: datetime) -> None:
        """Registra que `key` se aceptó en `when` (por ejemplo, por otro proceso)."""
        with self._lock:
            self._last_seen[key] = when

    def reset(self) -> None:
        with self._lock:
            self._last_seen.clear()

    def _prune(self, now: datetime) -> None:
        # Evita que el diccionario crezca sin límite con claves viejas.
        if len(self._last_seen) > 1000:
            self._last_seen = {k: t for k, t in self._last_seen.items() if now - t < self.window}
