"""Middlewares de seguridad (ASGI puro, sin leer el cuerpo en memoria).

- BodySizeLimitMiddleware: corta con 413 antes de que el servidor procese el
  multipart. Sin él, FastAPI guardaría en disco un upload de cualquier tamaño
  antes de que el endpoint pueda rechazarlo.
- OriginCheckMiddleware: en métodos que modifican datos, si el navegador envía
  `Origin`, debe ser uno de CORS_ORIGINS (defensa extra contra CSRF, además de
  la cookie SameSite=Strict).
- SecurityHeadersMiddleware: cabeceras defensivas en todas las respuestas.
- RequestContextMiddleware: id por request (cabecera X-Request-ID, también en
  los logs) y una línea de log de acceso por request.
"""

import json
import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

access_logger = logging.getLogger("facetrack.access")
# Un id recibido del cliente o de un proxy se reutiliza solo si es "seguro"
# (evita inyectar texto arbitrario en los logs).
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TOO_LARGE_MESSAGE = "La solicitud supera el tamaño máximo permitido."


async def _send_error(send: Send, status: int, code: str, detail: str) -> None:
    body = json.dumps({"detail": detail, "code": code}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await _send_error(send, 413, "payload_too_large", TOO_LARGE_MESSAGE)
            return

        # Sin Content-Length (chunked) se cuenta mientras llega. Al pasarse,
        # se responde 413 y la app ve al cliente como desconectado (lanzar una
        # excepción no sirve: FastAPI la convertiría en un 400 genérico).
        received = 0
        response_started = False
        rejected = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    rejected = True
                    if not response_started:
                        await _send_error(send, 413, "payload_too_large", TOO_LARGE_MESSAGE)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if rejected:
                return  # ya se respondió 413
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = {o.rstrip("/") for o in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            origin = dict(scope["headers"]).get(b"origin")
            if origin is not None and origin.decode("latin-1").rstrip("/") not in self.allowed:
                await _send_error(send, 403, "origin_not_allowed", "Origen no permitido.")
                return
        await self.app(scope, receive, send)


SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-origin"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(SECURITY_HEADERS)
                if is_api:
                    # Respuestas con datos personales: que no queden en cachés intermedias.
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            if scope["path"] != "/api/health":  # los healthchecks llegan cada pocos segundos
                # Sin query string: puede contener ids de personas u otros filtros.
                access_logger.info(
                    "%s %s %s %.1fms",
                    scope["method"],
                    scope["path"],
                    status,
                    duration_ms,
                    extra={
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status,
                        "duration_ms": duration_ms,
                    },
                )
            request_id_var.reset(token)
