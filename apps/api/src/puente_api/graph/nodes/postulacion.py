"""Agente de Postulación: CV y carta adaptados por candidato + `review_task` de lista corta.

El LLM redacta y verbaliza el desglose; el código elige quién entra a la lista corta (los
emparejamientos del solver, por puntaje) y verifica que el CV y la carta no mencionen
habilidades ausentes del perfil. Si la redacción no pasa el verificador se usa una plantilla
determinista armada solo con el perfil. Nada se envía a la empresa hasta que el orientador
apruebe la lista (nodo `orientador`).
"""

from collections import defaultdict
from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from puente_api.db import models
from puente_api.graph.state import PuenteState, deps
from puente_api.graph.taxonomy import SkillIndex, fold
from puente_api.llm.prompts import POSTULACION_SYSTEM, POSTULACION_USER
from puente_api.tracing import traced

MAX_CANDIDATES = 40
Breakdown = dict[str, Any]


class ApplicationDraft(BaseModel):
    tailored_cv: str = Field(min_length=20, max_length=3000)
    cover_letter: str = Field(min_length=20, max_length=2000)
    explanation: str = Field(min_length=10, max_length=600)
    skills_used: list[str] = Field(default_factory=list, max_length=40)


def foreign_skills(text: str, profile_skill_ids: set[str], index: SkillIndex) -> list[str]:
    """Etiquetas del catálogo que el texto menciona y que el perfil NO tiene."""
    padded = f" {fold(text)} "
    found: dict[str, str] = {}
    for key, skill in index.by_key.items():
        if skill.id not in profile_skill_ids and f" {key} " in padded:
            found[skill.id] = skill.label_es
    return sorted(found.values())


def verify_draft(
    draft: ApplicationDraft, profile_skill_ids: set[str], index: SkillIndex
) -> list[str]:
    """Violaciones del verificador (vacío = el borrador es válido)."""
    problems: list[str] = []
    for name in draft.skills_used:
        skill = index.match(name)
        if skill is None or skill.id not in profile_skill_ids:
            problems.append(f"declara «{name}» que no está en el perfil")
    for part, text in (("CV", draft.tailored_cv), ("carta", draft.cover_letter)):
        extra = foreign_skills(text, profile_skill_ids, index)
        if extra:
            problems.append(f"{part} menciona habilidades ausentes del perfil: {', '.join(extra)}")
    return problems


def fallback_draft(
    youth: models.Youth, posting: models.JobPosting, company: str, explanation: str
) -> ApplicationDraft:
    """Plantilla determinista: solo habilidades y evidencias del propio perfil."""
    skills = sorted(youth.skills, key=lambda ps: (-ps.level, ps.skill.label_es))
    lines = [f"- {ps.skill.label_es} (nivel {ps.level}): «{ps.evidence}»" for ps in skills]
    labels = ", ".join(ps.skill.label_es for ps in skills) or "las que detallo en mi perfil"
    cv = (
        f"{youth.display_name}\n"
        f"Resumen: postulación a «{posting.title}» en {company}.\n"
        "Habilidades con evidencia:\n" + ("\n".join(lines) or "- (perfil en construcción)")
    )
    letter = (
        f"Estimado equipo de {company}: me postulo a la vacante de {posting.title}. "
        f"Cuento con experiencia práctica en: {labels}. "
        "Quedo atento a una entrevista. Saludos cordiales, " + youth.display_name
    )
    return ApplicationDraft(
        tailored_cv=cv,
        cover_letter=letter,
        explanation=explanation,
        skills_used=[ps.skill.label_es for ps in skills],
    )


def _draft(
    llm,
    index: SkillIndex,
    youth: models.Youth,
    posting: models.JobPosting,
    company: str,
    result: models.MatchResult,
    base_explanation: str,
    skill_labels: dict[str, str],
) -> tuple[ApplicationDraft, list[str]]:
    """Devuelve (borrador final, violaciones del intento del LLM; vacío si fue válido)."""
    profile_ids = {ps.skill_id for ps in youth.skills}
    fallback = fallback_draft(youth, posting, company, base_explanation)
    skills_txt = (
        "\n".join(f"{ps.skill.label_es} | {ps.level} | {ps.evidence}" for ps in youth.skills)
        or "(sin habilidades)"
    )
    breakdown = dict(result.score_breakdown)
    breakdown["missingSkills"] = [
        skill_labels.get(s, s) for s in breakdown.get("missingSkills", [])
    ]
    breakdown.pop("missingRequired", None)
    prompt = POSTULACION_USER.format(
        name=youth.display_name,
        skills=skills_txt,
        title=posting.title,
        company=company,
        requirements="; ".join(
            f"{r.skill.label_es} ({'obligatoria' if r.required else 'deseable'})"
            for r in posting.requirements
        )
        or "(sin requisitos)",
        breakdown=breakdown,
    )
    draft = llm.structured(prompt, ApplicationDraft, system=POSTULACION_SYSTEM, default=fallback)
    if draft is fallback:
        return fallback, ["el LLM no devolvió una salida válida"]
    problems = verify_draft(draft, profile_ids, index)
    return (fallback, problems) if problems else (draft, [])


