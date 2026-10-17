"""Reglas del humano en el ciclo: qué decisiones admite cada tipo de revisión.

Compartido por el endpoint `POST /reviews/{id}/decision` (valida antes de escribir nada) y por el
nodo `orientador` (aplica los efectos tras el `interrupt`).
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from puente_api.db import models

Decision = Literal["aprobar", "editar", "rechazar"]
REVIEW_STATUS = {"aprobar": "aprobada", "editar": "editada", "rechazar": "rechazada"}
AGENT_BY_KIND = {
    "bloqueo_oferta": "mercado",
    "lista_corta": "postulacion",
    "alerta_sesgo": "auditor",
}
# Orden de aplicación: primero el sesgo (puede retener la lista corta), al final la lista.
KIND_ORDER = {"alerta_sesgo": 0, "bloqueo_oferta": 1, "lista_corta": 2}
POSTING_EDITABLE = {"title", "salary_min", "salary_max", "vacancies"}
_CAMEL = {"salaryMin": "salary_min", "salaryMax": "salary_max"}


class DecisionError(ValueError):
    """La decisión no es válida para esta revisión (se responde 422)."""


def clean_posting_edits(edits: dict[str, Any] | None) -> dict[str, Any]:
    """Filtra y tipa las ediciones permitidas de una oferta bloqueada."""
    clean: dict[str, Any] = {}
    for key, value in (edits or {}).items():
        key = _CAMEL.get(key, key)
        if key not in POSTING_EDITABLE or value is None:
            continue
        try:
            if key == "title":
                text = str(value).strip()
                if text:
                    clean[key] = text[:200]
            elif key == "vacancies":
                number = int(value)
                if 1 <= number <= 500:
                    clean[key] = number
            else:
                money = Decimal(str(value))
                if 0 < money <= 100_000:
                    clean[key] = money
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise DecisionError(f"edición inválida en «{key}»") from exc
    return clean


def shortlist_ids(review: models.ReviewTask) -> set[str]:
    return {
        c["matchResultId"]
        for block in review.proposal.get("postings", [])
        for c in block.get("candidates", [])
    }


def validate_decision(
    review: models.ReviewTask,
    decision: Decision,
    comment: str | None,
    edits: dict[str, Any] | None,
) -> None:
    if review.kind == "alerta_sesgo":
        if decision == "editar":
            raise DecisionError("Una alerta de sesgo solo se acepta (aprobar) o se descarta")
        if decision == "rechazar" and not (comment or "").strip():
            raise DecisionError(
                "Descartar una alerta de sesgo exige un comentario de justificación"
            )
    elif review.kind == "bloqueo_oferta" and decision == "editar":
        if not clean_posting_edits(edits):
            raise DecisionError(
                "Editar una oferta exige `edits` con title, salaryMin, salaryMax o vacancies"
            )
    elif review.kind == "lista_corta" and decision == "editar":
        if not edits or not (edits.get("remove") or edits.get("order")):
            raise DecisionError("Editar la lista corta exige `edits.remove` y/o `edits.order`")
        known = shortlist_ids(review)
        for key in ("remove", "order"):
            ids = edits.get(key) or []
            if not isinstance(ids, list) or not set(ids) <= known:
                raise DecisionError(f"`edits.{key}` contiene ids que no están en la lista corta")
