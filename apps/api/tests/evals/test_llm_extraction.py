"""El eval con LLM calcula bien sus métricas (con un LLM simulado: sin red)."""

import json
from types import SimpleNamespace

from puente_api.config import Settings
from puente_api.db.seed.loaders import read_seed_bundle
from puente_api.llm import LLMClient
from tests.evals.llm_extraction import eval_postings, eval_profiles, render, seeded_session

BUNDLE = read_seed_bundle()
LABELS = {s.key: s.label_es for s in BUNDLE.skills}


class OracleLLM:
    """Responde con las etiquetas correctas del seed (o vacío si `perfect=False`)."""

    def __init__(self, perfect: bool):
        self.perfect = perfect

    def __call__(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        out: dict = {"title": "x", "skills": []}
        if self.perfect:
            for p in BUNDLE.postings:
                if p.raw_input[:40] in prompt:
                    out["skills"] = [{"name": LABELS[r.skill]} for r in p.requirements]
            for y in BUNDLE.youth:
                if y.cv_raw_text and y.cv_raw_text[:40] in prompt:
                    out["skills"] = [
                        {"name": LABELS[s.skill], "evidence": s.evidence}
                        for s in y.skills
                        if s.evidence in y.cv_raw_text
                    ]
        msg = SimpleNamespace(content=json.dumps(out, ensure_ascii=False))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _llm(perfect: bool) -> LLMClient:
    settings = Settings(_env_file=None, llm_model="fake/m", llm_model_fast="fake/m")
    return LLMClient(settings, completion=OracleLLM(perfect))


def test_perfect_extraction_scores_f1_one_and_empty_scores_zero():
    session = seeded_session()
    perfect = eval_postings(_llm(True), session, BUNDLE, limit=5)
    assert perfect.micro()[2] == 1.0
    empty = eval_postings(_llm(False), session, BUNDLE, limit=5)
    assert empty.micro() == (0.0, 0.0, 0.0)


def test_profiles_require_literal_evidence_and_render_machine_lines():
    session = seeded_session()
    profiles, proposed, with_evidence = eval_profiles(_llm(True), session, BUNDLE, limit=3)
    assert profiles.micro()[2] == 1.0
    assert proposed == with_evidence > 0
    postings = eval_postings(_llm(True), session, BUNDLE, limit=2)
    md = render("fake/m", postings, profiles, proposed, with_evidence)
    assert "F1_OFERTAS=1.0000" in md and "F1_PERFILES=1.0000" in md
