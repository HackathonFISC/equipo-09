"""Ofertas de empleo (lectura). La ingesta con agentes llega en H2."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db

router = APIRouter(prefix="/postings", tags=["empresas"])

DB = Annotated[Session, Depends(get_db)]


def _posting_query() -> Select[tuple[models.JobPosting]]:
    return select(models.JobPosting).options(
        selectinload(models.JobPosting.location),
        selectinload(models.JobPosting.requirements).selectinload(models.PostingRequirement.skill),
        selectinload(models.JobPosting.audit_checks),
    )


@router.get(
    "",
    operation_id="listPostings",
    response_model=list[schemas.JobPosting],
    response_model_exclude_none=True,
)
def list_postings(
    db: DB,
    status: Annotated[schemas.PostingStatus | None, Query()] = None,
    company_id: Annotated[str | None, Query(alias="companyId")] = None,
) -> list[models.JobPosting]:
    stmt = _posting_query().order_by(models.JobPosting.created_at.desc(), models.JobPosting.title)
    if status:
        stmt = stmt.where(models.JobPosting.status == status)
    if company_id:
        stmt = stmt.where(models.JobPosting.company_id == company_id)
    return list(db.scalars(stmt))


@router.get(
    "/{posting_id}",
    operation_id="getPosting",
    response_model=schemas.JobPosting,
    response_model_exclude_none=True,
)
def get_posting(posting_id: str, db: DB) -> models.JobPosting:
    posting = db.scalar(_posting_query().where(models.JobPosting.id == posting_id))
    if posting is None:
        raise HTTPException(status_code=404, detail=f"Oferta {posting_id} no existe")
    return posting
