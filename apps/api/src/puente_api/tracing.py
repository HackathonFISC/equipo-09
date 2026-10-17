"""Registro de decisiones de agentes en `agent_trace` (trazabilidad propia, siempre activa).

Cada nodo del grafo escribe una fila: agente, paso (secuencia por hilo), entrada y salida
resumidas, herramienta usada, decisión, razón y duración. `GET /traces/{threadId}` lee estas
filas. Langfuse (opcional, ver `llm.observability`) es un complemento: si falta, nada cambia.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from puente_api.db import models
from puente_api.llm import observability

if TYPE_CHECKING:
    from puente_api.llm import LLMClient

TraceKind = Literal["paso", "pausa_hitl", "decision_humana", "guardrail", "error"]

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
    output_summary: str | None = None,
    tool: str | None = None,
    kind: TraceKind = "paso",
    decision: str | None = None,
    reason: str | None = None,
    duration_ms: int | None = None,
    langfuse_trace_id: str | None = None,
) -> models.AgentTrace:
    """Inserta una fila en `agent_trace` (sin commit: lo hace quien controla la transacción)."""
    if agent not in AGENTS:
        raise ValueError(f"Agente desconocido: {agent}")
    row = models.AgentTrace(
        thread_id=thread_id,
        agent=agent,
        step=str(next_step(session, thread_id)),
        input_summary=summarize(input_summary),
        output_summary=summarize(output_summary),
        tool=summarize(tool, 120),
        kind=kind,
        langfuse_trace_id=langfuse_trace_id,
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
    output_summary: str | None = None
    tool: str | None = None
    kind: TraceKind = "paso"
    decision: str | None = None
    reason: str | None = None


def _llm_tool(llm: "LLMClient", start: int) -> tuple[str | None, str | None]:
    """Resume las llamadas al LLM hechas en el bloque: (herramienta, aviso de degradación)."""
    calls = llm.call_log[start:]
    if not calls:
        return None, None
    real = [c for c in calls if not c.model.startswith("(")]
    models_used = sorted({c.model for c in real if c.ok}) or sorted({c.model for c in real})
    ms = sum(c.duration_ms for c in real)
    tokens = sum(c.tokens or 0 for c in real)
    label = f"llm: {', '.join(models_used) or 'sin respuesta'} ({len(real)} llamada(s), {ms} ms"
    label += f", {tokens} tokens)" if tokens else ")"
    degraded = any(c.model.startswith("(") for c in calls)
    retries = sum(1 for c in real if not c.ok)
    notes = []
    if degraded:
        notes.append("el LLM no dio una salida válida: se usó el valor por defecto seguro")
    elif retries:
        notes.append(f"{retries} llamada(s) fallida(s) antes de una respuesta válida")
    return label, "; ".join(notes) or None


@contextmanager
def traced(
    session: Session, thread_id: str, agent: str, llm: "LLMClient | None" = None
) -> Iterator[TraceEntry]:
    """Mide la duración del bloque y escribe la traza al terminar bien.

    Con `llm`, añade a la traza qué modelo se usó (y si hubo que caer al valor por defecto).
    Si el nodo falla, la transacción se revierte y quien ejecuta el grafo registra la traza
    de error aparte (ver `graph.runner.run`), para que no se pierda con el rollback.
    """
    entry = TraceEntry()
    start = time.perf_counter()
    mark = len(llm.call_log) if llm is not None else 0
    token = observability.trace_context.set(observability.TraceContext(thread_id, agent))
    try:
        yield entry
    finally:
        observability.trace_context.reset(token)
    llm_tool, warning = _llm_tool(llm, mark) if llm is not None else (None, None)
    reason = entry.reason
    if warning:
        reason = f"{reason} | {warning}" if reason else warning
    record_trace(
        session,
        thread_id,
        agent,
        input_summary=entry.input_summary,
        output_summary=entry.output_summary,
        tool=" + ".join(t for t in (entry.tool, llm_tool) if t) or None,
        kind=entry.kind,
        decision=entry.decision or "sin decisión",
        reason=reason,
        duration_ms=int((time.perf_counter() - start) * 1000),
        # Solo los nodos que llamaron al LLM tienen generaciones en Langfuse.
        langfuse_trace_id=thread_id if observability.is_enabled() and llm_tool else None,
    )
