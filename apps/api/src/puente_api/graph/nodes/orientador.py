"""Nodo del orientador: pausa con `interrupt` y aplica las decisiones humanas al reanudar.

Los nodos anteriores crean las `review_task` (con su propuesta) y dejan sus ids en el estado. Este
nodo se pausa una sola vez; `POST /reviews/{id}/decision` registra cada decisión y, cuando ya no
quedan revisiones pendientes del hilo, reanuda con `Command(resume={review_id: decisión})`.

LangGraph vuelve a ejecutar el nodo desde el inicio al reanudar, así que antes del `interrupt`
no hay efectos secundarios: todo se aplica después.
"""

from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from puente_api.db import models
from puente_api.graph.hitl import KIND_ORDER, REVIEW_STATUS, clean_posting_edits
from puente_api.graph.scheduling import assign_interview_slots, next_business_day
from puente_api.graph.state import PuenteState, deps
from puente_api.tracing import record_trace, summarize, traced

DecisionMap = dict[str, dict[str, Any]]


def _apply_bloqueo(
    session: Session, review: models.ReviewTask, d: dict[str, Any]
) -> tuple[str, str]:
    posting = session.get(models.JobPosting, review.subject_id)
    if posting is None:
        raise ValueError(f"Oferta {review.subject_id} no existe")
    decision = d["decision"]
    if decision == "aprobar":
        posting.status = "bloqueada"
        return "bloqueo confirmado", f"la oferta «{posting.title}» sigue bloqueada"
    if decision == "editar":
        edits = clean_posting_edits(d.get("edits"))
        for key, value in edits.items():
            setattr(posting, key, value)
        posting.status = "publicada"
        return "oferta editada y publicada", f"campos corregidos: {', '.join(sorted(edits))}"
    posting.status = "publicada"
    return "oferta liberada", f"el orientador descartó el bloqueo de «{posting.title}»"


def _apply_alerta(review: models.ReviewTask, d: dict[str, Any]) -> tuple[str, str, bool]:
    variable = review.proposal.get("variable")
    if d["decision"] == "aprobar":
        return (
            "hallazgo de sesgo aceptado",
            f"variable {variable}: lista corta retenida; hay que re-correr el matching",
            True,
        )
    return "alerta de sesgo descartada", f"variable {variable}: justificación del orientador", False


def _apply_shortlist(
    session: Session, review: models.ReviewTask, d: dict[str, Any], hold: bool
) -> tuple[str, str, dict[str, int]]:
    blocks = review.proposal.get("postings", [])
    all_ids = [c["matchResultId"] for b in blocks for c in b["candidates"]]
    counts = {"sent": 0, "removed": 0, "held": 0}
    if hold:
        counts["held"] = len(all_ids)
        return "lista corta retenida", "hay una alerta de sesgo aceptada sin resolver", counts

    edits = (d.get("edits") or {}) if d["decision"] == "editar" else {}
    removed = set(edits.get("remove") or [])
    order = edits.get("order") or []
    kept: list[str] = []
    for block in blocks:
        ids = [c["matchResultId"] for c in block["candidates"]]
        ordered = [i for i in order if i in ids] + [i for i in ids if i not in order]
        kept += [] if d["decision"] == "rechazar" else [i for i in ordered if i not in removed]
    dropped = [i for i in all_ids if i not in kept]

    results = {
        m.id: m
        for m in session.scalars(
            select(models.MatchResult).where(models.MatchResult.id.in_(all_ids))
        )
    }
    applications = {
        a.match_result_id: a
        for a in session.scalars(
            select(models.Application).where(models.Application.match_result_id.in_(all_ids))
        )
    }
    slots = assign_interview_slots(kept, next_business_day(datetime.now(UTC)))
    for mid in kept:
        results[mid].status = "aprobado"
        app = applications[mid]
        app.status = "enviada"
        # Se guarda en UTC como el resto de fechas (SQLite descarta la zona horaria).
        starts, ends = (t.astimezone(UTC) for t in slots[mid])
        session.add(models.InterviewSlot(application_id=app.id, starts_at=starts, ends_at=ends))
    for mid in dropped:
        results[mid].status = "rechazado"
        applications[mid].status = "descartada"
    session.flush()
    counts["sent"], counts["removed"] = len(kept), len(dropped)
    return (
        f"lista corta enviada: {len(kept)} candidato(s)",
        f"quitados por el orientador: {len(dropped)}; franjas de entrevista asignadas sin choques",
        counts,
    )


