"""Punto de entrada de la API. El contrato vive en packages/api-spec/openapi.yaml."""

from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from scalar_fastapi import get_scalar_api_reference
from starlette.exceptions import HTTPException as StarletteHTTPException

from puente_api.config import get_settings
from puente_api.db.session import init_db
from puente_api.graph.guardrail_port import GuardrailBlocked
from puente_api.problems import ProblemError
from puente_api.routers import catalogs, matching, postings, reviews, traces, youth

API_PREFIX = "/api/v1"
PROBLEM_JSON = "application/problem+json"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Puente API", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _problem(status: int, detail: str | None = None, guardrail: str | None = None) -> JSONResponse:
    body: dict[str, str | int] = {"title": HTTPStatus(status).phrase, "status": status}
    if detail:
        body["detail"] = detail
    if guardrail:
        body["guardrail"] = guardrail
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


@app.exception_handler(StarletteHTTPException)
async def http_problem(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    guardrail = exc.guardrail if isinstance(exc, ProblemError) else None
    return _problem(exc.status_code, str(exc.detail) if exc.detail else None, guardrail)


@app.exception_handler(RequestValidationError)
async def validation_problem(_request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(
        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
    )
    return _problem(422, detail)


@app.exception_handler(GuardrailBlocked)
async def guardrail_problem(_request: Request, exc: GuardrailBlocked) -> JSONResponse:
    detail = f"Entrada bloqueada por seguridad ({exc.label}): {'; '.join(exc.reasons)}"
    return _problem(422, detail, exc.code)


api = APIRouter(prefix=API_PREFIX)


@api.get("/health", tags=["sistema"], operation_id="getHealth")
def health() -> dict[str, str]:
    return {"status": "ok"}


api.include_router(catalogs.router)
api.include_router(postings.router)
api.include_router(youth.router)
api.include_router(matching.youth_router)
api.include_router(matching.router)
api.include_router(reviews.router)
api.include_router(traces.router)
app.include_router(api)


@app.get("/docs", include_in_schema=False)
def scalar_docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
