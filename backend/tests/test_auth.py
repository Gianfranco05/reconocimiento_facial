"""Autenticación, autorización y protecciones HTTP."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import SESSION_COOKIE
from app.core.security import create_access_token
from app.database.repositories.user_repository import UserRepository
from tests.api_fixtures import ADMIN_PASSWORD, jpeg, login, upload
from tests.conftest import load_fixture

PUBLIC_ROUTES = {("GET", "/api/health"), ("POST", "/api/auth/login")}


def session_cookie(test_client: TestClient) -> str:
    return test_client.cookies[SESSION_COOKIE]


# --- Login ---


def test_login_sets_secure_session_cookie(anon_client):
    response = anon_client.post("/api/auth/login", json={"username": " ADMIN ", "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin" and body["role"] == "ADMIN"
    assert "password" not in str(body).lower()

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api" in cookie
    assert "Secure" not in cookie  # en desarrollo (HTTP local); en producción sí


def test_me_requires_session(anon_client):
    response = anon_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    login(anon_client, "admin", ADMIN_PASSWORD)
    assert anon_client.get("/api/auth/me").json()["username"] == "admin"


@pytest.mark.parametrize(
    "username,password",
    [("admin", "incorrecta-123"), ("no-existe", "cualquiera-123"), ("admin", "")],
    ids=["wrong-password", "unknown-user", "empty-password"],
)
def test_invalid_credentials_same_generic_answer(anon_client, username, password):
    response = anon_client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code in (401, 422)
    if response.status_code == 401:
        assert response.json()["detail"] == "Usuario o contraseña incorrectos."
    assert SESSION_COOKIE not in anon_client.cookies


def test_inactive_user_cannot_log_in(anon_client, db_session):
    UserRepository(db_session).set_active("admin", False)
    response = anon_client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 401


def test_repeated_failures_are_throttled(anon_client):
    for _ in range(5):
        assert anon_client.post("/api/auth/login", json={"username": "admin", "password": "mal-123456"}).status_code == 401
    blocked = anon_client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_attempts"
    assert int(blocked.headers["retry-after"]) > 0
    # Otro usuario no queda bloqueado.
    assert anon_client.post("/api/auth/login", json={"username": "operador", "password": "operador-clave-123"}).status_code == 200


# --- Sesión ---


def test_logout_revokes_the_token(client):
    token = session_cookie(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert SESSION_COOKIE not in client.cookies

    # Aunque alguien haya copiado el token, ya no sirve.
    client.cookies.set(SESSION_COOKIE, token, path="/api")
    response = client.get("/api/auth/me")
    assert response.status_code == 401 and "cerrada" in response.json()["detail"]


def test_password_change_closes_existing_sessions(client, db_session):
    UserRepository(db_session).set_password("admin", "nueva-clave-456")
    assert client.get("/api/auth/me").status_code == 401


def test_deactivated_user_loses_session(client, db_session):
    UserRepository(db_session).set_active("admin", False)
    assert client.get("/api/personas").status_code == 401


def test_expired_token_rejected(anon_client, engine, db_session):
    user = UserRepository(db_session).get_by_username("admin")
    token, _ = create_access_token(engine.settings, user.id, user.token_version, datetime.now(UTC) - timedelta(days=2))
    anon_client.cookies.set(SESSION_COOKIE, token, path="/api")
    assert anon_client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("attack", ["tampered", "alg-none", "other-key", "garbage"])
def test_forged_tokens_rejected(client, attack):
    token = session_cookie(client)
    header, payload, signature = token.split(".")
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["sub"] = str(uuid.uuid4())
    forged = {
        "tampered": f"{header}.{jwt.encode(claims, 'x' * 40, algorithm='HS256').split('.')[1]}.{signature}",
        "alg-none": jwt.encode(claims, None, algorithm="none"),
        "other-key": jwt.encode(claims, "otra-clave-" + "x" * 40, algorithm="HS256"),
        "garbage": "no.es.un-jwt",
    }[attack]
    client.cookies.set(SESSION_COOKIE, forged, path="/api")
    assert client.get("/api/auth/me").status_code == 401


# --- Autorización ---


def _concrete_path(path: str) -> str:
    for param in ("{person_id}", "{face_id}", "{session_id}"):
        path = path.replace(param, str(uuid.uuid4()))
    return path


def test_every_route_requires_a_session(app, anon_client):
    # Se recorren las rutas del esquema OpenAPI: incluye todo router registrado,
    # así una ruta nueva sin protección hace fallar este test.
    routes = [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if (method.upper(), path) not in PUBLIC_ROUTES
    ]
    assert len(routes) >= 20
    for method, path in routes:
        response = anon_client.request(method, _concrete_path(path))
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_operator_can_operate_but_not_administer(operator_client, client):
    person = client.post("/api/personas", json={"first_name": "Ana"}).json()

    assert operator_client.get("/api/personas").status_code == 200
    assert operator_client.get("/api/configuracion").status_code == 200
    assert operator_client.get("/api/asistencia").status_code == 200
    recognized = operator_client.post("/api/reconocimiento/image", files=upload(jpeg(load_fixture("biden.jpg"))))
    assert recognized.status_code == 200
    assert operator_client.post("/api/liveness/sessions").status_code == 201

    config = operator_client.get("/api/configuracion").json()
    denied = [
        operator_client.post("/api/personas", json={"first_name": "X"}),
        operator_client.put(f"/api/personas/{person['id']}", json={"first_name": "Y"}),
        operator_client.delete(f"/api/personas/{person['id']}"),
        operator_client.post(f"/api/personas/{person['id']}/faces", files=upload(jpeg(load_fixture("biden.jpg")))),
        operator_client.put("/api/configuracion", json={k: config[k] for k in config if k not in ("privacy", "model_version")}),
    ]
    for response in denied:
        assert response.status_code == 403, response.request.url
        assert response.json()["code"] == "forbidden"
    assert client.get(f"/api/personas/{person['id']}").json()["first_name"] == "Ana"


# --- Protecciones HTTP ---


def test_security_headers(anon_client):
    response = anon_client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_health_is_public_and_minimal(anon_client):
    assert anon_client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_foreign_origin_cannot_post(anon_client):
    creds = {"username": "admin", "password": ADMIN_PASSWORD}
    evil = anon_client.post("/api/auth/login", json=creds, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and evil.json()["code"] == "origin_not_allowed"
    ok = anon_client.post("/api/auth/login", json=creds, headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 200


def test_cors_only_for_configured_origins(anon_client):
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = anon_client.options("/api/auth/login", headers={"Origin": "http://localhost:5173", **preflight})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = anon_client.options("/api/auth/login", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in denied.headers


def test_oversized_body_rejected_before_processing(client):
    big = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)  # 2 MB con límite de 1 MB
    response = client.post("/api/reconocimiento/image", files=upload(big))
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_oversized_chunked_body_rejected(client):
    def chunks():
        for _ in range(40):
            yield b"x" * (64 * 1024)  # 2.5 MB sin Content-Length

    response = client.post(
        "/api/reconocimiento/image",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=abc"},
    )
    assert response.status_code == 413
