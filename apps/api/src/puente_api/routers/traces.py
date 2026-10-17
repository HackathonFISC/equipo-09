"""Línea de tiempo de decisiones por agente (`agent_trace`) y listado de hilos recientes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db
from puente_api.problems import ProblemError

router = APIRouter(prefix="/traces", tags=["trazas"])

DB = Annotated[Session, Depends(get_db)]


def _step_no(row: models.AgentTrace, fallback: int) -> int:
    return int(row.step) if row.step.isdigit() else fallback


def _ordered(rows: list[models.AgentTrace]) -> list[models.AgentTrace]:
    # `created_at` tiene resolución de segundos en SQLite: el número de paso desempata.
    return sorted(rows, key=lambda r: _step_no(r, 0))


def _failed(row: models.AgentTrace) -> bool:
    blocked = row.kind == "guardrail" and (row.decision or "").startswith("bloqueado")
    return row.decision == "error" or row.kind == "error" or blocked


def _pending_reviews(db: Session, thread_ids: list[str]) -> dict[str, list[str]]:
    pending: dict[str, list[str]] = {}
    rows = db.execute(
        select(models.ReviewTask.graph_thread_id, models.ReviewTask.id)
        .where(
            models.ReviewTask.graph_thread_id.in_(thread_ids),
            models.ReviewTask.status == "pendiente",
        )
        .order_by(models.ReviewTask.created_at, models.ReviewTask.id)
    )
    for thread_id, review_id in rows:
        pending.setdefault(thread_id, []).append(review_id)
    return pending


def _status(last: models.AgentTrace, pending: list[str]) -> schemas.TraceStatus:
    if _failed(last):
        return "error"
    if pending:
        return "esperando_revision"
    # Los agentes corren de forma síncrona dentro de la petición.
    return "completado"


@router.get(
    "",
    operation_id="listTraces",
    response_model=list[schemas.TraceSummary],
    response_model_exclude_none=True,
)
def list_traces(
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[schemas.TraceStatus | None, Query()] = None,
) -> list[schemas.TraceSummary]:
    """Hilos recientes (el más nuevo primero) para navegar a su línea de tiempo."""
    latest = (
        select(models.AgentTrace.thread_id)
        .group_by(models.AgentTrace.thread_id)
        .order_by(func.max(models.AgentTrace.created_at).desc(), models.AgentTrace.thread_id)
        # Con filtro de estado se revisan más hilos para poder llenar `limit`.
        .limit(limit if status is None else 500)
    )
    thread_ids = list(db.scalars(latest))
    if not thread_ids:
        return []
    by_thread: dict[str, list[models.AgentTrace]] = {t: [] for t in thread_ids}
    for row in db.scalars(
        select(models.AgentTrace).where(models.AgentTrace.thread_id.in_(thread_ids))
    ):
        by_thread[row.thread_id].append(row)
    pending = _pending_reviews(db, thread_ids)

    out: list[schemas.TraceSummary] = []
    for thread_id in thread_ids:
        rows = _ordered(by_thread[thread_id])
        thread_status = _status(rows[-1], pending.get(thread_id, []))
        if status is not None and thread_status != status:
            continue
        agents: list[str] = []
        for r in rows:
            if r.agent not in agents:
                agents.append(r.agent)
        out.append(
            schemas.TraceSummary(
                thread_id=thread_id,
                status=thread_status,
                step_count=len(rows),
                agents=agents,
                last_decision=rows[-1].decision,
                started_at=min(r.created_at for r in rows),
                last_activity_at=max(r.created_at for r in rows),
            )
        )
        if len(out) == limit:
            break
    return out


@router.get(
    "/{thread_id}",
    operation_id="getTrace",
    response_model=schemas.Trace,
    response_model_exclude_none=True,
)
def get_trace(thread_id: str, db: DB) -> schemas.Trace:
    rows = _ordered(
        list(db.scalars(select(models.AgentTrace).where(models.AgentTrace.thread_id == thread_id)))
    )
    if not rows:
        raise ProblemError(404, f"Hilo {thread_id} sin trazas")
    pending = _pending_reviews(db, [thread_id]).get(thread_id, [])
    steps = [
        schemas.AgentTrace(
            agent=r.agent,
            step=_step_no(r, i + 1),
            kind=r.kind or "paso",
            input_summary=r.input_summary,
            output_summary=r.output_summary,
            tool=r.tool,
            decision=r.decision or "",
            reason=r.reason,
            duration_ms=r.duration_ms,
            langfuse_trace_id=r.langfuse_trace_id,
            created_at=r.created_at,
        )
        for i, r in enumerate(rows)
    ]
    return schemas.Trace(
        thread_id=thread_id,
        status=_status(rows[-1], pending),
        total_duration_ms=sum(r.duration_ms or 0 for r in rows),
        pending_review_ids=pending,
        steps=steps,
    )
