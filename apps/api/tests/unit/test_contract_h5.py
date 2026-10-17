"""H5: la API no expone operaciones fuera del contrato y se sabe cuáles faltan."""

from pathlib import Path

import yaml  # dependencia transitiva (LiteLLM/uvicorn); solo se usa en este test

from puente_api.main import app

SPEC = Path(__file__).resolve().parents[4] / "packages/api-spec/openapi.yaml"
# Operaciones del contrato que el MVP no implementa (alta de catálogos): congeladas en H5.
NOT_IMPLEMENTED = {"createCompany", "createTrainingCenter", "createCourse"}
METHODS = {"get", "post", "put", "patch", "delete"}


def _operations(paths: dict) -> set[str]:
    return {
        op["operationId"]
        for item in paths.values()
        for method, op in item.items()
        if method in METHODS and "operationId" in op
    }


def test_every_api_operation_is_in_the_contract_and_only_known_gaps_remain():
    contract = _operations(yaml.safe_load(SPEC.read_text(encoding="utf-8"))["paths"])
    implemented = _operations(app.openapi()["paths"])
    assert implemented <= contract, f"fuera del contrato: {implemented - contract}"
    assert contract - implemented == NOT_IMPLEMENTED
