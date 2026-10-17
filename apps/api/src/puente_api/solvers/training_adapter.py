"""Adaptadores del solver de formación: seeds u ORM -> `CourseIn`.

Firmas públicas::

    courses_from_seed(bundle: SeedBundle) -> list[CourseIn]
    courses_from_models(courses: Iterable[models.Course]) -> list[CourseIn]
        # requiere course.center, course.sessions y course.skills cargados
    load_courses(session: Session) -> list[CourseIn]

Los ids coinciden con los de `matching_adapter` (UUID del seed o `id` de la fila). El joven y
las ofertas se arman con `matching_adapter.input_from_seed / load_matching_input`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from puente_api.solvers.matching_adapter import _slots
from puente_api.solvers.training import CourseIn, SessionIn

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from puente_api.db import models
    from puente_api.db.seed.schemas import SeedBundle


def courses_from_seed(bundle: SeedBundle) -> list[CourseIn]:
    from puente_api.db.seed.loaders import seed_uuid

    centers = {c.key: c for c in bundle.training_centers}
    out = []
    for c in bundle.courses:
        center = centers[c.center]
        out.append(
            CourseIn(
                id=str(seed_uuid("course", c.key)),
                title=c.title,
                center_id=str(seed_uuid("training_center", c.center)),
                center_location_id=str(seed_uuid("location", center.location)),
                hours=c.hours,
                cost=c.cost,
                skill_ids=tuple(str(seed_uuid("skill", s)) for s in c.skills),
                sessions=tuple(
                    SessionIn(
                        id=str(seed_uuid("course_session", f"{c.key}:{s.key}")),
                        start_date=s.start_date,
                        schedule=_slots(s.schedule),
                        seats_total=s.seats_total,
                        seats_taken=s.seats_taken,
                    )
                    for s in c.sessions
                ),
            )
        )
    return out


def courses_from_models(courses: Iterable[models.Course]) -> list[CourseIn]:
    return [
        CourseIn(
            id=c.id,
            title=c.title,
            center_id=c.center_id,
            center_location_id=c.center.location_id,
            hours=c.hours,
            cost=float(c.cost),
            skill_ids=tuple(s.skill_id for s in c.skills),
            sessions=tuple(
                SessionIn(
                    id=s.id,
                    start_date=s.start_date,
                    schedule=_slots(s.schedule),
                    seats_total=s.seats_total,
                    seats_taken=s.seats_taken,
                )
                for s in c.sessions
            ),
        )
        for c in courses
    ]


def load_courses(session: Session) -> list[CourseIn]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from puente_api.db import models

    q = select(models.Course).options(
        selectinload(models.Course.center),
        selectinload(models.Course.sessions),
        selectinload(models.Course.skills),
    )
    return courses_from_models(session.scalars(q).all())
