# API REST

Referencia de la API de FaceTrack. El esquema completo (OpenAPI 3) está en [`openapi.json`](openapi.json); la documentación interactiva, en `/api/docs` (Swagger UI) y `/api/redoc`.

- La documentación interactiva está activa por defecto en desarrollo y **desactivada en producción** (describe toda la superficie de la API). Se controla con `API_DOCS=true|false`.
- `docs/openapi.json` se regenera con `python -m app.cli.export_openapi` (desde `backend/`). Un test falla si queda desactualizado respecto del código.

## Autenticación

`POST /api/auth/login` entrega una cookie de sesión `HttpOnly`; el navegador la envía sola en las demás llamadas. Todas las rutas la requieren salvo `GET /api/health` y el login. 🔒 = solo rol `ADMIN`. Detalles en [seguridad.md](seguridad.md).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/auth/login` | Inicia sesión (`username`, `password`) |
| GET | `/api/auth/me` | Usuario actual |
| POST | `/api/auth/logout` | Cierra y revoca la sesión |
| GET | `/api/health` | Estado del servicio y de la base (503 si la base no responde). Público |
| POST | `/api/personas` | 🔒 Crear persona (`first_name`/`nombre`, `last_name`/`apellido`, `email`) |
| GET | `/api/personas?active=` | Listar personas, con cantidad de muestras faciales |
| GET | `/api/personas/{id}` | Obtener persona |
| PUT | `/api/personas/{id}` | 🔒 Modificar (solo los campos enviados; `active=false` desactiva) |
| DELETE | `/api/personas/{id}` | 🔒 Eliminar (borra embeddings y asistencias; los eventos quedan sin nombre) |
| POST | `/api/personas/{id}/faces` | 🔒 Registrar muestra facial (`multipart/form-data`, campo `image`) |
| GET | `/api/personas/{id}/faces` | Listar muestras (solo metadatos) |
| DELETE | `/api/personas/{id}/faces/{face_id}` | 🔒 Eliminar una muestra |
| POST | `/api/reconocimiento/image` | Reconocer todos los rostros (`image`; `mode=recognition\|attendance`; `camera_id` opcional) |
| GET | `/api/historial` | Eventos de reconocimiento. Filtros: `person_id`, `recognized`, `camera_id`, `date` o `from`/`to`, `limit`, `offset` |
| GET | `/api/asistencia` | Registros ENTRY/EXIT. Filtros: `person_id`, `type`, `date` o `from`/`to`, `limit`, `offset` |
| GET | `/api/asistencia/export.csv` | Los mismos filtros, en CSV (hora local) |
| GET | `/api/estadisticas/resumen` | Dashboard de hoy: personas, reconocimientos, presentes, desconocidos, actividad reciente |
| GET | `/api/estadisticas?from=&to=` | Por día, por persona, desconocidos, entradas, salidas, confianza promedio (default: últimos 7 días) |
| POST | `/api/landmarks/image` | Malla facial, EAR y orientación de la cabeza de cada rostro (`include_points`) |
| POST | `/api/liveness/sessions` | Iniciar prueba de vida (`register_attendance`, `camera_id`); devuelve desafíos al azar |
| POST | `/api/liveness/sessions/{id}/frames` | Enviar un frame (`image`, `include_points`); devuelve estado, instrucción, pose y EAR |
| GET | `/api/liveness/sessions/{id}` | Estado y resultado (se conserva 5 minutos al terminar) |
| GET | `/api/configuracion` | Configuración en tiempo de ejecución y garantías de privacidad |
| PUT | `/api/configuracion` | 🔒 Reemplaza la configuración; se guarda y se aplica de inmediato |

Las fechas de los filtros (`date`, `from`, `to`) son días en hora local (`TIMEZONE`), ambos extremos incluidos. Las respuestas devuelven fechas en UTC (ISO 8601). Ninguna respuesta incluye embeddings ni hashes.

## Ejemplo

```bash
curl -X POST http://localhost:8080/api/reconocimiento/image \
  -b cookies.txt -H "Origin: http://localhost:8080" \
  -F "image=@grupo.jpg;type=image/jpeg" -F mode=attendance
```

```json
{
  "faces_detected": 2,
  "image_width": 1280,
  "image_height": 720,
  "events_recorded": 2,
  "results": [
    {"recognized": true, "person_id": "b24a…", "name": "Gianfranco Canciani", "confidence": 0.84, "distance": 0.20,
     "bbox": {"x": 120, "y": 80, "width": 220, "height": 220}, "error": null,
     "attendance": {"type": "ENTRY", "created_at": "2026-09-22T11:01:00Z"}},
    {"recognized": false, "person_id": null, "name": "Desconocido", "confidence": 0.0, "distance": 0.73,
     "bbox": {"x": 700, "y": 90, "width": 200, "height": 200}, "error": null, "attendance": null}
  ]
}
```

## Errores

Siempre `{"detail": "...", "code": "..."}`. Los errores 5xx agregan `request_id`: es el mismo valor de la cabecera `X-Request-ID` (presente en toda respuesta) y de las líneas de log de esa request.

| Status | `code` | Cuándo |
|---|---|---|
| 400 | `invalid_image` | Archivo vacío, corrupto o que no es una imagen |
| 401 | `unauthenticated` | Sin sesión, credenciales inválidas, sesión vencida o revocada |
| 403 | `forbidden` | El rol no alcanza |
| 403 | `origin_not_allowed` | Escritura desde un origen fuera de `CORS_ORIGINS` |
| 404 | `not_found` | Recurso inexistente |
| 409 | `duplicate` | Email o usuario ya registrado |
| 409 | `face_conflict` | La muestra no coincide con la persona o coincide con otra |
| 413 | `payload_too_large` | Supera `MAX_UPLOAD_MB` o 16 megapíxeles |
| 415 | `unsupported_media_type` | Tipo no permitido, o contenido distinto del tipo declarado |
| 422 | `validation_error` | Parámetros o cuerpo inválidos (`detail` lista los campos) |
| 422 | `face_not_found` / `multiple_faces` / `face_too_small` / `low_quality` | La foto de registro no sirve |
| 429 | `too_many_attempts` | Demasiados intentos de login fallidos (`Retry-After`) |
| 500 | `internal_error` | Error inesperado (el detalle solo va al log) |
| 503 | `database_error` | La base no responde (el detalle solo va al log) |

## Configuración en tiempo de ejecución

`PUT /api/configuracion` recibe la configuración completa (threshold, cooldown, intervalo de asistencia, FPS, máximo de rostros, id de cámara, guardar eventos). Se valida, se guarda en la tabla `app_settings` (con prioridad sobre las variables de entorno) y se aplica sin reiniciar. La respuesta incluye un bloque `privacy` de solo lectura: guardar imágenes o vídeo no es configurable porque el sistema no tiene código que lo haga.
