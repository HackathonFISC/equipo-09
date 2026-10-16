"""Punto de entrada de la API. El contrato vive en packages/api-spec/openapi.yaml."""

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference

app = FastAPI(title="Puente API", version="0.1.0", docs_url=None, redoc_url=None)


@app.get("/health", tags=["sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/docs", include_in_schema=False)
def scalar_docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
