# Desarrollo

Cómo correr FaceTrack sin Docker (salvo PostgreSQL), usar las herramientas de consola, correr los tests y leer los logs.

## Entorno local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cp .env.example .env
```

Completar en `.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # EMBEDDING_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # SECRET_KEY
```

Base de datos, modelos y primer usuario (desde `backend/`):

```bash
docker compose up -d postgres            # desde la raíz; 127.0.0.1:5433
alembic upgrade head
python -m app.cli.download_models        # una sola vez; nunca se descargan en ejecución
python -m app.cli.users create admin --role admin
```

> Usar `127.0.0.1` (no `localhost`) en `DATABASE_URL`: PostgreSQL solo escucha en IPv4 y, con `localhost`, cada conexión puede esperar 3 s intentando IPv6 primero.

API y frontend, en dos terminales:

```bash
cd backend && uvicorn app.main:app --reload        # http://localhost:8000, docs en /api/docs
cd frontend && npm install && npm run dev          # http://localhost:5173 (redirige /api a :8000)
```

Si el puerto 5173 está ocupado y Vite usa otro, agregarlo a `CORS_ORIGINS`: si no, el login desde ahí se rechaza con 403 (protección contra CSRF).

## Herramientas de consola

Desde `backend/`:

```bash
# Detección (ventana de OpenCV; q o Esc para salir)
python -m app.cli.detect [--camera 1 | --video clip.mp4 | --image foto.jpg]

# Personas y registro facial (solo guarda el embedding cifrado)
python -m app.cli.persons add --first-name Gianfranco --last-name Canciani --email gian@example.com
python -m app.cli.persons enroll <person_id> frontal.jpg izquierda.jpg derecha.jpg
python -m app.cli.persons list | deactivate <person_id> | delete <person_id>

# Reconocimiento con las personas de la base (eventos y, opcionalmente, asistencia)
python -m app.cli.recognize --db [--attendance] [--image grupo.jpg --headless]

# Reconocimiento sin base: personas desde carpetas (data/gallery/<Nombre>/*.jpg)
python -m app.cli.recognize --gallery ../data/gallery [--image grupo.jpg --headless]

# Usuarios del panel
python -m app.cli.users create <usuario> --role admin|operator

# Esquema OpenAPI → docs/openapi.json
python -m app.cli.export_openapi
```

Con `--image`, `recognize` imprime el mismo JSON que `POST /api/reconocimiento/image`. El script original sigue funcionando desde la raíz: `python Reconocimiento.py`.

## Base de datos

| Tabla | Contenido |
|---|---|
| `persons` | `id` (UUID), `first_name`, `last_name`, `email` (único, en minúsculas), `active`, `created_at`, `updated_at` |
| `face_embeddings` | `id`, `person_id`, `embedding` (**cifrado**), `dimension`, `model_version`, `created_at` |
| `recognition_events` | `id`, `person_id` (NULL = desconocido o persona eliminada), `recognized`, `confidence`, `distance`, `camera_id`, `created_at` |
| `attendance_records` | `id`, `person_id`, `type` (`ENTRY`/`EXIT`), `confidence`, `created_at` |
| `app_settings` | Configuración editable desde la API (JSON) |
| `users` | Usuarios del panel: `username`, hash Argon2id, `role`, `active`, `token_version`, `last_login_at` |
| `revoked_tokens` | Sesiones cerradas con logout, hasta su vencimiento |

Las fechas se guardan en UTC (`timestamptz`); "hoy" se calcula con `TIMEZONE`. Las migraciones están en `backend/alembic/versions` (`alembic upgrade head` / `alembic downgrade -1`); un test verifica que los modelos coincidan con ellas.

### Reglas de negocio

**Cooldown.** Una persona genera como máximo un evento cada `RECOGNITION_COOLDOWN_SECONDS`; los desconocidos, como máximo uno por cámara en esa ventana. Un filtro en memoria evita consultar la base en cada frame, y antes de guardar se verifica el último evento en la base: la ventana se respeta aunque el proceso se reinicie.

**Asistencia.** Para una persona reconocida:

| Último registro | Resultado |
|---|---|
| Ninguno | `ENTRY` |
| Hace menos de `ATTENDANCE_MIN_INTERVAL_MINUTES` | Nada (sigue frente a la cámara) |
| `EXIT` | `ENTRY` |
| `ENTRY` del mismo día | `EXIT` |
| `ENTRY` de un día anterior (olvidó marcar la salida) | `ENTRY` |

Así nunca hay `ENTRY, ENTRY` en una jornada ni un día que empiece con `EXIT`. Dos reconocimientos simultáneos de la misma persona (dos cámaras) se serializan con `SELECT … FOR UPDATE`. Las personas inactivas no registran asistencia.

## Tests y calidad

```bash
cd backend
FACETRACK_REQUIRE_DB=1 python -m pytest --cov=app    # 264 tests, 96 % de cobertura
ruff check .                                         # lint (estilo, bugs comunes, seguridad)

cd frontend
npm test                                             # Vitest + Testing Library
npm run build                                        # incluye el type-check estricto
```

- Los tests usan **modelos reales y fotos reales** (`backend/tests/fixtures`: retratos oficiales de dominio público y la imagen de ejemplo de OpenCV). El parpadeo se prueba "cerrando" los ojos de fotos reales, y la cámara, con vídeos generados.
- Los de base de datos usan `facetrack_test` (creada por el contenedor), aplican las migraciones desde cero y revierten cada test. Si PostgreSQL no responde, se saltean; con `FACETRACK_REQUIRE_DB=1` fallan (usarlo siempre, para que una base caída no pase desapercibida).
- Hay tests que protegen invariantes: toda ruta nueva exige sesión, `docs/openapi.json` está al día y el test de concurrencia de asistencia falla si se quita el bloqueo de fila.

## Logs

Cada línea lleva el id de la request (`X-Request-ID`), el mismo que devuelve la API y que los errores 5xx incluyen en el cuerpo:

```
2026-09-22 16:22:58 [INFO] facetrack.access [3f9a1c2b7d8e4f10]: POST /api/reconocimiento/image 200 41.3ms
2026-09-22 16:22:58 [INFO] app.services.event_service [3f9a1c2b7d8e4f10]: Person recognized: Barack Obama
```

- `LOG_FORMAT=json` emite una línea JSON por registro (`time`, `level`, `logger`, `request_id`, `message` y, en el log de acceso, `method`, `path`, `status`, `duration_ms`). Pensado para herramientas de logs en producción.
- Si llega un `X-Request-ID` de un proxy, se reutiliza solo si es seguro (letras, números, `.`, `_` o `-`, hasta 64 caracteres).
- El log de acceso omite el query string y los healthchecks.
- Nunca se loguean embeddings, imágenes, contraseñas, tokens ni la URL de la base.
