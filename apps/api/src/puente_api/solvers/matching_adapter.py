"""Adaptadores entre el solver de matching y la capa de datos.

- `input_from_seed(bundle)`: entrada del solver desde los archivos semilla (sin BD).
- `input_from_models(youths, postings, commute_rows)`: desde objetos SQLAlchemy ya cargados.
- `load_matching_input(session)`: consulta la BD y arma la entrada (ofertas `publicada`).
- `to_match_result_rows(result, run_id)`: filas para `match_result` con `score_breakdown` y
  `constraints_checked` en el formato de `openapi.yaml` (camelCase) + detalle completo.
- `run_params(result)`: dict para `match_run.params` / `solver_status` / `solve_ms`.

El LLM nunca entra aquí; la explicación se redacta después a partir del desglose.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from puente_api.solvers.matching import (
    C_BUDGET,
    C_COMMUTE,
    C_SALARY,
    C_SCHEDULE,
    CommuteEntry,
    MatchingResult,
    PostingIn,
    Requirement,
    TimeSlot,
    YouthIn,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from puente_api.db import models
    from puente_api.db.seed.schemas import SeedBundle


@dataclass(frozen=True)
class MatchingInput:
    youths: list[YouthIn]
    postings: list[PostingIn]
    commute: dict[tuple[str, str], CommuteEntry]


def _slots(raw: Iterable[Any]) -> tuple[TimeSlot, ...]:
    """Acepta franjas `{day,start,end}` (openapi) o `{dia,inicio,fin}` (doc 05)."""
    out = []
    for s in raw or []:
        d = s if isinstance(s, dict) else s.model_dump()
        out.append(
            TimeSlot(
                day=d.get("day", d.get("dia")),
                start=d.get("start", d.get("inicio")),
                end=d.get("end", d.get("fin")),
            )
        )
    return tuple(out)


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def input_from_seed(
    bundle: SeedBundle, *, statuses: Sequence[str] = ("publicada",)
) -> MatchingInput:
    """Entrada del solver desde un `SeedBundle`, con los UUID deterministas del loader."""
    from puente_api.db.seed.loaders import seed_uuid

    def loc(k: str) -> str:
        return str(seed_uuid("location", k))

    def sk(k: str) -> str:
        return str(seed_uuid("skill", k))

    youths = [
        YouthIn(
            id=str(seed_uuid("youth", y.key)),
            location_id=loc(y.location),
            max_commute_min=y.max_commute_min,
            transport_budget_daily=y.transport_budget_daily,
            availability=_slots(y.availability),
            min_salary=y.min_salary,
            skills={sk(s.skill): s.level for s in y.skills},
        )
        for y in bundle.youth
    ]
    postings = [
        PostingIn(
            id=str(seed_uuid("job_posting", p.key)),
            location_id=loc(p.location),
            schedule=_slots(p.schedule),
            salary_min=p.salary_min,
            salary_max=p.salary_max,
            vacancies=p.vacancies,
            requirements=tuple(
                Requirement(skill_id=sk(r.skill), weight=r.weight, required=r.required)
                for r in p.requirements
            ),
        )
        for p in bundle.postings
        if p.status in statuses
    ]
    commute = {
        (loc(c.origin), loc(c.dest)): CommuteEntry(minutes=c.minutes, cost_daily=c.cost_daily)
        for c in bundle.commute
    }
    return MatchingInput(youths, postings, commute)


def input_from_models(
    youths: Iterable[models.Youth],
    postings: Iterable[models.JobPosting],
    commute_rows: Iterable[models.CommuteMatrix],
) -> MatchingInput:
    """Entrada del solver desde objetos ORM (con `skills` y `requirements` cargados)."""
    ys = [
        YouthIn(
            id=y.id,
            location_id=y.location_id,
            max_commute_min=y.max_commute_min,
            transport_budget_daily=float(y.transport_budget_daily),
            availability=_slots(y.availability),
            min_salary=_f(y.min_salary),
            skills={s.skill_id: s.level for s in y.skills},
        )
        for y in youths
    ]
    ps = [
        PostingIn(
            id=p.id,
            location_id=p.location_id,
            schedule=_slots(p.schedule),
            salary_min=_f(p.salary_min),
            salary_max=_f(p.salary_max),
            vacancies=p.vacancies,
            requirements=tuple(
                Requirement(skill_id=r.skill_id, weight=r.weight, required=r.required)
                for r in p.requirements
            ),
        )
        for p in postings
    ]
    commute = {
        (c.origin_id, c.dest_id): CommuteEntry(minutes=c.minutes, cost_daily=float(c.cost_daily))
        for c in commute_rows
    }
    return MatchingInput(ys, ps, commute)


def load_matching_input(
    session: Session,
    *,
    statuses: Sequence[str] = ("publicada",),
    youth_ids: Sequence[str] | None = None,
    posting_ids: Sequence[str] | None = None,
) -> MatchingInput:
    """Consulta jóvenes, ofertas (por estado) y la matriz de traslado."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from puente_api.db import models

    yq = select(models.Youth).options(selectinload(models.Youth.skills))
    if youth_ids is not None:
        yq = yq.where(models.Youth.id.in_(youth_ids))
    pq = (
        select(models.JobPosting)
        .options(selectinload(models.JobPosting.requirements))
        .where(models.JobPosting.status.in_(statuses))
    )
    if posting_ids is not None:
        pq = pq.where(models.JobPosting.id.in_(posting_ids))
    return input_from_models(
        session.scalars(yq).all(),
        session.scalars(pq).all(),
        session.scalars(select(models.CommuteMatrix)).all(),
    )


def to_match_result_rows(result: MatchingResult, run_id: str) -> list[dict[str, Any]]:
    """Filas para `match_result`. `score_breakdown`/`constraints_checked` llevan las claves
    camelCase de openapi.yaml y, además, el detalle completo (`detail`) para el auditor."""
    rows = []
    for a in result.assignments:
        b = a.breakdown
        c = {x.name: x for x in a.constraints}
        rows.append(
            {
                "run_id": run_id,
                "youth_id": a.youth_id,
                "posting_id": a.posting_id,
                "score": a.score,
                "score_breakdown": {
                    "skillCoverage": b.skill_coverage,
                    "commute": b.commute,
                    "cost": b.cost,
                    "schedule": b.schedule,
                    "salary": b.salary,
                    "missingSkills": list(b.missing_skills),
                    "missingRequired": list(b.missing_required),
                    "penalty": b.penalty,
                },
                "constraints_checked": {
                    "commuteMin": int(c[C_COMMUTE].value or 0),
                    "dailyCost": float(c[C_BUDGET].value or 0.0),
                    "scheduleOverlap": bool(c[C_SCHEDULE].ok),
                    "salaryOk": bool(c[C_SALARY].ok),
                    "active": a.active_constraints,
                    "slacks": [s.model_dump() for s in a.slacks],
                    "detail": [x.model_dump() for x in a.constraints],
                },
                "status": "propuesto",
            }
        )
    return rows


def run_params(result: MatchingResult) -> dict[str, Any]:
    """Campos para `match_run`: `params` (jsonb), `solver_status`, `solve_ms`."""
    return {
        "params": {
            **result.params.model_dump(mode="json"),
            "eligible_pairs": result.eligible_pairs,
            "objective": result.objective,
            "unfilled": result.unfilled,
            "unassigned": [u.model_dump() for u in result.unassigned],
        },
        "solver_status": result.status,
        "solve_ms": result.solve_ms,
    }
