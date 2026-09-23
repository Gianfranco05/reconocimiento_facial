#!/bin/sh
# Arranque del contenedor del backend: aplica las migraciones pendientes y
# después ejecuta el comando (uvicorn por defecto).
set -eu

echo "[entrypoint] Applying database migrations"
alembic upgrade head

exec "$@"
