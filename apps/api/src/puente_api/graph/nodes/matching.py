"""Agente de Matching: ejecuta el solver CP-SAT y persiste `match_run` + `match_result[]`.

No hay LLM aquí: el código asigna y decide restricciones. La explicación inicial es una
plantilla determinista armada con el desglose; Postulación la verbaliza después con el LLM.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from puente_api.db import models
from puente_api.graph.state import PuenteState, deps
from puente_api.solvers.matching import MatchingParams, solve_matching
from puente_api.solvers.matching_adapter import (
    load_matching_input,
    run_params,
    to_match_result_rows,
)
from puente_api.tracing import traced

DEFAULT_TIME_LIMIT_S = 5.0


def describe_match(breakdown: dict[str, Any], skill_labels: dict[str, str]) -> str:
    """Plantilla determinista que solo repite el desglose del solver."""
    pct = lambda v: f"{round(float(v) * 100)}%"  # noqa: E731
    missing = [skill_labels.get(s, s) for s in breakdown.get("missingSkills", [])]
    text = (
        f"Cobertura de habilidades {pct(breakdown['skillCoverage'])}, "
        f"traslado {pct(breakdown['commute'])}, "
        f"costo {pct(breakdown['cost'])}, horario {pct(breakdown['schedule'])}, "
        f"salario {pct(breakdown['salary'])}."
    )
    if missing:
        text += f" Le faltan: {', '.join(missing)}."
    return text


def matching_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, _llm, thread_id = deps(config)
    payload = state["payload"]

    with traced(session, thread_id, "matching") as trace:
        trace.tool = "OR-Tools CP-SAT"
        inp = load_matching_input(
            session,
            youth_ids=payload.get("youth_ids") or None,
            posting_ids=payload.get("posting_ids") or None,
        )
        params = MatchingParams.relaxed(
            time_limit_s=payload.get("time_limit_seconds") or DEFAULT_TIME_LIMIT_S
        )
        trace.input_summary = f"{len(inp.youths)} jóvenes, {len(inp.postings)} ofertas publicadas"
        result = solve_matching(inp.youths, inp.postings, inp.commute, params)

        run = models.MatchRun(
            triggered_by=payload.get("triggered_by", "api"),
            graph_thread_id=thread_id,
            **run_params(result),
        )
        session.add(run)
        session.flush()

        labels = {s.id: s.label_es for s in session.scalars(select(models.Skill))}
        for row in to_match_result_rows(result, run.id):
            session.add(
                models.MatchResult(
                    **row, explanation=describe_match(row["score_breakdown"], labels)
                )
            )
        session.flush()

        trace.decision = (
            f"{len(result.assignments)} asignaciones, solver {result.status} "
            f"en {result.solve_ms} ms"
        )
        unfilled = sum(result.unfilled.values())
        trace.output_summary = f"corrida {run.id}: estado {result.status}"
        trace.reason = (
            f"pares elegibles: {result.eligible_pairs} | jóvenes sin asignar: "
            f"{len(result.unassigned)} | cupos vacíos: {unfilled} | restricciones: "
            "traslado, presupuesto, horario, salario y habilidades obligatorias (preset relajado)"
        )

    return {
        "run_id": run.id,
        "youth_ids": [y.id for y in inp.youths],
        "posting_ids": [p.id for p in inp.postings],
        "matching_result": result.model_dump(mode="json"),
        "result": {
            "run_id": run.id,
            "solver_status": result.status,
            "assigned": len(result.assignments),
        },
    }
