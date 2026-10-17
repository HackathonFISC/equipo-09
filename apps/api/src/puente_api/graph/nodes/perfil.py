"""Agente de Perfil: CV y entrevista adaptativa → `profile_skill[]` con evidencia.

El LLM propone habilidades y redacta preguntas; el código exige que cada habilidad cite un
fragmento literal del texto fuente, la normaliza a ESCO-lite, calcula los huecos frente a la
demanda de las ofertas publicadas y decide cuándo termina la entrevista.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from puente_api.db import models
from puente_api.graph.guardrail_port import screen_input
from puente_api.graph.state import PuenteState, deps
from puente_api.graph.taxonomy import SkillIndex, evidence_in
from puente_api.llm import LLMClient
from puente_api.llm.prompts import (
    PERFIL_CV_SYSTEM,
    PERFIL_CV_USER,
    PERFIL_INTERVIEW_SYSTEM,
    PERFIL_INTERVIEW_USER,
)
from puente_api.tracing import TraceEntry, traced

MIN_TURNS = 2
MAX_TURNS = 5
GAP_LIMIT = 8

# Preguntas seguras si el LLM no responde: cubren lo que más piden las ofertas de entrada.
FALLBACK_QUESTIONS = [
    "¿Has trabajado o ayudado alguna vez atendiendo a clientes, en un negocio o con tu familia?",
    "¿Has manejado dinero, una caja o cuentas, aunque sea de forma informal?",
    "¿Qué herramientas de computadora o del celular usas con soltura?",
    "¿Has organizado o cuidado algo: un inventario, una bodega, niños o un evento?",
    "¿Hay algún oficio o tarea práctica en la que te consideres bueno o buena?",
]


class InterviewStateError(ValueError):
    """La respuesta no corresponde a ninguna pregunta abierta."""


class ExtractedProfileSkill(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    level: int = Field(default=1, ge=1, le=3)
    evidence: str = Field(min_length=1, max_length=400)


class CvExtraction(BaseModel):
    skills: list[ExtractedProfileSkill] = Field(default_factory=list, max_length=40)


class InterviewOutput(BaseModel):
    skills: list[ExtractedProfileSkill] = Field(default_factory=list, max_length=10)
    next_question: str | None = Field(default=None, max_length=300)


def _save_skills(
    session: Session,
    youth: models.Youth,
    index: SkillIndex,
    extracted: list[ExtractedProfileSkill],
    source_text: str,
    source: str,
) -> tuple[list[models.ProfileSkill], list[str]]:
    """Valida evidencia, normaliza y hace upsert. Devuelve (guardadas, descartadas)."""
    by_skill = {ps.skill_id: ps for ps in youth.skills}
    saved: dict[str, models.ProfileSkill] = {}
    rejected: list[str] = []
    for item in extracted:
        if not evidence_in(item.evidence, source_text):
            rejected.append(f"{item.name} (evidencia no literal)")
            continue
        skill = index.match(item.name)
        if skill is None:
            rejected.append(f"{item.name} (fuera de ESCO-lite)")
            continue
        current = by_skill.get(skill.id)
        if current is None:
            current = models.ProfileSkill(
                skill_id=skill.id, level=item.level, source=source, evidence=item.evidence
            )
            current.skill = skill
            youth.skills.append(current)
            by_skill[skill.id] = current
        elif item.level >= current.level:
            current.level, current.source, current.evidence = item.level, source, item.evidence
        saved[skill.id] = current
    session.flush()
    return list(saved.values()), rejected


def _demand_gaps(session: Session, youth: models.Youth) -> list[str]:
    """Habilidades más pedidas por ofertas publicadas que el joven aún no tiene."""
    have = {ps.skill_id for ps in youth.skills}
    stmt = (
        select(models.Skill.id, models.Skill.label_es, func.count().label("n"))
        .join(models.PostingRequirement, models.PostingRequirement.skill_id == models.Skill.id)
        .join(models.JobPosting, models.JobPosting.id == models.PostingRequirement.posting_id)
        .where(models.JobPosting.status == "publicada")
        .group_by(models.Skill.id, models.Skill.label_es)
        .order_by(func.count().desc(), models.Skill.label_es)
    )
    return [label for sid, label, _n in session.execute(stmt) if sid not in have][:GAP_LIMIT]


def _labels(skills: list[models.ProfileSkill]) -> str:
    return ", ".join(ps.skill.label_es for ps in skills) or "ninguna"


def _run_cv(
    session: Session, llm: LLMClient, youth: models.Youth, text: str, trace: TraceEntry
) -> dict[str, Any]:
    trace.input_summary = f"cv: {text}"
    youth.cv_raw_text = text
    index = SkillIndex.load(session)
    extraction = llm.structured(
        PERFIL_CV_USER.format(skills="; ".join(index.labels), text=text),
        CvExtraction,
        system=PERFIL_CV_SYSTEM,
        default=CvExtraction(),
    )
    saved, rejected = _save_skills(session, youth, index, extraction.skills, text, "cv")
    trace.decision = f"{len(saved)} habilidades del CV guardadas con evidencia"
    trace.reason = f"guardadas: {_labels(saved)}" + (
        f" | descartadas: {', '.join(rejected)}" if rejected else ""
    )
    return {"youth_id": youth.id, "skill_ids": [ps.skill_id for ps in saved]}


def _run_interview(
    session: Session,
    llm: LLMClient,
    youth: models.Youth,
    answer: str | None,
    trace: TraceEntry,
) -> dict[str, Any]:
    turns = list(
        session.scalars(
            select(models.InterviewTurn)
            .where(models.InterviewTurn.youth_id == youth.id)
            .order_by(models.InterviewTurn.idx)
        )
    )
    open_turn = turns[-1] if turns and turns[-1].answer is None else None

    # Reinicio idempotente: answer=null con una pregunta abierta la repite.
    if answer is None and open_turn is not None:
        trace.input_summary = "inicio de entrevista (pregunta pendiente)"
        trace.decision = f"repite la pregunta {open_turn.idx}"
        return {"done": False, "question": open_turn.question, "index": open_turn.idx}
    if answer is not None and open_turn is None:
        raise InterviewStateError("No hay una pregunta abierta: inicia con answer = null")

    answered = [t for t in turns if t.answer is not None]
    if answer is None and len(answered) >= MAX_TURNS:
        trace.input_summary = "inicio de entrevista"
        trace.decision = "entrevista ya completada"
        return {"done": True, "skill_ids": [ps.skill_id for ps in youth.skills]}

    index = SkillIndex.load(session)
    history = "\n".join(f"P{t.idx}: {t.question}\nR{t.idx}: {t.answer}" for t in answered)
    gaps = _demand_gaps(session, youth)
    n_answered = len(answered) + (1 if answer is not None else 0)
    fallback = (
        FALLBACK_QUESTIONS[n_answered % len(FALLBACK_QUESTIONS)] if n_answered < MAX_TURNS else None
    )
    output = llm.structured(
        PERFIL_INTERVIEW_USER.format(
            skills="; ".join(index.labels),
            current=_labels(list(youth.skills)),
            gaps=", ".join(gaps) or "ninguno",
            history=history or "(sin turnos)",
            question=open_turn.question if open_turn else "(ninguna, es el inicio)",
            answer=answer or "",
        ),
        InterviewOutput,
        system=PERFIL_INTERVIEW_SYSTEM,
        default=InterviewOutput(next_question=fallback),
    )

    discovered: list[models.ProfileSkill] = []
    rejected: list[str] = []
    if answer is not None and open_turn is not None:
        open_turn.answer = answer
        discovered, rejected = _save_skills(
            session, youth, index, output.skills, answer, "entrevista"
        )
        trace.input_summary = f"respuesta {open_turn.idx}: {answer}"
    else:
        trace.input_summary = "inicio de entrevista"

    # El código decide el cierre: tope de turnos, o el LLM no ve huecos tras un mínimo.
    next_question = (output.next_question or "").strip() or None
    if n_answered < MIN_TURNS and next_question is None:
        next_question = fallback
    done = n_answered >= MAX_TURNS or next_question is None

    reason = f"huecos: {', '.join(gaps) or 'ninguno'}"
    if discovered:
        reason += f" | descubiertas: {_labels(discovered)}"
    if rejected:
        reason += f" | descartadas: {', '.join(rejected)}"
    trace.reason = reason

    if done:
        session.flush()
        trace.decision = f"entrevista completa tras {n_answered} respuestas"
        return {
            "done": True,
            "skill_ids": [ps.skill_id for ps in youth.skills],
            "discovered_ids": [ps.skill_id for ps in discovered],
        }

    idx = (turns[-1].idx + 1) if turns else 1
    session.add(models.InterviewTurn(youth_id=youth.id, idx=idx, question=next_question))
    session.flush()
    trace.decision = f"pregunta {idx}: {next_question}"
    return {
        "done": False,
        "question": next_question,
        "index": idx,
        "skill_ids": [ps.skill_id for ps in discovered],
    }


def perfil_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, llm, thread_id = deps(config)
    payload = state["payload"]
    youth = session.get(models.Youth, payload["youth_id"])
    if youth is None:
        raise ValueError(f"Joven {payload['youth_id']} no existe")

    with traced(session, thread_id, "perfil", llm) as trace:
        trace.tool = "ESCO-lite + evidencia literal"
        if state["event"] == "profile.cv":
            text = screen_input(session, thread_id, "perfil", payload["text"], "CV", source="cv")
            result = _run_cv(session, llm, youth, text, trace)
        else:
            answer = payload.get("answer")
            if answer is not None:
                answer = screen_input(
                    session,
                    thread_id,
                    "perfil",
                    answer,
                    "respuesta de entrevista",
                    source="interview",
                )
            result = _run_interview(session, llm, youth, answer, trace)
    return {"result": result}
