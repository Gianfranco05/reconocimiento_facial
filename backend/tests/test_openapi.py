"""Documentación de la API."""

import pytest
from fastapi.testclient import TestClient

from app.cli.export_openapi import OUTPUT, build_schema, render
from app.core.config import Settings
from app.main import create_app


def test_exported_schema_is_up_to_date():
    # Si falla: correr `python -m app.cli.export_openapi` y versionar docs/openapi.json.
    assert OUTPUT.is_file(), "falta docs/openapi.json"
    assert OUTPUT.read_text(encoding="utf-8") == render(build_schema())


def test_protected_routes_declare_the_session_cookie():
    schema = build_schema()
    assert schema["components"]["securitySchemes"]["APIKeyCookie"]["in"] == "cookie"
    public = {("/api/health", "get"), ("/api/auth/login", "post")}
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            secured = bool(operation.get("security"))
            assert secured != ((path, method) in public), f"{method.upper()} {path}"


def test_every_operation_is_tagged_and_documented_tags_exist():
    schema = build_schema()
    known = {tag["name"] for tag in schema["tags"]}
    for operations in schema["paths"].values():
        for operation in operations.values():
            assert operation.get("tags") and set(operation["tags"]) <= known


@pytest.mark.parametrize(
    "overrides,enabled",
    [({}, True), ({"environment": "production", "secret_key": "k" * 40}, False), ({"api_docs": False}, False)],
    ids=["dev-default", "production-default", "explicitly-off"],
)
def test_docs_toggle(overrides, enabled):
    app = create_app(Settings(_env_file=None, **overrides))
    client = TestClient(app)  # sin "with": no hace falta arrancar el motor para servir la documentación
    assert (client.get("/api/openapi.json").status_code == 200) is enabled
    assert (client.get("/api/docs").status_code == 200) is enabled
