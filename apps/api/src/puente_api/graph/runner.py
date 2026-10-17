"""Ejecuta el grafo dentro de una transacción y garantiza la traza también ante errores.

Un grafo que llega a `interrupt` devuelve el control con lo hecho hasta ahí confirmado en la BD;
`resume` lo continúa más tarde (otra petición, otra sesión) desde el checkpoint.
"""

from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy.orm import Session

from puente_api.graph.state import Event
from puente_api.graph.supervisor import ROUTES, get_graph
from puente_api.llm import LLMClient
from puente_api.tracing import record_trace


def _config(session: Session, llm: LLMClient, thread_id: str) -> RunnableConfig:
    return {"configurable": {"session": session, "llm": llm, "thread_id": thread_id}}


def _fail(session: Session, thread_id: str, agent: str, summary: str, exc: Exception) -> None:
    session.rollback()
    record_trace(
        session,
        thread_id,
        agent,
        input_summary=summary,
        decision="error",
        reason=f"{type(exc).__name__}: {exc}",
    )
    session.commit()


def run(
    session: Session,
    llm: LLMClient,
    event: Event,
    payload: dict[str, Any],
    thread_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Corre el grafo para `event` y hace commit. Devuelve (thread_id, resultado acumulado).

    Si el grafo se pausa en una revisión humana, el resultado incluye `awaiting_review=True`.
    Si un nodo falla, revierte lo que hizo, registra la traza de error y relanza la excepción.
    """
    thread_id = thread_id or str(uuid4())
    try:
        state = get_graph().invoke(
            {"thread_id": thread_id, "event": event, "payload": payload},
            config=_config(session, llm, thread_id),
        )
        session.commit()
    except Exception as exc:
        _fail(session, thread_id, ROUTES.get(event, "supervisor"), f"evento {event}", exc)
        raise
    return thread_id, _result(state)


def is_paused(thread_id: str) -> bool:
    """¿El hilo está detenido en un `interrupt` y puede reanudarse?"""
    snapshot = get_graph().get_state({"configurable": {"thread_id": thread_id}})
    return bool(snapshot.next)


def resume(
    session: Session, llm: LLMClient, thread_id: str, decisions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Reanuda el hilo con las decisiones humanas (`review_id → decisión`) y hace commit."""
    try:
        state = get_graph().invoke(
            Command(resume=decisions), config=_config(session, llm, thread_id)
        )
        session.commit()
    except Exception as exc:
        _fail(session, thread_id, "orientador", "reanudación tras revisión humana", exc)
        raise
    return _result(state)


def _result(state: dict[str, Any]) -> dict[str, Any]:
    result = dict(state.get("result", {}))
    if state.get("__interrupt__"):
        result["awaiting_review"] = True
    return result
