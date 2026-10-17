"""Agente de Inteligencia de mercado: texto de oferta → `job_posting` + `posting_requirement[]`.

El LLM extrae; el código normaliza a ESCO-lite y a corregimientos, sanea rangos, verifica que
los hallazgos discriminatorios citen texto literal y decide el estado de la oferta.
"""

from decimal import Decimal
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sqlalchemy import select

from puente_api.db import models
from puente_api.graph.guardrail_port import screen_input
from puente_api.graph.state import PuenteState, deps
from puente_api.graph.taxonomy import SkillIndex, evidence_in, match_location
from puente_api.llm.prompts import MERCADO_SYSTEM, MERCADO_USER
from puente_api.schemas import TimeSlotIn
from puente_api.tracing import traced

FlagKind = Literal[
    "edad",
    "genero",
    "apariencia",
    "estado_civil",
    "foto",
    "residencia",
    "religion",
    "nacionalidad",
    "otro",
]
# Variables de auditoría del contrato (`AuditCheck.variable`).
_AUDIT_VARIABLE = {"genero": "genero", "residencia": "corregimiento"}


class ExtractedRequirement(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    weight: int = Field(default=2, ge=1, le=3)
    required: bool = True
    evidence: str | None = Field(default=None, max_length=400)


class FlaggedRequirement(BaseModel):
    kind: FlagKind
    text: str = Field(min_length=1, max_length=300)


class PostingExtraction(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    skills: list[ExtractedRequirement] = Field(default_factory=list, max_length=30)
    corregimiento: str | None = None
    schedule: list[TimeSlotIn] = Field(default_factory=list, max_length=14)
    salary_min: float | None = None
    salary_max: float | None = None
    vacancies: int = Field(default=1, ge=1, le=500)
    flagged_requirements: list[FlaggedRequirement] = Field(default_factory=list)


def _fallback_title(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "Oferta sin título")
    return first[:200]


def _money(value: float | None) -> Decimal | None:
    if value is None or value <= 0 or value > 100_000:
        return None
    return Decimal(str(round(value, 2)))


def mercado_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, llm, thread_id = deps(config)
    payload = state["payload"]
    text: str = payload["text"]
    company = session.get(models.Company, payload["company_id"])
    if company is None:
        raise ValueError(f"Empresa {payload['company_id']} no existe")

    with traced(session, thread_id, "mercado", llm) as trace:
        trace.tool = "ESCO-lite + reglas de oferta"
        text = screen_input(session, thread_id, "mercado", text, "oferta")
        trace.input_summary = f"{payload['input_type']}: {text}"
        index = SkillIndex.load(session)
        corregimientos = sorted(session.scalars(select(models.Location.corregimiento)))
        prompt = MERCADO_USER.format(
            skills="; ".join(index.labels),
            locations="; ".join(corregimientos),
            text=text,
        )
        extraction = llm.structured(
            prompt,
            PostingExtraction,
            system=MERCADO_SYSTEM,
            default=PostingExtraction(title=_fallback_title(text)),
        )

        # Normalización a ESCO-lite: deduplicar por habilidad (peso máximo, requerido si alguno).
        requirements: dict[str, models.PostingRequirement] = {}
        labels: dict[str, str] = {}
        discarded: list[str] = []
        for req in extraction.skills:
            skill = index.match(req.name)
            if skill is None:
                discarded.append(req.name)
                continue
            labels[skill.id] = skill.label_es
            current = requirements.get(skill.id)
            if current is None:
                requirements[skill.id] = models.PostingRequirement(
                    skill_id=skill.id, weight=req.weight, required=req.required
                )
            else:
                current.weight = max(current.weight, req.weight)
                current.required = current.required or req.required

        location = match_location(session, extraction.corregimiento)
        salary_min, salary_max = _money(extraction.salary_min), _money(extraction.salary_max)
        if salary_min and salary_max and salary_min > salary_max:
            salary_min, salary_max = salary_max, salary_min

        # Solo cuentan los hallazgos que citan texto literal de la oferta.
        flags = [f for f in extraction.flagged_requirements if evidence_in(f.text, text)]
        status = "bloqueada" if flags else "publicada"

        posting = models.JobPosting(
            company_id=company.id,
            title=extraction.title,
            raw_input=payload.get("raw_input", text),
            input_type=payload["input_type"],
            location_id=location.id if location else company.location_id,
            schedule=[slot.model_dump() for slot in extraction.schedule],
            salary_min=salary_min,
            salary_max=salary_max,
            vacancies=extraction.vacancies,
            status=status,
            requirements=list(requirements.values()),
        )
        session.add(posting)
        session.flush()

        review_ids: list[str] = []
        if flags:
            variables = {_AUDIT_VARIABLE.get(f.kind) for f in flags} - {None}
            session.add(
                models.AuditCheck(
                    posting_id=posting.id,
                    kind="discriminacion",
                    variable=next(iter(sorted(variables)), None),
                    passed=False,
                    findings=[f"{f.kind}: «{f.text}»" for f in flags],
                )
            )
            # El grafo se pausa en el nodo `orientador` hasta que el orientador decida.
            task = models.ReviewTask(
                kind="bloqueo_oferta",
                subject_id=posting.id,
                proposal={
                    "action": "bloquear",
                    "postingTitle": posting.title,
                    "vacancies": posting.vacancies,
                    "salaryMin": float(posting.salary_min) if posting.salary_min else None,
                    "salaryMax": float(posting.salary_max) if posting.salary_max else None,
                    "originalText": posting.raw_input,
                    "findings": [f.model_dump() for f in flags],
                },
                explanation="La oferta contiene requisitos posiblemente discriminatorios: "
                + "; ".join(f"«{f.text}» ({f.kind})" for f in flags),
                graph_thread_id=thread_id,
            )
            session.add(task)
            session.flush()
            review_ids.append(task.id)

        trace.decision = f"oferta {status}: «{posting.title}» con {len(requirements)} habilidades"
        reasons = [
            f"habilidades: {', '.join(labels.values()) or 'ninguna'}",
            f"ubicación: {location.corregimiento if location else 'la de la empresa'}",
        ]
        if discarded:
            reasons.append(f"fuera de ESCO-lite (descartadas): {', '.join(discarded)}")
        if flags:
            reasons.append("hallazgos: " + "; ".join(f"{f.kind} «{f.text}»" for f in flags))
        trace.reason = " | ".join(reasons)
        trace.output_summary = (
            f"oferta {posting.id}: {len(requirements)} requisitos, {len(flags)} hallazgo(s)"
        )

    return {
        "result": {"posting_id": posting.id, "status": status},
        "review_ids": review_ids,
    }
