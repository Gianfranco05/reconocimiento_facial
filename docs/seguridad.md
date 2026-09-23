# Seguridad y privacidad

## Usuarios y roles

Los usuarios del panel (distintos de las *personas* reconocidas) se crean por consola. La contraseña se pide sin mostrarla, o por `--password-stdin` para scripts; **nunca se acepta como argumento**, que quedaría en el historial de la terminal y en la lista de procesos.

```bash
python -m app.cli.users create admin --role admin          # desde backend/, o:
docker compose exec backend python -m app.cli.users create admin --role admin
python -m app.cli.users list | set-password <usuario> | deactivate <usuario> | activate <usuario>
```

| Rol | Puede |
|---|---|
| `ADMIN` | Todo: personas (crear, editar, eliminar), registro de rostros, configuración |
| `OPERATOR` | Operar la cámara (reconocimiento, asistencia, liveness) y consultar personas, asistencia, historial, estadísticas y configuración |

## Sesión

- `POST /api/auth/login` verifica la contraseña (hash **Argon2id**) y entrega un **JWT** firmado (HS256, con vencimiento `ACCESS_TOKEN_MINUTES`) en una cookie **`HttpOnly`** (JavaScript no puede leerla), **`SameSite=Strict`**, `Path=/api` y **`Secure`** con `ENVIRONMENT=production`.
- Cada request valida firma, emisor y vencimiento, y que el usuario siga activo. Solo se acepta HS256: un token con `alg: none` se rechaza.
- `POST /api/auth/logout` **revoca** el token (tabla `revoked_tokens`): aunque alguien lo haya copiado, deja de servir. Cambiar la contraseña o desactivar al usuario cierra todas sus sesiones (`token_version`).
- Todas las rutas exigen sesión salvo `GET /api/health` (solo informa `status` y `database`) y `POST /api/auth/login`. Un test recorre el esquema OpenAPI para garantizar que ninguna ruta nueva quede abierta.

## Protecciones

| Riesgo | Medida |
|---|---|
| Adivinar contraseñas | Tras `LOGIN_MAX_ATTEMPTS` fallos por usuario+IP, bloqueo de `LOGIN_LOCKOUT_MINUTES` (429 con `Retry-After`) |
| Descubrir qué usuarios existen | Mismo mensaje y mismo costo de verificación exista o no el usuario |
| Contraseñas débiles | Mínimo 10 caracteres, combinando letras con números o símbolos |
| CSRF | Cookie `SameSite=Strict`; además, las escrituras con un `Origin` fuera de `CORS_ORIGINS` se rechazan (403) |
| CORS | Solo los orígenes de `CORS_ORIGINS`; el comodín `*` se rechaza al arrancar |
| Uploads enormes | nginx corta a los 6 MB; el backend corta a `MAX_UPLOAD_MB` **antes** de procesar el multipart (por `Content-Length`, o contando el cuerpo si no lo trae) |
| Archivos maliciosos | MIME permitido + firma real del archivo coherente con el MIME + decodificación real + máximo 16 megapíxeles |
| Clave de firma débil | En producción, `SECRET_KEY` de 32+ caracteres es obligatoria. En desarrollo, si es débil, se usa una clave aleatoria por proceso (nunca `change_me`) |
| Filtrar datos | Nunca se devuelven embeddings ni hashes; errores internos con mensaje genérico; `Cache-Control: no-store` en la API |
| Clickjacking, sniffing, recursos externos | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; en nginx, CSP de solo recursos propios y `Permissions-Policy: camera=(self)` |
| Contenedores | Backend y nginx sin root; código de solo lectura; el backend no publica puertos y PostgreSQL solo escucha en `127.0.0.1` |

**Frontend.** Las rutas redirigen al login si no hay sesión y vuelven al destino original, solo si es una ruta interna (evita redirecciones abiertas). Si la API responde 401 (sesión vencida o cerrada), la interfaz vuelve al login. Un operador no ve las acciones de administración; la API las valida igual.

## Privacidad

- Todo el procesamiento es local; no se envían imágenes a servicios externos.
- **No se guardan imágenes ni vídeo**: las imágenes que llegan a la API se procesan en memoria y se descartan. `SAVE_IMAGES` y `SAVE_VIDEO` solo aceptan `false`: no hay código que las guarde, y ofrecer esas opciones sería engañoso.
- Los **embeddings** son datos biométricos sensibles: se guardan **cifrados** (Fernet: AES-128-CBC + HMAC-SHA256) con `EMBEDDING_ENCRYPTION_KEY`, que vive solo en el entorno. Sin la clave no se pueden leer, y una alteración se detecta.
- **Si se pierde `EMBEDDING_ENCRYPTION_KEY`, los embeddings guardados no se pueden recuperar** y hay que volver a registrar los rostros. Guardarla en un gestor de secretos. La rotación de claves no está implementada.
- Los logs no incluyen imágenes, embeddings, contraseñas, tokens ni la URL de la base. Sí incluyen el nombre de las personas reconocidas (es el propósito del historial). El log de acceso omite el query string, que puede contener ids de personas.
- En el navegador, la cámara se enciende solo al pulsar *Iniciar cámara* / *Abrir cámara* y se apaga al detenerla o salir de la página.
- Al eliminar una persona se borran sus embeddings y su asistencia. Sus eventos se conservan sin nombre (`person_id = NULL`) para que las estadísticas históricas sigan siendo correctas.
- `.env` y `data/` están excluidos de Git y de las imágenes Docker.
