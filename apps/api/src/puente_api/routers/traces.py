"""Línea de tiempo de decisiones por agente (`agent_trace`)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db
from puente_api.problems import ProblemError

router = APIRouter(prefix="/traces", tags=["trazas"])

DB = Annotated[Session, Depends(get_db)]


@router.get(
    "/{thread_id}",
    operation_id="getTrace",
    response_model=schemas.Trace,
    response_model_exclude_none=True,
)
def get_trace(thread_id: str, db: DB) -> schemas.Trace:
    rows = list(
        db.scalars(
            select(models.AgentTrace)
            .where(models.AgentTrace.thread_id == thread_id)
            .order_by(models.AgentTrace.created_at)
        )
    )
    if not rows:
        raise ProblemError(404, f"Hilo {thread_id} sin trazas")
    # `created_at` tiene resolución de segundos en SQLite: el número de paso desempata.
    rows.sort(key=lambda r: int(r.step) if r.step.isdigit() else 0)
    pending_review = db.scalar(
        select(models.ReviewTask.id).where(
            models.ReviewTask.graph_thread_id == thread_id,
            models.ReviewTask.status == "pendiente",
        )
    )
    if rows[-1].decision == "error":
        status = "error"
    elif pending_review:
        status = "esperando_revision"
    else:
        # Los agentes de H2 corren de forma síncrona dentro de la petición.
        status = "completado"
    steps = [
        schemas.AgentTrace(
            agent=r.agent,
            step=int(r.step) if r.step.isdigit() else i + 1,
            input_summary=r.input_summary,
            decision=r.decision or "",
            reason=r.reason,
            duration_ms=r.duration_ms,
            langfuse_trace_id=r.langfuse_trace_id,
            created_at=r.created_at,
        )
        for i, r in enumerate(rows)
    ]
    return schemas.Trace(thread_id=thread_id, status=status, steps=steps)
