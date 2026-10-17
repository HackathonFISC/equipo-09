"""Eval con LLM real (opcional): F1 de extracción de habilidades en ofertas y CVs del seed.

No corre en `pnpm --filter api evals` (que es determinista y sin red). Se ejecuta a mano con un
proveedor configurado en `.env`; con `LLM_CACHE_DIR` la segunda corrida no gasta llamadas:

    cd apps/api
    LLM_CACHE_DIR=.llm-cache uv run python -m tests.evals.llm_extraction            # todo
    LLM_CACHE_DIR=.llm-cache uv run python -m tests.evals.llm_extraction --limit 5  # prueba

Usa los mismos prompts, esquemas y normalización a ESCO-lite que los agentes Mercado y Perfil, y
escribe `results-llm.md` (que `report.py` lee para la tabla del PRD).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from puente_api.config import get_settings
from puente_api.db import models
from puente_api.db.seed.loaders import read_seed_bundle, seed_database, seed_uuid
from puente_api.db.seed.schemas import SeedBundle
from puente_api.graph.nodes.mercado import PostingExtraction
from puente_api.graph.nodes.perfil import CvExtraction
from puente_api.graph.taxonomy import SkillIndex, evidence_in
from puente_api.guardrails import screen_text
from puente_api.llm import LLMClient
from puente_api.llm.prompts import MERCADO_SYSTEM, MERCADO_USER, PERFIL_CV_SYSTEM, PERFIL_CV_USER

OUT = Path(__file__).parent / "results-llm.md"


@dataclass
class Row:
    key: str
    gold: set[str]
    pred: set[str]

    @property
    def tp(self) -> int:
        return len(self.gold & self.pred)


@dataclass
class Score:
    rows: list[Row] = field(default_factory=list)
    no_answer: int = 0  # el LLM no respondió y se usó el valor por defecto

    def micro(self) -> tuple[float, float, float]:
        tp = sum(r.tp for r in self.rows)
        n_pred = sum(len(r.pred) for r in self.rows)
        n_gold = sum(len(r.gold) for r in self.rows)
        p = tp / n_pred if n_pred else 0.0
        r = tp / n_gold if n_gold else 0.0
        return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def seeded_session() -> Session:
    """BD SQLite en memoria con los seeds (solo se leen skills y corregimientos)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_database(session)
    session.commit()
    return session


def _used_default(llm: LLMClient, mark: int) -> bool:
    return any(c.model.startswith("(") for c in llm.call_log[mark:])


def eval_postings(llm: LLMClient, session: Session, bundle: SeedBundle, limit: int | None) -> Score:
    index = SkillIndex.load(session)
    locations = "; ".join(sorted(session.scalars(select(models.Location.corregimiento))))
    score = Score()
    for posting in bundle.postings[:limit]:
        text = screen_text(posting.raw_input, source="posting").sanitized
        mark = len(llm.call_log)
        out = llm.structured(
            MERCADO_USER.format(skills="; ".join(index.labels), locations=locations, text=text),
            PostingExtraction,
            system=MERCADO_SYSTEM,
            default=PostingExtraction(title="(sin respuesta)"),
        )
        if _used_default(llm, mark):
            score.no_answer += 1
        pred = {s.id for req in out.skills if (s := index.match(req.name))}
        gold = {str(seed_uuid("skill", r.skill)) for r in posting.requirements}
        score.rows.append(Row(posting.key, gold, pred))
    return score


