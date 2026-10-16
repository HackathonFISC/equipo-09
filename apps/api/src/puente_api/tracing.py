"""Registro de decisiones de agentes en `agent_trace` (trazabilidad propia, sin Langfuse aún).

Cada nodo del grafo escribe una fila: agente, paso (secuencia por hilo), entrada resumida,
decisión, razón y duración. `GET /traces/{threadId}` lee estas filas.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from puente_api.db import models

AGENTS = {
    "supervisor",
    "mercado",
    "perfil",
    "matching",
    "formacion",
    "postulacion",
    "entrevista",
    "auditor",
    "orientador",
}
_MAX_SUMMARY = 500


def summarize(text: str | None, limit: int = _MAX_SUMMARY) -> str | None:
    """Recorta y aplana el texto para que la traza no guarde documentos completos."""
    if text is None:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def next_step(session: Session, thread_id: str) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(models.AgentTrace)
        .where(models.AgentTrace.thread_id == thread_id)
    )
    return int(count or 0) + 1


def record_trace(
    session: Session,
    thread_id: str,
    agent: str,
    *,
    input_summary: str | None = None,
    decision: str | None = None,
    reason: str | None = None,
    duration_ms: int | None = None,
) -> models.AgentTrace:
    """Inserta una fila en `agent_trace` (sin commit: lo hace quien controla la transacción)."""
    if agent not in AGENTS:
        raise ValueError(f"Agente desconocido: {agent}")
    row = models.AgentTrace(
        thread_id=thread_id,
        agent=agent,
        step=str(next_step(session, thread_id)),
        input_summary=summarize(input_summary),
        decision=summarize(decision, 1000),
        reason=summarize(reason, 2000),
        duration_ms=duration_ms,
    )
    session.add(row)
    session.flush()
    return row


@dataclass
class TraceEntry:
    """Lo que un nodo rellena mientras trabaja; `traced` lo persiste al salir."""

    input_summary: str | None = None
    decision: str | None = None
    reason: str | None = None


@contextmanager
def traced(session: Session, thread_id: str, agent: str) -> Iterator[TraceEntry]:
    """Mide la duración del bloque y escribe la traza al terminar bien.

    Si el nodo falla, la transacción se revierte y quien ejecuta el grafo registra la traza
    de error aparte (ver `graph.runner.run`), para que no se pierda con el rollback.
    """
    entry = TraceEntry()
    start = time.perf_counter()
    yield entry
    record_trace(
        session,
        thread_id,
        agent,
        input_summary=entry.input_summary,
        decision=entry.decision or "sin decisión",
        reason=entry.reason,
        duration_ms=int((time.perf_counter() - start) * 1000),
    )
