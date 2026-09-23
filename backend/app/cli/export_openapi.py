"""Exporta el esquema OpenAPI de la API a docs/openapi.json.

Uso (desde backend/):
    python -m app.cli.export_openapi

Sirve para consultar la API sin levantarla (o con la documentación
interactiva desactivada, como en producción) y para generar clientes. Un
test verifica que el archivo esté al día con el código.
"""

import json
import sys
from pathlib import Path

from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app

OUTPUT = PROJECT_ROOT / "docs" / "openapi.json"


def build_schema() -> dict:
    # Configuración fija: el esquema no depende del .env de quien lo genera.
    settings = Settings(_env_file=None, api_docs=True)
    return create_app(settings).openapi()


def render(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(output: Path = OUTPUT) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(build_schema()), encoding="utf-8")
    print(f"Esquema OpenAPI escrito en {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
