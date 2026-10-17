"""Agente Auditor: verificación contrafactual de la corrida y alertas de sesgo.

El cálculo vive en `solvers/auditor.py` (Sebastian) detrás del puerto `graph.audit_port`. Este
nodo prepara los atributos protegidos, persiste un `audit_check` por variable y, si alguna
verificación falla, abre una `review_task` de tipo `alerta_sesgo` para el orientador.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from puente_api.db import models
from puente_api.graph.audit_port import YouthAttributes, audit_matching, is_stub
from puente_api.graph.state import PuenteState, deps
from puente_api.solvers.matching import MatchingResult
from puente_api.solvers.matching_adapter import load_matching_input
from puente_api.tracing import traced


def _attributes(session, youth_ids: list[str]) -> dict[str, YouthAttributes]:
    youths = session.scalars(
        select(models.Youth)
        .where(models.Youth.id.in_(youth_ids))
        .options(selectinload(models.Youth.location))
    )
    return {
        y.id: YouthAttributes(
            display_name=y.display_name,
            gender=y.gender,
            corregimiento=y.location.corregimiento if y.location else None,
            location_id=y.location_id,
            birth_year=y.birth_year,
        )
        for y in youths
    }


def auditor_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, _llm, thread_id = deps(config)
    run_id = state["run_id"]
    youth_ids, posting_ids = state["youth_ids"], state["posting_ids"]

    with traced(session, thread_id, "auditor") as trace:
        trace.tool = "auditor contrafactual" + (" (STUB)" if is_stub() else "")
        trace.input_summary = (
            f"corrida {run_id}: {len(youth_ids)} jóvenes, {len(posting_ids)} ofertas"
        )
        result = MatchingResult.model_validate(state["matching_result"])
        inp = load_matching_input(session, youth_ids=youth_ids, posting_ids=posting_ids)
        findings = audit_matching(inp, result, _attributes(session, youth_ids))

        review_ids: list[str] = []
        failed = []
        for finding in findings:
            check = models.AuditCheck(
                run_id=run_id,
                kind="contrafactual",
                variable=finding.variable,
                parity=finding.parity,
                passed=finding.passed,
                findings=finding.findings,
            )
            session.add(check)
            session.flush()
            if finding.passed:
                continue
            failed.append(finding)
            parity = "n/d" if finding.parity is None else f"{finding.parity:.2f}"
            task = models.ReviewTask(
                kind="alerta_sesgo",
                subject_id=check.id,
                proposal={
                    "action": "rerun_sin_variable",
                    "runId": run_id,
                    "variable": finding.variable,
                    "parity": finding.parity,
                    "findings": finding.findings,
                },
                explanation=(
                    f"El auditor contrafactual detectó posible sesgo por {finding.variable} "
                    f"(paridad {parity}): " + "; ".join(finding.findings)
                ),
                graph_thread_id=thread_id,
            )
            session.add(task)
            session.flush()
            review_ids.append(task.id)

        trace.decision = (
            f"{len(findings) - len(failed)} de {len(findings)} verificaciones aprobadas"
            + (f"; {len(failed)} alerta(s) de sesgo a revisión" if failed else "")
        )
        reasons = [
            f"{f.variable}: paridad {'n/d' if f.parity is None else f'{f.parity:.2f}'} "
            f"({'aprobada' if f.passed else 'ALERTA'})"
            for f in findings
        ]
        if is_stub():
            reasons.append("auditor STUB: sin verificación real")
        trace.reason = " | ".join(reasons)
        trace.output_summary = f"{len(findings)} verificación(es), {len(failed)} alerta(s)"

    return {"review_ids": review_ids}
