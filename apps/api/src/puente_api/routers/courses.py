"""Cursos con sesiones (lectura). Los usan `/centro` y la ruta de formación en la web."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db

router = APIRouter(prefix="/courses", tags=["formacion"])

DB = Annotated[Session, Depends(get_db)]


@router.get(
    "",
    operation_id="listCourses",
    response_model=list[schemas.Course],
    response_model_exclude_none=True,
)
def list_courses(db: DB) -> list[schemas.Course]:
    courses = db.scalars(
        select(models.Course)
        .options(selectinload(models.Course.sessions), selectinload(models.Course.skills))
        .order_by(models.Course.title, models.Course.id)
    )
    return [
        schemas.Course(
            id=c.id,
            center_id=c.center_id,
            title=c.title,
            hours=c.hours,
            cost=float(c.cost or 0),
            skill_ids=sorted(cs.skill_id for cs in c.skills),
            sessions=[
                schemas.CourseSession.model_validate(s)
                for s in sorted(c.sessions, key=lambda s: (s.start_date, s.id))
            ],
        )
        for c in courses
    ]
