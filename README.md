# FaceTrack

Sistema de visión artificial para **reconocimiento facial, control de asistencia y estadísticas**, con procesamiento **local** y foco en privacidad.

Detecta y reconoce rostros en tiempo real desde la cámara del navegador, distingue personas conocidas de desconocidas con un umbral configurable, registra entradas y salidas, y puede exigir una prueba de vida básica antes de validar a alguien. Todo corre en tu máquina: las imágenes no salen de ella ni se guardan.

**Autor:** Gianfranco Canciani

---

- [Características](#características)
- [Arquitectura](#arquitectura)
- [Tecnologías](#tecnologías)
- [Instalación con Docker](#instalación-con-docker)
- [Variables de entorno](#variables-de-entorno)
- [Ejecución local](#ejecución-local)
- [API](#api)
- [Estructura](#estructura)
- [Capturas](#capturas)
- [Flujo de reconocimiento](#flujo-de-reconocimiento)
- [Privacidad](#privacidad)
- [Limitaciones](#limitaciones)
- [Roadmap](#roadmap)

Documentación detallada: [visión y liveness](docs/vision.md) · [API](docs/api.md) · [seguridad y privacidad](docs/seguridad.md) · [desarrollo](docs/desarrollo.md)

## Características

**Visión**
- Detección de varios rostros por imagen (OpenCV YuNet), cada uno reconocido de forma independiente.
- Embeddings faciales (OpenCV SFace, 128 dimensiones) y decisión conocido/desconocido con **umbral configurable**: el más parecido no se acepta si no pasa el umbral.
- Varias muestras por persona (frontal, perfiles, arriba, abajo).
- Landmarks faciales (malla de 478 puntos, MediaPipe), detección de parpadeo y orientación de la cabeza.
- **Liveness** por desafíos (parpadear + un giro de cabeza al azar): `LIVE` / `SUSPICIOUS` / `UNKNOWN`.

**Gestión**
- Personas: alta, edición, desactivación y baja.
- Registro facial guiado de 5 poses, con control de calidad (tamaño, nitidez, iluminación) y de coherencia (la foto debe ser de esa persona y no de otra registrada).
- Historial de reconocimientos, incluidos los desconocidos, con **cooldown** anti-duplicados.
- Asistencia `ENTRY`/`EXIT` sin entradas duplicadas, con filtros y exportación a CSV.
- Estadísticas por día y por persona, y un dashboard con los números del día.
- Configuración editable en caliente: umbral, cooldown, FPS, máximo de rostros, cámara.

**Plataforma**
- API REST (FastAPI) documentada con OpenAPI.
- Frontend React + TypeScript con CSS Modules (sin frameworks de CSS).
- PostgreSQL con migraciones (Alembic); embeddings **cifrados**.
- Login con roles administrador/operador: sesión JWT en cookie HttpOnly, revocable.
- Docker Compose: tres contenedores sin root, con healthchecks.
- Logs con id de request; 292 tests (264 del backend, con modelos y fotos reales, y 28 del frontend) y 96 % de cobertura en el backend.

## Arquitectura

```
                    ┌─────────────┐
                    │    React    │   navegador: cámara, dashboard, gestión
                    │ TypeScript  │
                    └──────┬──────┘
                           │  REST (/api) · cookie de sesión
                    ┌──────▼──────┐
                    │    nginx    │   archivos estáticos, proxy, cabeceras de seguridad
                    └──────┬──────┘
                    ┌──────▼──────┐
                    │   FastAPI   │   auth, validación, errores → services
                    └──────┬──────┘
             ┌─────────────┼──────────────┬───────────────┐
             ▼             ▼              ▼               ▼
        Recognition    Attendance     Statistics      Liveness
         Pipeline       Service        Service      (landmarks)
             │                                            │
             ▼                                            ▼
     OpenCV (YuNet + SFace)                     MediaPipe Face Landmarker
             │
             ▼
  PostgreSQL: personas · embeddings cifrados · eventos · asistencia · usuarios
```

Cada capa tiene una responsabilidad:

| Capa | Hace | No hace |
|---|---|---|
| `api/` | Rutas HTTP: validar la entrada, autorizar y traducir errores de dominio a códigos HTTP | Lógica de negocio |
| `services/` (visión) | Detectar, generar embeddings, comparar, landmarks | Acceder a la base |
| `services/` (negocio) | Eventos con cooldown, asistencia, estadísticas, liveness, registro facial | Conocer HTTP |
| `database/repositories/` | Consultas SQL (único lugar que habla con la base) | Decidir reglas |
| `schemas/` | Contratos de entrada y salida (nunca incluyen embeddings) | — |

El reconocimiento **no está acoplado a MediaPipe ni a un modelo concreto**: `FaceEmbedder` es una interfaz y cada embedding guarda su `model_version`. Detalles en [docs/vision.md](docs/vision.md).

## Tecnologías

| | |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn, Pydantic, SQLAlchemy 2, Alembic, psycopg 3 |
| **Visión** | OpenCV (YuNet, SFace), MediaPipe Tasks (Face Landmarker, BlazeFace), NumPy |
| **Seguridad** | Argon2id, PyJWT, cryptography (Fernet) |
| **Frontend** | React 19, TypeScript, Vite, React Router, CSS Modules, Lucide |
| **Infraestructura** | PostgreSQL 17, Docker Compose, nginx |
| **Calidad** | pytest, pytest-cov, Ruff, Vitest, Testing Library |

## Instalación con Docker

Requisitos: Docker con Compose.

```bash
cp .env.example .env
```

Completar los dos secretos del `.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # EMBEDDING_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # SECRET_KEY
```

Levantar y crear el primer administrador (la contraseña se pide sin mostrarla):

```bash
docker compose up -d --build
docker compose exec backend python -m app.cli.users create admin --role admin
```

Abrir **<http://localhost:8080>**.

```
navegador ──▶ frontend (nginx :8080) ──/api──▶ backend (:8000, red interna) ──▶ postgres (volumen postgres_data)
```

| Servicio | Qué hace |
|---|---|
| `postgres` | Datos en el volumen `postgres_data`: sobrevive a reinicios y a `docker compose down` (se borra con `down -v`). Solo escucha en `127.0.0.1:5433`, para desarrollo y tests |
| `backend` | Al arrancar aplica las migraciones y levanta la API. Los modelos van dentro de la imagen: nunca se descarga nada en ejecución. Corre sin root, con el código en solo lectura y **sin publicar puertos** |
| `frontend` | nginx sin root: sirve la aplicación, redirige `/api` al backend, agrega CSP y `Permissions-Policy: camera=(self)`, y corta uploads de más de 6 MB |

Los tres tienen healthcheck y arrancan en orden: postgres → backend → frontend. Comandos útiles: `docker compose logs -f backend`, `docker compose exec backend python -m app.cli.users list`, `docker compose down`.

> **HTTPS.** En Docker el backend corre en modo `production` y la cookie de sesión es `Secure`. Los navegadores la aceptan en `http://localhost`, pero para usar FaceTrack desde otra máquina hay que servirlo por HTTPS (un proxy con certificado delante del puerto 8080). Sin HTTPS el login fuera de `localhost` no funciona, y es correcto que así sea.

## Variables de entorno

Se leen de `.env` (ver [.env.example](.env.example)). Un valor fuera de rango hace fallar el arranque con un mensaje claro.

| Variable | Default | Descripción |
|---|---|---|
| **Secretos** | | |
| `EMBEDDING_ENCRYPTION_KEY` | — | **Obligatoria.** Clave Fernet que cifra los embeddings. Si se pierde, hay que re-registrar los rostros |
| `SECRET_KEY` | — | Firma de las sesiones. En producción: 32+ caracteres aleatorios (obligatorio) |
| **General** | | |
| `ENVIRONMENT` | `development` | `production` exige `SECRET_KEY` fuerte, usa cookie `Secure` y desactiva `/api/docs` |
| `TIMEZONE` | `America/Argentina/Buenos_Aires` | Zona horaria que define qué es "hoy" |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | Nivel de log; `json` emite una línea JSON por registro |
| `API_DOCS` | según `ENVIRONMENT` | Fuerza activar/desactivar la documentación interactiva |
| **Reconocimiento** | | |
| `FACE_RECOGNITION_THRESHOLD` | `0.63` | Distancia coseno máxima para aceptar una identidad (0–2); más bajo = más estricto |
| `MIN_FACE_SIZE` | `40` | Lado mínimo (px) de un rostro para intentar reconocerlo |
| `DETECTION_MIN_CONFIDENCE` / `MAX_FACES` | `0.6` / `10` | Score mínimo del detector y máximo de rostros por imagen |
| `FACE_DETECTOR_BACKEND` | `yunet` | `yunet` o `mediapipe` (el reconocimiento requiere `yunet`) |
| `RECOGNITION_COOLDOWN_SECONDS` | `10` | Ventana anti-duplicados de eventos |
| **Registro facial** | | |
| `ENROLLMENT_MIN_FACE_SIZE` | `80` | Lado mínimo del rostro (px) |
| `ENROLLMENT_MIN_DETECTION_SCORE` | `0.8` | Score mínimo del detector |
| `ENROLLMENT_MIN_SHARPNESS` | `100` | Nitidez mínima (varianza del Laplaciano) |
| `ENROLLMENT_MIN_BRIGHTNESS` / `_MAX_BRIGHTNESS` | `50` / `210` | Brillo medio aceptado (0–255) |
| **Asistencia y liveness** | | |
| `ATTENDANCE_MIN_INTERVAL_MINUTES` | `10` | Tiempo mínimo entre dos registros de una persona |
| `LIVENESS_TIMEOUT_SECONDS` | `20` | Tiempo máximo de la prueba de vida |
| `LIVENESS_YAW_DEGREES` / `LIVENESS_PITCH_DEGREES` | `20` / `12` | Giro mínimo pedido respecto de la pose inicial |
| `LIVENESS_BLINK_CLOSE_RATIO` / `_OPEN_RATIO` | `0.65` / `0.85` | Umbrales de parpadeo, relativos a la apertura normal de cada persona |
| **Cámara** | | |
| `CAMERA_INDEX` / `CAMERA_FPS` / `CAMERA_ID` | `0` / `15` / `default` | Webcam de las herramientas de consola, FPS e id guardado en cada evento |
| **API y seguridad** | | |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes del frontend (separados por coma; `*` no se admite). También se usan contra CSRF |
| `MAX_UPLOAD_MB` | `5` | Tamaño máximo de cada imagen |
| `ACCESS_TOKEN_MINUTES` | `480` | Duración de la sesión |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | `5` / `5` | Bloqueo tras intentos de login fallidos |
| **Base de datos** | | |
| `DATABASE_URL` / `TEST_DATABASE_URL` | `postgresql://postgres:postgres@127.0.0.1:5433/facetrack` (`…_test`) | Base principal y de tests. Usar `127.0.0.1`, no `localhost` (ver [desarrollo](docs/desarrollo.md)) |
| **Privacidad** | | |
| `SAVE_EVENTS` | `true` | Guardar el historial de reconocimientos |
| `SAVE_IMAGES` / `SAVE_VIDEO` | `false` | Solo aceptan `false`: FaceTrack no guarda imágenes ni vídeo |
| **Docker Compose** | | |
| `FRONTEND_PORT` / `PUBLIC_ORIGIN` | `8080` / `http://localhost:8080` | Puerto publicado y dirección con la que se abre la app |
| `DOCKER_ENVIRONMENT` | `production` | `ENVIRONMENT` del backend en Docker |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `postgres` / `postgres` | Credenciales de la base (cambiarlas fuera de una prueba local) |

## Ejecución local

Para desarrollar sin Docker (solo PostgreSQL en contenedor). Guía completa en [docs/desarrollo.md](docs/desarrollo.md).

```bash
python -m venv .venv && .venv/Scripts/activate           # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
docker compose up -d postgres
cd backend
alembic upgrade head
python -m app.cli.download_models
python -m app.cli.users create admin --role admin
uvicorn app.main:app --reload                             # API en :8000, documentación en /api/docs
```

```bash
cd frontend && npm install && npm run dev                 # http://localhost:5173
```

Tests: `FACETRACK_REQUIRE_DB=1 python -m pytest` (backend), `npm test` (frontend). Lint: `ruff check .`

## API

API REST bajo `/api`, con sesión por cookie. Resumen (referencia completa en [docs/api.md](docs/api.md) y [docs/openapi.json](docs/openapi.json)):

| Área | Rutas |
|---|---|
| Sesión | `POST /api/auth/login` · `GET /api/auth/me` · `POST /api/auth/logout` |
| Personas | `GET/POST /api/personas` · `GET/PUT/DELETE /api/personas/{id}` · `GET/POST /api/personas/{id}/faces` · `DELETE …/faces/{face_id}` |
| Reconocimiento | `POST /api/reconocimiento/image` (`mode=recognition\|attendance`) · `GET /api/historial` |
| Liveness | `POST /api/landmarks/image` · `POST /api/liveness/sessions` · `POST /api/liveness/sessions/{id}/frames` |
| Asistencia | `GET /api/asistencia` · `GET /api/asistencia/export.csv` |
| Estadísticas | `GET /api/estadisticas/resumen` · `GET /api/estadisticas?from=&to=` |
| Configuración | `GET/PUT /api/configuracion` |
| Estado | `GET /api/health` (público) |

```json
POST /api/reconocimiento/image
{
  "faces_detected": 2,
  "results": [
    {"recognized": true,  "name": "Gianfranco Canciani", "confidence": 0.84, "distance": 0.20, "person_id": "b24a…", "…": "…"},
    {"recognized": false, "name": "Desconocido",         "confidence": 0.0,  "distance": 0.73, "person_id": null,     "…": "…"}
  ]
}
```

Los errores son siempre `{"detail", "code"}`; los 5xx agregan un `request_id` para encontrar el detalle en los logs.

## Estructura

```
reconocimiento_facial/
├── backend/
│   ├── app/
│   │   ├── main.py            # App FastAPI (create_app): middlewares, routers, errores
│   │   ├── api/               # Rutas: auth, personas, reconocimiento, liveness, asistencia,
│   │   │                      #   estadísticas, configuración, health; dependencias, middlewares
│   │   ├── core/              # Configuración, logging, seguridad (cifrado, Argon2, JWT), excepciones
│   │   ├── database/          # Modelos SQLAlchemy y repositorios
│   │   ├── schemas/           # Contratos de la API (Pydantic)
│   │   ├── services/          # Visión (detectores, embeddings, reconocedor, landmarks) y negocio
│   │   │                      #   (eventos, asistencia, estadísticas, liveness, engine)
│   │   ├── utils/             # Imágenes, validación de uploads, fechas, dibujo
│   │   └── cli/               # detect, recognize, persons, users, download_models, export_openapi
│   ├── alembic/               # Migraciones
│   ├── tests/                 # pytest (fixtures: fotos reales de dominio público)
│   ├── Dockerfile, docker-entrypoint.sh, requirements*.txt, pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/             # Dashboard, Reconocimiento, Personas, Registro, Detalle, Asistencia,
│   │   │                      #   Historial, Estadísticas, Configuración, Login
│   │   ├── components/        # Layout, CameraView, FaceEnrollment, LivenessPanel, BarChart, ui/…
│   │   ├── auth/              # Contexto de sesión y rutas protegidas
│   │   ├── hooks/             # useCamera, useLiveness, useAsync, useFilters
│   │   ├── services/          # Cliente HTTP tipado
│   │   ├── types/, utils/, styles/
│   ├── Dockerfile, nginx.conf
├── models/                    # Modelos de visión (los .onnx/.task se descargan; no se versionan)
├── docs/                      # vision.md, api.md, seguridad.md, desarrollo.md, openapi.json
├── docker/postgres/init/      # Crea la base de tests
├── data/                      # Datos locales (no se versionan)
├── docker-compose.yml, .env.example
└── Reconocimiento.py          # Entrada del proyecto original (sigue funcionando)
```

## Capturas

Con datos **ficticios** de demostración (nombres inventados, una semana de actividad):

| Dashboard | Estadísticas |
|---|---|
| ![Dashboard: personas registradas, reconocimientos de hoy, presentes, desconocidos y actividad reciente](docs/capturas/dashboard.png) | ![Estadísticas: reconocimientos y asistencia por día y reconocimientos por persona](docs/capturas/estadisticas.png) |

| Personas | Detalle de persona |
|---|---|
| ![Personas: tabla con estado y cantidad de muestras faciales](docs/capturas/personas.png) | ![Detalle: datos, muestras faciales, asistencia y reconocimientos recientes](docs/capturas/persona-detalle.png) |

| Asistencia | Historial |
|---|---|
| ![Asistencia: filtros, entradas y salidas, exportación CSV](docs/capturas/asistencia.png) | ![Historial: reconocimientos conocidos y desconocidos con confianza, distancia y cámara](docs/capturas/historial.png) |

| Configuración | Login |
|---|---|
| ![Configuración: umbral, cooldown, cámara y garantías de privacidad](docs/capturas/configuracion.png) | ![Inicio de sesión](docs/capturas/login.png) |

> ⏳ **Pendiente: Reconocimiento y Liveness.** Estas pantallas muestran la cámara en vivo con el rostro de una persona, así que la captura debe hacerse con una webcam real y el consentimiento de quien aparece. Guardarlas como `docs/capturas/reconocimiento.png` y `docs/capturas/liveness.png`.

## Flujo de reconocimiento

```
                    Iniciar cámara (navegador)
                              │  frames a los FPS configurados, de a uno
                              ▼
                 Detectar rostros (YuNet) ── cada rostro por separado
                              │
                              ▼
            Alinear y extraer embedding (SFace, 128-D)
                              │
                              ▼
         Distancia a la muestra más cercana de cada persona
                   ┌──────────┴──────────┐
         distancia ≤ threshold      distancia > threshold
                   │                     │
             Persona conocida        Desconocido
                   │                     │
                   ▼                     ▼
      Confidence = 1 − d/(2·t)     evento "desconocido"
                   │                (uno por cámara y ventana)
                   ▼
      Liveness (opcional): parpadeo + giro al azar → LIVE
                   │
                   ▼
      Evento (con cooldown) → Asistencia ENTRY/EXIT → PostgreSQL → Dashboard
```

- **Threshold** (`0.63` por defecto) = similitud coseno 0,363 recomendada por OpenCV para SFace. Ajustarlo con la cámara real.
- **Confidence** es una heurística (1 con distancia 0; 0,5 justo en el umbral), **no una probabilidad**.
- Medido con las fotos de los tests: la misma persona en dos fotos distintas da distancia ≈ 0,19; personas distintas, entre 0,69 y 1,1.

Cómo se calibraron el registro facial, el parpadeo y la orientación de la cabeza: [docs/vision.md](docs/vision.md).

## Privacidad

- **Procesamiento local.** Nada se envía a servicios externos.
- **Sin imágenes ni vídeo guardados.** Las imágenes se procesan en memoria y se descartan; no es una opción configurable, porque no existe código que las guarde.
- **Embeddings cifrados** (AES-128 + HMAC) con una clave que vive solo en el entorno. Ninguna respuesta de la API los incluye.
- **Logs sin datos sensibles**: nunca embeddings, imágenes, contraseñas, tokens ni la URL de la base.
- La cámara se enciende solo a pedido y se apaga al salir de la página.
- Al eliminar una persona se borran sus embeddings y su asistencia; su historial queda sin nombre.

Detalle y medidas de seguridad: [docs/seguridad.md](docs/seguridad.md).

## Limitaciones

- **El liveness es básico.** Detecta fotos estáticas, pero un vídeo de la persona haciendo los gestos, o una máscara, pueden superarlo. No es seguridad biométrica de alta garantía. En los modos Reconocimiento y Asistencia no se exige liveness: una foto de una persona registrada sería reconocida.
- **Umbrales sin calibración propia.** El threshold de reconocimiento viene de la recomendación de OpenCV, y los de calidad y parpadeo se calibraron con pocas fotos. Conviene ajustarlos con la cámara y la iluminación reales.
- **Probado sin webcam real.** El parpadeo, la orientación de la cabeza y la cámara del navegador se probaron con fotos reales modificadas y una cámara simulada. Tampoco se probó en un teléfono real.
- **Un solo proceso.** La galería en memoria, el cooldown, las sesiones de liveness y el bloqueo por intentos de login viven en el proceso: la API debe correr con un worker. Si se registran rostros por consola con la API corriendo, hay que reiniciarla.
- **Detección a distancia.** Los landmarks (MediaPipe) solo ven rostros cercanos; una segunda persona lejos puede no detectarse durante el liveness.
- **Infraestructura.** Sin HTTPS incluido (hace falta un proxy con certificado para usarlo en red). La imagen del backend pesa ~1,6 GB por OpenCV y MediaPipe. No hay rotación de la clave de cifrado.
- **Gestión de usuarios solo por consola** (no hay pantalla de administración de usuarios).
- **Zona horaria.** Los filtros de fecha usan la zona del servidor y las horas se muestran con la del navegador; en uso local coinciden.

## Roadmap

- [x] **Sprint 1 — Refactor:** detector separado, estructura, configuración, logging.
- [x] **Sprint 2 — Recognition Engine:** embeddings, comparación, threshold, conocido/desconocido, múltiples rostros.
- [x] **Sprint 3 — PostgreSQL:** SQLAlchemy, Alembic, personas, embeddings cifrados, eventos, asistencia.
- [x] **Sprint 4 — FastAPI:** CRUD de personas, registro facial, reconocimiento, historial, asistencia, estadísticas.
- [x] **Sprint 5 — React:** dashboard, personas, registro, reconocimiento, asistencia, historial, estadísticas, configuración.
- [x] **Sprint 6 — Visión avanzada:** landmarks, parpadeo, orientación de la cabeza, liveness.
- [x] **Sprint 7 — Seguridad:** autenticación, roles, cookies, CORS, validación, límites de upload.
- [x] **Sprint 8 — Docker:** Dockerfiles, Compose, healthchecks.
- [x] **Sprint 9 — Calidad:** cobertura de tests, lint, manejo de errores, logs con id de request, documentación de la API, README.

**Próximos pasos posibles:** capturas de Reconocimiento y Liveness con una webcam real; calibrar los umbrales con la cámara de uso; HTTPS en Compose; pantalla de administración de usuarios; estado compartido (p. ej. Redis) para correr varios workers.

**Fuera de alcance de la V1:** emociones, edad, género, voz, múltiples cámaras simultáneas, notificaciones, app móvil, despliegue en la nube.
