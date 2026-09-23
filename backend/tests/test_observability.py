"""Id de request, log de acceso y formato JSON de logs."""

import json
import logging

from app.core.exceptions import FaceTrackError
from app.core.logging import JsonFormatter, RequestIdFilter, request_id_var
from tests.api_fixtures import jpeg, upload
from tests.conftest import load_fixture


def test_every_response_has_a_request_id(anon_client):
    first = anon_client.get("/api/health").headers["x-request-id"]
    second = anon_client.get("/api/health").headers["x-request-id"]
    assert first and second and first != second


def test_safe_incoming_request_id_is_reused(anon_client):
    response = anon_client.get("/api/health", headers={"X-Request-ID": "proxy-abc.123"})
    assert response.headers["x-request-id"] == "proxy-abc.123"


def test_unsafe_incoming_request_id_is_replaced(anon_client):
    response = anon_client.get("/api/health", headers={"X-Request-ID": "x\n[ERROR] inyectado"})
    assert response.headers["x-request-id"] != "x\n[ERROR] inyectado"
    assert "\n" not in response.headers["x-request-id"]


def test_server_errors_include_the_request_id(client, engine, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise FaceTrackError("fallo interno")

    monkeypatch.setattr(engine, "recognize", broken)
    with caplog.at_level(logging.ERROR):
        response = client.post("/api/reconocimiento/image", files=upload(jpeg(load_fixture("biden.jpg"))))
    body = response.json()
    assert response.status_code == 500
    assert body["request_id"] == response.headers["x-request-id"]
    # El log del error lleva el mismo id: se puede encontrar el detalle.
    assert any(getattr(r, "request_id", None) == body["request_id"] for r in caplog.records)


def test_client_errors_do_not_include_request_id(client):
    body = client.get("/api/personas/00000000-0000-0000-0000-000000000000").json()
    assert body["code"] == "not_found" and "request_id" not in body


def test_access_log_without_query_string(client, caplog):
    with caplog.at_level(logging.INFO, logger="facetrack.access"):
        client.get("/api/asistencia", params={"person_id": "00000000-0000-0000-0000-000000000000"})
        client.get("/api/health")
    lines = [r for r in caplog.records if r.name == "facetrack.access"]
    assert len(lines) == 1  # los healthchecks no se loguean
    assert lines[0].path == "/api/asistencia" and lines[0].status == 200
    assert "person_id" not in lines[0].getMessage()


def test_json_formatter():
    token = request_id_var.set("req-1")
    try:
        record = logging.LogRecord("facetrack.test", logging.INFO, __file__, 1, "Persona reconocida: %s", ("Ana",), None)
        RequestIdFilter().filter(record)
        record.status = 200
        entry = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert entry["message"] == "Persona reconocida: Ana"
    assert entry["request_id"] == "req-1" and entry["level"] == "INFO" and entry["status"] == 200


def test_outside_a_request_the_id_is_dash():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "m", (), None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"
