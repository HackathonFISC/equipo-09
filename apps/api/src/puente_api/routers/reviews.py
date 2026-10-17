"""Bandeja del orientador (HITL): lista de revisiones y decisión que reanuda el grafo."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db
from puente_api.graph import runner
from puente_api.graph.hitl import REVIEW_STATUS, DecisionError, validate_decision
from puente_api.graph.nodes.orientador import apply_reviews
from puente_api.llm import LLMClient, get_llm
from puente_api.problems import ProblemError
from puente_api.routers.serializers import review_out

router = APIRouter(prefix="/reviews", tags=["orientador"])

DB = Annotated[Session, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm)]


@router.get(
    "",
    operation_id="listReviews",
    response_model=list[schemas.ReviewTask],
    response_model_exclude_none=True,
)
def list_reviews(
    db: DB,
    status: Annotated[schemas.ReviewStatus | None, Query()] = None,
    kind: Annotated[schemas.ReviewKind | None, Query()] = None,
) -> list[schemas.ReviewTask]:
    stmt = select(models.ReviewTask).order_by(models.ReviewTask.created_at, models.ReviewTask.id)
    if status:
        stmt = stmt.where(models.ReviewTask.status == status)
    if kind:
        stmt = stmt.where(models.ReviewTask.kind == kind)
    return [review_out(r) for r in db.scalars(stmt)]


@router.post(
    "/{review_id}/decision",
    operation_id="decideReview",
    status_code=202,
    response_model=schemas.Accepted,
    response_model_exclude_none=True,
)
def decide_review(
    review_id: str, body: schemas.ReviewDecision, db: DB, llm: LLM
) -> schemas.Accepted:
    """Registra la decisión humana y, cuando el hilo ya no tiene revisiones pendientes, lo reanuda.

    Un hilo puede tener varias revisiones (p. ej. alerta de sesgo + lista corta): el grafo sigue
    pausado hasta que se decidan todas, y entonces se reanuda con todas las decisiones a la vez.
    """
    review = db.get(models.ReviewTask, review_id)
    if review is None:
        raise ProblemError(404, f"Revisión {review_id} no existe")
    if review.status != "pendiente":
        raise ProblemError(409, f"La revisión ya fue resuelta ({review.status})")
    try:
        validate_decision(review, body.decision, body.comment, body.edits)
    except DecisionError as exc:
        raise ProblemError(422, str(exc)) from exc

    review.status = REVIEW_STATUS[body.decision]
    review.reviewer = body.reviewer
    review.comment = body.comment
    review.resolved_at = datetime.now(UTC)
    review.proposal = {
        **review.proposal,
        "decision": {
            "decision": body.decision,
            "reviewer": body.reviewer,
            "comment": body.comment,
            "edits": body.edits,
        },
    }
    db.flush()

    thread_id = review.graph_thread_id
    accepted = schemas.Accepted(thread_id=thread_id or review.id, resource_id=review.id)
    pending = db.scalar(
        select(func.count())
        .select_from(models.ReviewTask)
        .where(
            models.ReviewTask.graph_thread_id == thread_id, models.ReviewTask.status == "pendiente"
        )
    )
    if pending:
        db.commit()  # el hilo sigue esperando las demás revisiones
        return accepted

    batch = [review]
    if thread_id:
        batch = list(
            db.scalars(
                select(models.ReviewTask).where(
                    models.ReviewTask.graph_thread_id == thread_id,
                    models.ReviewTask.status != "pendiente",
                )
            )
        )
    decisions = {r.id: r.proposal["decision"] for r in batch if "decision" in r.proposal}
    if thread_id and runner.is_paused(thread_id):
        runner.resume(db, llm, thread_id, decisions)
    else:
        # Revisión creada sin checkpoint (datos previos al HITL): se aplican sus efectos sin grafo.
        apply_reviews(db, thread_id or f"review-{review.id}", batch, decisions)
        db.commit()
    return accepted