def apply_reviews(
    session: Session, thread_id: str, reviews: list[models.ReviewTask], decisions: DecisionMap
) -> dict[str, Any]:
    """Aplica las decisiones humanas y escribe una traza `orientador` por revisión."""
    result: dict[str, Any] = {"decisions": {}}
    bias_accepted = False
    for review in sorted(reviews, key=lambda r: (KIND_ORDER.get(r.kind, 9), r.created_at)):
        d = decisions[review.id]
        with traced(session, thread_id, "orientador") as trace:
            trace.kind = "decision_humana"
            trace.tool = "revisión humana (HITL)"
            trace.input_summary = f"{review.kind}: {review.explanation}"
            if review.kind == "bloqueo_oferta":
                outcome, detail = _apply_bloqueo(session, review, d)
                result["posting_status"] = session.get(models.JobPosting, review.subject_id).status
            elif review.kind == "alerta_sesgo":
                outcome, detail, accepted = _apply_alerta(review, d)
                bias_accepted = bias_accepted or accepted
                result["rerun_required"] = bias_accepted
            else:
                outcome, detail, counts = _apply_shortlist(session, review, d, bias_accepted)
                result["shortlist"] = counts
            who = d.get("reviewer") or "orientador"
            trace.decision = f"{d['decision']} por {who}: {outcome}"
            comment = f" | comentario: {d['comment']}" if d.get("comment") else ""
            trace.reason = detail + comment
            trace.output_summary = f"revisión {review.id}: {REVIEW_STATUS[d['decision']]}"
        result["decisions"][review.id] = d["decision"]
    return result


def _trace_pause(session: Session, thread_id: str, reviews: list[models.ReviewTask]) -> None:
    """Deja en la línea de tiempo que el grafo espera a un humano (una vez por conjunto).

    Al reanudar, LangGraph vuelve a ejecutar el nodo desde el principio: la marca de las ids de
    revisión evita duplicar la fila.
    """
    marker = "revisiones: " + ", ".join(sorted(r.id for r in reviews))
    already = session.scalar(
        select(models.AgentTrace.id).where(
            models.AgentTrace.thread_id == thread_id,
            models.AgentTrace.kind == "pausa_hitl",
            models.AgentTrace.reason == summarize(marker, 2000),
        )
    )
    if already:
        return
    kinds = ", ".join(sorted({r.kind for r in reviews}))
    record_trace(
        session,
        thread_id,
        "orientador",
        kind="pausa_hitl",
        tool="interrupt (LangGraph)",
        input_summary=f"{len(reviews)} revisión(es) pendiente(s): {kinds}",
        decision="pausa: esperando la decisión del orientador",
        reason=marker,
        duration_ms=0,
    )


def orientador_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, _llm, thread_id = deps(config)
    review_ids = state.get("review_ids", [])
    reviews = [session.get(models.ReviewTask, rid) for rid in review_ids]
    reviews = [r for r in reviews if r is not None]

    _trace_pause(session, thread_id, reviews)
    decisions: DecisionMap = interrupt(
        {
            "type": "revision_humana",
            "thread_id": thread_id,
            "reviews": [{"id": r.id, "kind": r.kind, "subject_id": r.subject_id} for r in reviews],
        }
    )
    outcome = apply_reviews(session, thread_id, reviews, decisions)
    return {"result": {**state.get("result", {}), **outcome}}
