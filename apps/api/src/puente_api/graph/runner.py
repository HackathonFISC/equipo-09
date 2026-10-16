"""Ejecuta el grafo dentro de una transacción y garantiza la traza también ante errores."""

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from puente_api.graph.state import Event
from puente_api.graph.supervisor import ROUTES, build_graph
from puente_api.llm import LLMClient
from puente_api.tracing import record_trace


def run(
    session: Session,
    llm: LLMClient,
    event: Event,
    payload: dict[str, Any],
    thread_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Corre el grafo para `event` y hace commit. Devuelve (thread_id, resultado del agente).

    Si un nodo falla, revierte lo que hizo, registra la traza de error y relanza la excepción.
    """
    thread_id = thread_id or str(uuid4())
    config = {"configurable": {"session": session, "llm": llm, "thread_id": thread_id}}
    try:
        state = build_graph().invoke(
            {"thread_id": thread_id, "event": event, "payload": payload}, config=config
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        record_trace(
            session,
            thread_id,
            ROUTES.get(event, "supervisor"),
            input_summary=f"evento {event}",
            decision="error",
            reason=f"{type(exc).__name__}: {exc}",
        )
        session.commit()
        raise
    return thread_id, state.get("result", {})
