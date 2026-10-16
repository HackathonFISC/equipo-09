"""Grafo LangGraph: un supervisor determinista enruta cada evento al agente que le toca.

    START → supervisor ─┬─ posting.created ─────────────→ mercado → END
                        └─ profile.cv / profile.interview → perfil  → END

H3 añade Matching → Auditor → Postulación, el checkpointer y los `interrupt` HITL.
"""

from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from puente_api.graph.nodes.mercado import mercado_node
from puente_api.graph.nodes.perfil import perfil_node
from puente_api.graph.state import PuenteState, Route, deps
from puente_api.tracing import traced

ROUTES: dict[str, Route] = {
    "posting.created": "mercado",
    "profile.cv": "perfil",
    "profile.interview": "perfil",
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


@lru_cache
def build_graph() -> CompiledStateGraph:
    graph = StateGraph(PuenteState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("mercado", mercado_node)
    graph.add_node("perfil", perfil_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _next, {"mercado": "mercado", "perfil": "perfil"})
    graph.add_edge("mercado", END)
    graph.add_edge("perfil", END)
    return graph.compile()