def eval_profiles(
    llm: LLMClient, session: Session, bundle: SeedBundle, limit: int | None
) -> tuple[Score, int, int]:
    """F1 sobre los jóvenes con CV, y cuántas habilidades propuestas traían evidencia literal."""
    index = SkillIndex.load(session)
    score = Score()
    proposed = with_evidence = 0
    for youth in [y for y in bundle.youth if y.cv_raw_text][:limit]:
        text = screen_text(youth.cv_raw_text or "", source="cv").sanitized
        mark = len(llm.call_log)
        out = llm.structured(
            PERFIL_CV_USER.format(skills="; ".join(index.labels), text=text),
            CvExtraction,
            system=PERFIL_CV_SYSTEM,
            default=CvExtraction(),
        )
        if _used_default(llm, mark):
            score.no_answer += 1
        pred: set[str] = set()
        for item in out.skills:
            proposed += 1
            if not evidence_in(item.evidence, text):
                continue  # el agente real la descarta: sin evidencia no cuenta
            with_evidence += 1
            if skill := index.match(item.name):
                pred.add(skill.id)
        # Esperadas: solo las habilidades cuya evidencia está en el CV (otras vienen de la
        # entrevista y el CV no las menciona).
        gold = {
            str(seed_uuid("skill", s.skill))
            for s in youth.skills
            if evidence_in(s.evidence, youth.cv_raw_text or "")
        }
        score.rows.append(Row(youth.key, gold, pred))
    return score, proposed, with_evidence


def render(model: str, postings: Score, profiles: Score, proposed: int, evid: int) -> str:
    pp, pr, pf = postings.micro()
    yp, yr, yf = profiles.micro()
    evidence_rate = evid / proposed if proposed else 0.0
    lines = [
        "# Resultados de evals con LLM",
        "",
        f"Generado con `uv run python -m tests.evals.llm_extraction` el "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC con el modelo `{model}`. No editar a mano.",
        "",
        "Métrica: precisión, recall y F1 micro de las habilidades ESCO-lite extraídas frente a "
        "las etiquetadas en el seed (requisitos de cada oferta; habilidades de cada joven).",
        "",
        "| Grupo | Casos | Precisión | Recall | F1 | Meta | Sin respuesta del LLM |",
        "|---|---:|---:|---:|---:|---|---:|",
        f"| Ofertas (agente Mercado) | {len(postings.rows)} | {pp:.2f} | {pr:.2f} | {pf:.2f} "
        f"| F1 ≥ 0.80 | {postings.no_answer} |",
        f"| CVs (agente Perfil) | {len(profiles.rows)} | {yp:.2f} | {yr:.2f} | {yf:.2f} "
        f"| F1 ≥ 0.80 | {profiles.no_answer} |",
        "",
        f"Habilidades propuestas por Perfil con evidencia literal: {evid}/{proposed} "
        f"({100 * evidence_rate:.0f} %). Las que no la traen se descartan por código.",
        "",
        "## Detalle (ofertas)",
        "",
        "| Oferta | Esperadas | Extraídas | Aciertos |",
        "|---|---:|---:|---:|",
        *[f"| `{r.key}` | {len(r.gold)} | {len(r.pred)} | {r.tp} |" for r in postings.rows],
        "",
        # Líneas que lee `prd_metrics.llm_metric` (no cambiar el formato).
        f"F1_OFERTAS={pf:.4f}",
        f"F1_PERFILES={yf:.4f}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="máximo de casos por grupo")
    args = parser.parse_args(argv)

    # Sin presupuesto de tiempo (es una corrida larga) pero con circuito: si el proveedor cae,
    # no se insiste durante 50 casos.
    settings = get_settings().model_copy(update={"llm_budget_s": 0, "llm_circuit_failures": 3})
    llm = LLMClient(settings)
    session = seeded_session()
    bundle = read_seed_bundle()
    postings = eval_postings(llm, session, bundle, args.limit)
    profiles, proposed, evid = eval_profiles(llm, session, bundle, args.limit)
    OUT.write_text(render(settings.llm_model, postings, profiles, proposed, evid), encoding="utf-8")
    total = len(postings.rows) + len(profiles.rows)
    missing = postings.no_answer + profiles.no_answer
    print(f"F1 ofertas={postings.micro()[2]:.2f} perfiles={profiles.micro()[2]:.2f} -> {OUT}")
    if missing:
        print(
            f"ATENCIÓN: {missing}/{total} casos sin respuesta del LLM; revisa la clave y el modelo"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
