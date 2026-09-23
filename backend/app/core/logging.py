"""Configuración de logging.

Regla: nunca loguear embeddings, imágenes, contraseñas, tokens ni la URL de
la base. Los nombres de personas reconocidas sí aparecen (es el propósito del
historial), en nivel INFO.

Cada línea lleva el id de la request que la produjo (`request_id`), el mismo
que la API devuelve en la cabecera `X-Request-ID`: permite encontrar en el log
todo lo que pasó en una llamada concreta. Fuera de una request vale "-".

Formatos (LOG_FORMAT): `text` para leer en consola, `json` (una línea JSON por
registro) para herramientas de logs en producción.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s"


class RequestIdFilter(logging.Filter):
    """Agrega `request_id` a cada registro (lo toma del contexto de la request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        for key in ("method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)
