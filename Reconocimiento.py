"""Punto de entrada heredado del proyecto original.

La lógica se movió a `backend/app/`. Este archivo se conserva para que
`python Reconocimiento.py` siga funcionando igual que antes (webcam + detección).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.cli.detect import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
