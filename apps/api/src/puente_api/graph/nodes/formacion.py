"""Agente de Ruta de formación: el solver MIP elige los cursos; el LLM solo explica.

Entrada: el joven, las ofertas publicadas y el catálogo de cursos con sesiones. El código resuelve
(`solvers.training`), guarda el plan y verifica que la explicación del LLM no invente cifras; si
el LLM falla o contradice los hechos del solver se usa el texto determinista del solver.
"""

import re
from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from puente_api.db import models
from puente_api.graph.state import PuenteState, deps
from puente_api.llm.prompts import FORMACION_SYSTEM, FORMACION_USER
from puente_api.solvers.matching_adapter import load_matching_input
from puente_api.solvers.training import TrainingParams, TrainingPlanResult, solve_training
from puente_api.solvers.training_adapter import load_courses
from puente_api.tracing import summarize, traced

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
MAX_EXPLANATION = 900


class PlanExplanation(BaseModel):
    explanation: str = Field(min_length=1, max_length=MAX_EXPLANATION)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def verify_explanation(text: str, facts: str) -> bool:
    """La explicación no puede traer cifras que no estén en los hechos del solver."""
    return bool(text.strip()) and _numbers(text) <= _numbers(facts)


def formacion_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, llm, thread_id = deps(config)
    youth_id: str = state["payload"]["youth_id"]
    youth = session.get(models.Youth, youth_id)
    if youth is None:
        raise ValueError(f"Joven {youth_id} no existe")

    with traced(session, thread_id, "formacion", llm) as trace:
        trace.tool = "OR-Tools MIP (respaldo greedy)"
        inp = load_matching_input(session, youth_ids=[youth_id])
        courses = load_courses(session)
        params = TrainingParams()
        postings = sorted(inp.postings, key=lambda p: (-p.vacancies, p.id))[: params.max_postings]
        trace.input_summary = (
            f"joven {youth_id}: {len(postings)} ofertas publicadas, {len(courses)} cursos"
        )
        result: TrainingPlanResult = solve_training(
            inp.youths[0], postings, courses, inp.commute, params
        )

        facts = result.explanation_facts()
        explanation, source = facts, "texto determinista del solver"
        if result.items:
            draft = llm.structured(
                FORMACION_USER.format(facts=facts),
                PlanExplanation,
                system=FORMACION_SYSTEM,
                default=PlanExplanation(explanation=facts[:MAX_EXPLANATION]),
            ).explanation.strip()
            if verify_explanation(draft, facts):
                explanation, source = draft, "redactada por el LLM y verificada contra el solver"
            else:
                source = "el LLM trajo cifras ajenas al solver: se usó el texto del solver"

        plan = models.TrainingPlan(
            youth_id=youth_id,
            total_cost=result.total_cost,
            unlocked_postings=len(result.unlocked),
            explanation=explanation,
            status="propuesto",
            # Microsegundos: "la última ruta" no debe empatar con otra del mismo segundo.
            created_at=datetime.now(UTC),
            items=[
                models.TrainingPlanItem(session_id=it.session.id, order=it.order)
                for it in result.items
            ],
        )
        session.add(plan)
        session.flush()

        trace.output_summary = summarize(f"plan {plan.id}: {facts}")
        trace.decision = (
            f"ruta de {len(result.items)} curso(s), B/. {result.total_cost:.2f}, "
            f"desbloquea {len(result.unlocked)} oferta(s)"
            if result.items
            else "sin ruta factible o sin brechas que cerrar"
        )
        reasons = [
            f"solver {result.method} {result.status} en {result.solve_ms} ms",
            f"sesiones candidatas: {result.candidate_sessions}",
            f"explicación: {source}",
        ]
        if result.fallback_reason:
            reasons.append(f"respaldo: {result.fallback_reason}")
        if result.unreachable:
            reasons.append(f"brechas sin curso factible: {len(result.unreachable)}")
        trace.reason = " | ".join(reasons)

    return {"result": {"plan_id": plan.id, "courses": len(result.items)}}
