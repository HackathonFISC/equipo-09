"""Matching: corridas (solver → auditor → postulación) y matches por joven."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db
from puente_api.graph import runner
from puente_api.llm import LLMClient, get_llm
from puente_api.problems import ProblemError
from puente_api.routers.serializers import matches_out

router = APIRouter(prefix="/match-runs", tags=["matching"])
youth_router = APIRouter(prefix="/youth", tags=["jovenes"])

DB = Annotated[Session, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm)]


@router.post(
    "",
    operation_id="createMatchRun",
    status_code=202,
    response_model=schemas.Accepted,
    response_model_exclude_none=True,
)
def create_match_run(
    db: DB, llm: LLM, body: Annotated[schemas.MatchRunRequest | None, Body()] = None
) -> schemas.Accepted:
    """Matching (CP-SAT) → Auditor → Postulación. Se detiene en la revisión del orientador."""
    body = body or schemas.MatchRunRequest()
    payload = {
        "youth_ids": body.youth_ids,
        "posting_ids": body.posting_ids,
        "time_limit_seconds": body.time_limit_seconds,
        "triggered_by": "api",
    }
    try:
        thread_id, result = runner.run(db, llm, "match.requested", payload)
    except ValueError as exc:  # p. ej. tamaño fuera del límite del solver
        raise ProblemError(422, str(exc)) from exc
    return schemas.Accepted(thread_id=thread_id, resource_id=result.get("run_id"))


@router.get(
    "/{run_id}",
    operation_id="getMatchRun",
    response_model=schemas.MatchRun,
    response_model_exclude_none=True,
)
def get_match_run(run_id: str, db: DB) -> schemas.MatchRun:
    run = db.get(models.MatchRun, run_id)
    if run is None:
        raise ProblemError(404, f"Corrida {run_id} no existe")
    results = db.scalars(
        select(models.MatchResult)
        .where(models.MatchResult.run_id == run_id)
        .order_by(models.MatchResult.score.desc(), models.MatchResult.youth_id)
    )
    audit = db.scalars(
        select(models.AuditCheck)
        .where(models.AuditCheck.run_id == run_id)
        .order_by(models.AuditCheck.created_at, models.AuditCheck.variable)
    )
    return schemas.MatchRun(
        id=run.id,
        solver_status=run.solver_status or "TIMEOUT",
        solve_ms=run.solve_ms,
        thread_id=run.graph_thread_id,
        results=matches_out(db, results),
        audit=[schemas.AuditCheck.model_validate(a) for a in audit],
    )


@youth_router.get(
    "/{youth_id}/matches",
    operation_id="listYouthMatches",
    response_model=list[schemas.MatchResult],
    response_model_exclude_none=True,
)
def list_youth_matches(
    youth_id: str,
    db: DB,
    status: Annotated[schemas.MatchStatus | None, Query()] = None,
) -> list[schemas.MatchResult]:
    stmt = (
        select(models.MatchResult)
        .where(models.MatchResult.youth_id == youth_id)
        .order_by(models.MatchResult.score.desc(), models.MatchResult.posting_id)
    )
    if status:
        stmt = stmt.where(models.MatchResult.status == status)
    return matches_out(db, db.scalars(stmt))
