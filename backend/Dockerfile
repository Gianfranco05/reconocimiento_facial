# Imagen del backend (API FastAPI + modelos de visión).
# Contexto de build: la raíz del repositorio (ver docker-compose.yml), para
# poder copiar la carpeta models/.

# --- Etapa 1: dependencias en un virtualenv ---------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# --- Etapa 2: modelos -------------------------------------------------------
# Se usan los de models/ si están; los que falten se descargan una sola vez al
# construir. En ejecución nunca se descarga nada.
FROM builder AS models

WORKDIR /app/backend
COPY backend/app ./app
COPY models /app/models
RUN python -m app.cli.download_models

# --- Etapa 3: imagen final --------------------------------------------------
FROM python:3.12-slim

# Librerías del sistema: OpenCV (libGL, glib) y MediaPipe Tasks (EGL/GLES,
# aunque corra en CPU las carga al iniciar el Face Landmarker).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios: la API no necesita root.
RUN useradd --system --uid 10001 --home /app facetrack

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODELS_DIR=/app/models \
    MPLCONFIGDIR=/tmp/matplotlib

COPY --from=builder /opt/venv /opt/venv
COPY --from=models /app/models /app/models
WORKDIR /app/backend
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh && chown -R root:root /app && chmod -R a-w /app

USER facetrack
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
# Un solo worker: la galería en memoria, el cooldown y las sesiones de
# liveness son por proceso (ver README, Limitaciones).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