def postulacion_node(state: PuenteState, config: RunnableConfig) -> dict[str, Any]:
    session, llm, thread_id = deps(config)
    run_id = state["run_id"]
    review_ids = list(state.get("review_ids", []))

    with traced(session, thread_id, "postulacion") as trace:
        matches = list(
            session.scalars(
                select(models.MatchResult)
                .where(
                    models.MatchResult.run_id == run_id, models.MatchResult.status == "propuesto"
                )
                .order_by(models.MatchResult.score.desc(), models.MatchResult.youth_id)
                .limit(MAX_CANDIDATES)
            )
        )
        trace.input_summary = f"corrida {run_id}: {len(matches)} candidatos asignados"
        if not matches:
            trace.decision = "sin candidatos: no hay lista corta que revisar"
            return {"result": {**state.get("result", {}), "shortlists": 0}}

        index = SkillIndex.load(session)
        skill_labels = {s.id: s.label_es for s in session.scalars(select(models.Skill))}
        youths = {
            y.id: y
            for y in session.scalars(
                select(models.Youth)
                .where(models.Youth.id.in_({m.youth_id for m in matches}))
                .options(selectinload(models.Youth.skills).selectinload(models.ProfileSkill.skill))
            )
        }
        postings = {
            p.id: p
            for p in session.scalars(
                select(models.JobPosting)
                .where(models.JobPosting.id.in_({m.posting_id for m in matches}))
                .options(
                    selectinload(models.JobPosting.company),
                    selectinload(models.JobPosting.requirements).selectinload(
                        models.PostingRequirement.skill
                    ),
                )
            )
        }

        by_posting: dict[str, list[dict[str, Any]]] = defaultdict(list)
        fell_back: list[str] = []
        for match in matches:
            youth, posting = youths[match.youth_id], postings[match.posting_id]
            draft, problems = _draft(
                llm,
                index,
                youth,
                posting,
                posting.company.name,
                match,
                match.explanation or "",
                skill_labels,
            )
            if problems:
                fell_back.append(f"{youth.display_name}: {'; '.join(problems)}")
            match.explanation = draft.explanation
            application = models.Application(
                match_result_id=match.id,
                tailored_cv=draft.tailored_cv,
                cover_letter=draft.cover_letter,
                status="en_lista_corta",
            )
            session.add(application)
            session.flush()
            by_posting[posting.id].append(
                {
                    "rank": len(by_posting[posting.id]) + 1,
                    "matchResultId": match.id,
                    "applicationId": application.id,
                    "youthId": youth.id,
                    "displayName": youth.display_name,
                    "score": round(match.score, 4),
                    "explanation": draft.explanation,
                }
            )

        proposal = {
            "action": "enviar_lista_corta",
            "runId": run_id,
            "postings": [
                {
                    "postingId": pid,
                    "title": postings[pid].title,
                    "vacancies": postings[pid].vacancies,
                    "candidates": candidates,
                }
                for pid, candidates in by_posting.items()
            ],
        }
        task = models.ReviewTask(
            kind="lista_corta",
            subject_id=run_id,
            proposal=proposal,
            explanation=(
                f"Lista corta para {len(by_posting)} oferta(s) con {len(matches)} candidato(s). "
                "Revisa el orden, quita a quien no corresponda y aprueba para enviarla."
            ),
            graph_thread_id=thread_id,
        )
        session.add(task)
        session.flush()
        review_ids.append(task.id)

        trace.decision = (
            f"{len(matches)} postulaciones redactadas en {len(by_posting)} lista(s) corta(s); "
            "pausa para revisión del orientador"
        )
        trace.reason = "verificador: CV y carta solo con habilidades del perfil" + (
            f" | plantilla segura en {len(fell_back)}: {' / '.join(fell_back)}" if fell_back else ""
        )

    return {
        "review_ids": review_ids,
        "result": {**state.get("result", {}), "shortlists": len(by_posting)},
    }
