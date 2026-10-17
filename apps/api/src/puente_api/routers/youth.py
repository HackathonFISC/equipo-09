"""Jóvenes: registro, perfil, CV y entrevista (agente de Perfil)."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from puente_api import schemas
from puente_api.db import models
from puente_api.db.session import get_db
from puente_api.graph import runner
from puente_api.graph.nodes.perfil import InterviewStateError
from puente_api.llm import LLMClient, get_llm
from puente_api.problems import ProblemError
from puente_api.routers.serializers import training_plan_out
from puente_api.routers.uploads import read_input

router = APIRouter(prefix="/youth", tags=["jovenes"])

DB = Annotated[Session, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm)]


def _load_youth(db: Session, youth_id: str) -> models.Youth:
    youth = db.scalar(
        select(models.Youth)
        .where(models.Youth.id == youth_id)
        .options(selectinload(models.Youth.skills).selectinload(models.ProfileSkill.skill))
        .execution_options(populate_existing=True)
    )
    if youth is None:
        raise ProblemError(404, f"Joven {youth_id} no existe")
    return youth


@router.post(
    "",
    operation_id="createYouth",
    status_code=201,
    response_model=schemas.Youth,
    response_model_exclude_none=True,
)
def create_youth(body: schemas.YouthCreate, db: DB) -> models.Youth:
    if db.get(models.Location, body.location_id) is None:
        raise ProblemError(422, f"Corregimiento {body.location_id} no existe", "dato_absurdo")
    youth = models.Youth(
        display_name=body.display_name,
        birth_year=body.birth_year,
        gender=body.gender,
        location_id=body.location_id,
        max_commute_min=body.max_commute_min,
        transport_budget_daily=Decimal(str(body.transport_budget_daily)),
        min_salary=Decimal(str(body.min_salary)) if body.min_salary is not None else None,
        studying=bool(body.studying),
        availability=[slot.model_dump() for slot in body.availability],
        is_synthetic=False,
    )
    db.add(youth)
    db.commit()
    return _load_youth(db, youth.id)


@router.get(
    "/{youth_id}",
    operation_id="getYouth",
    response_model=schemas.Youth,
    response_model_exclude_none=True,
)
def get_youth(youth_id: str, db: DB) -> models.Youth:
    return _load_youth(db, youth_id)


@router.post(
    "/{youth_id}/cv",
    operation_id="uploadCv",
    status_code=202,
    response_model=schemas.Accepted,
    response_model_exclude_none=True,
)
async def upload_cv(
    youth_id: str,
    db: DB,
    llm: LLM,
    text: Annotated[str | None, Form(max_length=20000)] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> schemas.Accepted:
    """Agente de Perfil: extrae habilidades con evidencia del CV (PDF o texto)."""
    _load_youth(db, youth_id)
    uploaded = await read_input(text, file)
    payload = {"youth_id": youth_id, "text": uploaded.text}
    thread_id, _ = await run_in_threadpool(runner.run, db, llm, "profile.cv", payload)
    return schemas.Accepted(thread_id=thread_id, resource_id=youth_id)


def interview_thread_id(youth_id: str) -> str:
    """Un hilo por joven: toda su entrevista queda en la misma línea de tiempo."""
    return f"entrevista-{youth_id}"


@router.post(
    "/{youth_id}/interview",
    operation_id="answerInterview",
    response_model=schemas.InterviewStep,
    response_model_exclude_none=True,
)
async def answer_interview(
    youth_id: str, body: schemas.InterviewAnswer, db: DB, llm: LLM
) -> schemas.InterviewStep:
    """Guarda la respuesta, extrae habilidades y devuelve la siguiente pregunta o el perfil."""
    _load_youth(db, youth_id)
    answer = body.answer.strip() if body.answer and body.answer.strip() else None
    if body.answer is not None and answer is None:
        raise ProblemError(422, "La respuesta está vacía")
    payload = {"youth_id": youth_id, "answer": answer}
    try:
        _, result = await run_in_threadpool(
            runner.run, db, llm, "profile.interview", payload, interview_thread_id(youth_id)
        )
    except InterviewStateError as exc:
        raise ProblemError(422, str(exc)) from exc

    youth = _load_youth(db, youth_id)
    by_skill = {ps.skill_id: ps for ps in youth.skills}
    # En curso: lo descubierto en este turno. Al cerrar: el perfil final completo.
    skills = [by_skill[sid] for sid in result.get("skill_ids", []) if sid in by_skill]
    return schemas.InterviewStep(
        done=result["done"],
        question=result.get("question"),
        index=result.get("index"),
        discovered_skills=[schemas.ProfileSkill.model_validate(ps) for ps in skills],
    )


@router.post(
    "/{youth_id}/training-plan",
    operation_id="createTrainingPlan",
    status_code=202,
    response_model=schemas.Accepted,
    response_model_exclude_none=True,
)
async def create_training_plan(youth_id: str, db: DB, llm: LLM) -> schemas.Accepted:
    """Agente de Ruta de formación: el solver MIP elige cursos; el LLM explica la ruta."""
    _load_youth(db, youth_id)
    thread_id, result = await run_in_threadpool(
        runner.run, db, llm, "training.requested", {"youth_id": youth_id}
    )
    return schemas.Accepted(thread_id=thread_id, resource_id=result.get("plan_id"))


@router.get(
    "/{youth_id}/training-plan",
    operation_id="getTrainingPlan",
    response_model=schemas.TrainingPlan,
    response_model_exclude_none=True,
)
def get_training_plan(youth_id: str, db: DB) -> schemas.TrainingPlan:
    """Última ruta de formación calculada para el joven."""
    _load_youth(db, youth_id)
    plan = db.scalar(
        select(models.TrainingPlan)
        .where(models.TrainingPlan.youth_id == youth_id)
        .options(selectinload(models.TrainingPlan.items))
        .order_by(models.TrainingPlan.created_at.desc())
        .limit(1)
    )
    if plan is None:
        raise ProblemError(404, f"El joven {youth_id} aún no tiene una ruta de formación")
    return training_plan_out(db, plan)
