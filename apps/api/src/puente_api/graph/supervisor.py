"""Grafo LangGraph: un supervisor determinista enruta cada evento al agente que le toca.

    START → supervisor ─┬─ posting.created ──→ mercado ──(oferta bloqueada)──┐
                        ├─ profile.cv / profile.interview → perfil → END     │
                        └─ match.requested → matching → auditor → postulacion┤
                                                                             ▼
                                              orientador (interrupt HITL) → END

El nodo `orientador` se pausa con `interrupt` hasta que el orientador decide cada `review_task`
(`POST /reviews/{id}/decision`); entonces el runner reanuda con `Command(resume=...)`. El estado
se guarda en el checkpointer, así que la pausa sobrevive entre peticiones HTTP.
"""

from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from puente_api.graph.checkpoint import get_checkpointer
from puente_api.graph.nodes.auditor import auditor_node
from puente_api.graph.nodes.matching import matching_node
from puente_api.graph.nodes.mercado import mercado_node
from puente_api.graph.nodes.orientador import orientador_node
from puente_api.graph.nodes.perfil import perfil_node
from puente_api.graph.nodes.postulacion import postulacion_node
from puente_api.graph.state import PuenteState, Route, deps
from puente_api.tracing import traced

ROUTES: dict[str, Route] = {
    "posting.created": "mercado",
    "profile.cv": "perfil",
    "profile.interview": "perfil",
    "match.requested": "matching",
}


def supervisor_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, _llm, thread_id = deps(config)
    event = state["event"]
    with traced(session, thread_id, "supervisor") as trace:
        trace.input_summary = f"evento {event}"
        route = ROUTES.get(event)
        if route is None:
            raise ValueError(f"Evento sin ruta: {event}")
        trace.decision = f"enruta a {route}"
        trace.reason = f"regla fija: {event} → {route}"
    return {"route": route}


def _next(state: PuenteState) -> Route:
    return state["route"]


def _review_or_end(state: PuenteState) -> str:
    """Solo se pausa si algún nodo dejó revisiones humanas pendientes."""
    return "orientador" if state.get("review_ids") else END


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    graph = StateGraph(PuenteState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("mercado", mercado_node)
    graph.add_node("perfil", perfil_node)
    graph.add_node("matching", matching_node)
    graph.add_node("auditor", auditor_node)
    graph.add_node("postulacion", postulacion_node)
    graph.add_node("orientador", orientador_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor", _next, {"mercado": "mercado", "perfil": "perfil", "matching": "matching"}
    )
    graph.add_conditional_edges("mercado", _review_or_end, ["orientador", END])
    graph.add_edge("perfil", END)
    graph.add_edge("matching", "auditor")
    graph.add_edge("auditor", "postulacion")
    graph.add_conditional_edges("postulacion", _review_or_end, ["orientador", END])
    graph.add_edge("orientador", END)
    return graph.compile(checkpointer=checkpointer)


@lru_cache
def get_graph() -> CompiledStateGraph:
    """Grafo compilado con el checkpointer del proceso (uno por aplicación)."""
    return build_graph(get_checkpointer())
