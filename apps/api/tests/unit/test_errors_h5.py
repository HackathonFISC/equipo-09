"""H5: un error no controlado responde problem+json en español y con cabeceras CORS."""

import pytest
from fastapi.testclient import TestClient

from puente_api.main import app

ORIGIN = "http://localhost:3001"


@pytest.fixture
def boom_client():
    def boom():
        raise RuntimeError("fallo inesperado")

    app.add_api_route("/api/v1/__boom", boom, methods=["GET"])
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes.pop()  # quita la ruta temporal


def test_unhandled_error_is_problem_json_with_cors(boom_client):
    res = boom_client.get("/api/v1/__boom", headers={"Origin": ORIGIN})
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.headers["access-control-allow-origin"] == ORIGIN
    body = res.json()
    assert body["status"] == 500
    assert "error interno" in body["detail"]
    assert "fallo inesperado" not in body["detail"]  # el detalle técnico solo va al log


def test_business_errors_keep_their_status(client):
    res = client.get("/api/v1/traces/no-existe", headers={"Origin": ORIGIN})
    assert res.status_code == 404
    assert res.headers["access-control-allow-origin"] == ORIGIN
