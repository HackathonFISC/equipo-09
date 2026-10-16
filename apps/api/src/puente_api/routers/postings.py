"""Ofertas de empleo: lectura e ingesta con el agente de Mercado."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db
from puente_api.graph import runner
from puente_api.llm import LLMClient, get_llm
from puente_api.problems import ProblemError
from puente_api.routers.uploads import read_input

router = APIRouter(prefix="/postings", tags=["empresas"])

DB = Annotated[Session, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm)]


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


@router.post(
    "",
    operation_id="ingestPosting",
    status_code=202,
    response_model=schemas.Accepted,
    response_model_exclude_none=True,
)
async def ingest_posting(
    db: DB,
    llm: LLM,
    company_id: Annotated[str, Form(alias="companyId")],
    text: Annotated[str | None, Form(max_length=20000)] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> schemas.Accepted:
    """Agente de Mercado: extrae, normaliza y persiste la oferta (bloqueada si discrimina)."""
    if db.get(models.Company, company_id) is None:
        raise ProblemError(422, f"Empresa {company_id} no existe")
    uploaded = await read_input(text, file)
    payload = {
        "company_id": company_id,
        "text": uploaded.text,
        "input_type": uploaded.input_type,
        "raw_input": uploaded.text,
    }
    thread_id, result = await run_in_threadpool(runner.run, db, llm, "posting.created", payload)
    return schemas.Accepted(thread_id=thread_id, resource_id=result.get("posting_id"))
