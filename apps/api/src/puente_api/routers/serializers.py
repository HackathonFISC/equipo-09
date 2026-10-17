"""Conversión de filas de matching/postulación a los schemas del contrato."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from puente_api import schemas
from puente_api.db import models
from puente_api.schemas import normalize_slots


def skill_labels(db: Session) -> dict[str, str]:
    return {s.id: s.label_es for s in db.scalars(select(models.Skill))}


def match_out(row: models.MatchResult, labels: dict[str, str]) -> schemas.MatchResult:
    """`missingSkills` se guarda con ids de habilidad; el contrato lo expone con etiquetas."""
    breakdown = dict(row.score_breakdown)
    breakdown["missingSkills"] = [labels.get(s, s) for s in breakdown.get("missingSkills", [])]
    return schemas.MatchResult.model_validate(
        {
            "run_id": row.run_id,
            "youth_id": row.youth_id,
            "posting_id": row.posting_id,
            "score": row.score,
            "score_breakdown": breakdown,
            "constraints_checked": row.constraints_checked,
            "explanation": row.explanation,
            "status": row.status,
        }
    )


def matches_out(db: Session, rows: Iterable[models.MatchResult]) -> list[schemas.MatchResult]:
    labels = skill_labels(db)
    return [match_out(r, labels) for r in rows]


REVIEW_AGENT = {
    "bloqueo_oferta": "mercado",
    "lista_corta": "postulacion",
    "alerta_sesgo": "auditor",
}


def review_out(row: models.ReviewTask) -> schemas.ReviewTask:
    out = schemas.ReviewTask.model_validate(row)
    out.agent = REVIEW_AGENT.get(row.kind)
    return out


def training_plan_out(db: Session, plan: models.TrainingPlan) -> schemas.TrainingPlan:
    """Ruta guardada → contrato. El traslado se recalcula desde la matriz (no se persiste)."""
    youth = db.get(models.Youth, plan.youth_id)
    items: list[schemas.TrainingPlanItem] = []
    for item in plan.items:
        session = db.get(models.CourseSession, item.session_id)
        if session is None or youth is None:  # curso eliminado después de calcular la ruta
            continue
        course = db.get(models.Course, session.course_id)
        commute = db.get(models.CommuteMatrix, (youth.location_id, course.center.location_id))
        items.append(
            schemas.TrainingPlanItem(
                course_title=course.title,
                session=schemas.CourseSession(
                    id=session.id,
                    schedule=normalize_slots(session.schedule),
                    start_date=session.start_date,
                    seats_total=session.seats_total,
                    seats_taken=session.seats_taken,
                ),
                commute_min=commute.minutes if commute else None,
            )
        )
    return schemas.TrainingPlan(
        id=plan.id,
        youth_id=plan.youth_id,
        items=items,
        total_cost=float(plan.total_cost),
        unlocked_postings=plan.unlocked_postings,
        explanation=plan.explanation or "",
    )
