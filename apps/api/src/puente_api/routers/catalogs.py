"""Catálogos: corregimientos y taxonomía ESCO-lite."""

import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db

router = APIRouter(tags=["catalogos"])

DB = Annotated[Session, Depends(get_db)]


def _fold(text: str) -> str:
    """Minúsculas sin acentos, para que «atencion» encuentre «Atención»."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@router.get(
    "/locations",
    operation_id="listLocations",
    response_model=list[schemas.Location],
    response_model_exclude_none=True,
)
def list_locations(db: DB) -> list[models.Location]:
    stmt = select(models.Location).order_by(
        models.Location.provincia, models.Location.distrito, models.Location.corregimiento
    )
    return list(db.scalars(stmt))


@router.get(
    "/skills",
    operation_id="listSkills",
    response_model=list[schemas.Skill],
    response_model_exclude_none=True,
)
def list_skills(db: DB, q: Annotated[str | None, Query()] = None) -> list[models.Skill]:
    skills = list(db.scalars(select(models.Skill).order_by(models.Skill.label_es)))
    if not q or not q.strip():
        return skills
    # ~150 filas: filtrar en Python permite ignorar acentos también en SQLite.
    needle = _fold(q.strip())
    return [
        skill
        for skill in skills
        if needle in _fold(skill.label_es)
        or any(needle in _fold(alias) for alias in skill.aliases or [])
    ]
