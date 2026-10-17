"""H3: corrida completa Matching → Auditor → Postulación, pausa HITL y reanudación.

El LLM está simulado y el auditor se sustituye por un stub controlable cuando hace falta.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from puente_api.config import Settings
from puente_api.db import models
from puente_api.graph import audit_port, runner
from puente_api.graph.audit_port import AuditFinding
from puente_api.graph.scheduling import assign_interview_slots, next_business_day
from puente_api.llm import LLMClient, get_llm
from puente_api.main import app
from tests.unit.conftest import COMPANY, LOC_A, POST_OK, SK_CAJA

Y1, Y2 = "00000000-0000-0000-0004-000000000001", "00000000-0000-0000-0004-000000000002"
API = "/api/v1"


class PostulacionLLM:
    """Responde al agente de Postulación; `bad` fuerza un borrador con una habilidad ajena."""

    def __init__(self, bad: bool = False):
        self.bad = bad
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        extra = " Domino Excel avanzado." if self.bad else ""
        out = {
            "tailored_cv": "Resumen: cajera con práctica en comercio."
            + extra
            + " Habilidades: Manejo de caja.",
            "cover_letter": "Me postulo con gusto; tengo práctica en Manejo de caja.",
            "explanation": "Cubre la habilidad de caja y el traslado es corto.",
            "skills_used": ["Manejo de caja"],
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(out)))]
        )


@pytest.fixture
def use_llm():
    def _install(fake) -> None:
        settings = Settings(
            llm_model="fake/m", llm_model_fast="fake/m", llm_fallback_model=None, llm_max_retries=0
        )
        app.dependency_overrides[get_llm] = lambda: LLMClient(settings=settings, completion=fake)

    return _install


@pytest.fixture
def seeded(session_factory):
    with session_factory() as s:
        s.add_all(
            [
                models.CommuteMatrix(
                    origin_id=LOC_A, dest_id=LOC_A, minutes=10, cost_daily=0.5, mode="bus"
                ),
            ]
        )
        for yid, name in ((Y1, "Ana"), (Y2, "Beatriz")):
            s.add(
                models.Youth(
                    id=yid,
                    display_name=name,
                    birth_year=2003,
                    location_id=LOC_A,
                    max_commute_min=60,
                    transport_budget_daily=5,
                    availability=[{"day": "lun", "start": "07:00", "end": "17:00"}],
                    skills=[
                        models.ProfileSkill(
                            skill_id=SK_CAJA, level=2, source="cv", evidence="cobraba en la caja"
                        )
                    ],
                )
            )
        s.commit()


def _no_bias(monkeypatch, failing: bool = False):
    def fake(_inp, _res, _attrs):
        return [
            AuditFinding(
                variable="genero",
                parity=0.4 if failing else 1.0,
                passed=not failing,
                findings=["paridad baja por género"] if failing else [],
            )
        ]

    monkeypatch.setattr(audit_port, "_load_impl", lambda: fake)


def _start(client):
    res = client.post(f"{API}/match-runs", json={"timeLimitSeconds": 2})
    assert res.status_code == 202, res.text
    return res.json()


def _agents(client, thread):
    return [s["agent"] for s in client.get(f"{API}/traces/{thread}").json()["steps"]]


def test_full_run_pauses_and_resumes_after_approval(client, use_llm, seeded, monkeypatch):
    _no_bias(monkeypatch)
    llm = PostulacionLLM()
    use_llm(llm)
    body = _start(client)
    thread, run_id = body["threadId"], body["resourceId"]

    # Pausado en la revisión humana.
    trace = client.get(f"{API}/traces/{thread}").json()
    assert trace["status"] == "esperando_revision"
    assert _agents(client, thread) == [
        "supervisor",
        "matching",
        "auditor",
        "postulacion",
        "orientador",  # fila de pausa HITL
    ]
    assert trace["steps"][-1]["kind"] == "pausa_hitl"
    assert llm.calls == 2

    run = client.get(f"{API}/match-runs/{run_id}").json()
    assert run["threadId"] == thread
    assert len(run["results"]) == 2
    assert {r["status"] for r in run["results"]} == {"propuesto"}
    assert run["results"][0]["explanation"]
    assert run["audit"][0]["variable"] == "genero"

    [review] = client.get(f"{API}/reviews", params={"status": "pendiente"}).json()
    assert review["kind"] == "lista_corta"
    assert review["agent"] == "postulacion"
    assert review["threadId"] == thread
    cands = review["proposal"]["postings"][0]["candidates"]
    assert len(cands) == 2
    assert client.get(f"{API}/postings/{POST_OK}/shortlist").json() == []

    # El orientador quita a una candidata y el grafo se reanuda.
    drop = cands[1]["matchResultId"]
    res = client.post(
        f"{API}/reviews/{review['id']}/decision",
        json={"decision": "editar", "reviewer": "Marta", "edits": {"remove": [drop]}},
    )
    assert res.status_code == 202
    assert res.json()["threadId"] == thread

    trace = client.get(f"{API}/traces/{thread}").json()
    assert trace["status"] == "completado"
    assert _agents(client, thread)[-1] == "orientador"
    assert "Marta" in trace["steps"][-1]["decision"]

    shortlist = client.get(f"{API}/postings/{POST_OK}/shortlist").json()
    assert len(shortlist) == 1
    assert shortlist[0]["status"] == "enviada"
    assert shortlist[0]["matchResult"]["status"] == "aprobado"
    assert shortlist[0]["interviewSlots"]
    assert "Manejo de caja" in shortlist[0]["tailoredCv"]
    statuses = {r["status"] for r in client.get(f"{API}/match-runs/{run_id}").json()["results"]}
    assert statuses == {"aprobado", "rechazado"}
    approved_youth = shortlist[0]["matchResult"]["youthId"]
    assert client.get(f"{API}/youth/{approved_youth}/matches", params={"status": "aprobado"}).json()

    done = client.get(f"{API}/reviews/", params={"status": "editada"}).json()
    assert done[0]["reviewer"] == "Marta"
    # Decidir dos veces: 409.
    again = client.post(
        f"{API}/reviews/{review['id']}/decision", json={"decision": "aprobar", "reviewer": "M"}
    )
    assert again.status_code == 409


def test_reject_shortlist_discards_everything(
    client, use_llm, seeded, monkeypatch, session_factory
):
    _no_bias(monkeypatch)
    use_llm(PostulacionLLM())
    _start(client)
    [review] = client.get(f"{API}/reviews").json()
    client.post(
        f"{API}/reviews/{review['id']}/decision", json={"decision": "rechazar", "reviewer": "M"}
    )
    with session_factory() as s:
        apps = s.scalars(select(models.Application)).all()
        assert {a.status for a in apps} == {"descartada"}
        assert s.scalars(select(models.InterviewSlot)).all() == []


def test_unverifiable_draft_falls_back_to_safe_template(client, use_llm, seeded, monkeypatch):
    _no_bias(monkeypatch)
    use_llm(PostulacionLLM(bad=True))
    body = _start(client)
    [review] = client.get(f"{API}/reviews").json()
    steps = client.get(f"{API}/traces/{body['threadId']}").json()["steps"]
    assert "plantilla segura" in next(s for s in steps if s["agent"] == "postulacion")["reason"]
    client.post(
        f"{API}/reviews/{review['id']}/decision", json={"decision": "aprobar", "reviewer": "M"}
    )
    for item in client.get(f"{API}/postings/{POST_OK}/shortlist").json():
        assert "Excel" not in item["tailoredCv"]


def test_bias_alert_gates_resume_and_holds_shortlist(client, use_llm, seeded, monkeypatch):
    _no_bias(monkeypatch, failing=True)
    use_llm(PostulacionLLM())
    body = _start(client)
    reviews = {r["kind"]: r for r in client.get(f"{API}/reviews").json()}
    assert set(reviews) == {"alerta_sesgo", "lista_corta"}

    # Descartar una alerta exige justificación.
    bad = client.post(
        f"{API}/reviews/{reviews['alerta_sesgo']['id']}/decision",
        json={"decision": "rechazar", "reviewer": "M"},
    )
    assert bad.status_code == 422

    # Aceptar la alerta no reanuda mientras la lista siga pendiente.
    client.post(
        f"{API}/reviews/{reviews['alerta_sesgo']['id']}/decision",
        json={"decision": "aprobar", "reviewer": "M"},
    )
    assert client.get(f"{API}/traces/{body['threadId']}").json()["status"] == "esperando_revision"
    client.post(
        f"{API}/reviews/{reviews['lista_corta']['id']}/decision",
        json={"decision": "aprobar", "reviewer": "M"},
    )
    trace = client.get(f"{API}/traces/{body['threadId']}").json()
    assert trace["status"] == "completado"
    decided = [s for s in trace["steps"] if s["kind"] == "decision_humana"]
    assert len(decided) == 2
    # Con el sesgo aceptado la lista queda retenida.
    assert client.get(f"{API}/postings/{POST_OK}/shortlist").json() == []


def test_blocked_posting_pauses_and_can_be_released(client, use_llm, session_factory):
    mercado = {
        "title": "Cajera",
        "skills": [{"name": "Manejo de caja"}],
        "flagged_requirements": [{"kind": "genero", "text": "Solo mujeres"}],
    }

    def fake(**_kw):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(mercado)))]
        )

    use_llm(fake)
    body = client.post(
        f"{API}/postings", data={"companyId": COMPANY, "text": "Cajera. Solo mujeres."}
    ).json()
    posting = body["resourceId"]
    assert client.get(f"{API}/postings/{posting}").json()["status"] == "bloqueada"
    [review] = client.get(f"{API}/reviews").json()
    assert review["kind"] == "bloqueo_oferta"

    # editar sin cambios válidos: 422
    assert (
        client.post(
            f"{API}/reviews/{review['id']}/decision",
            json={"decision": "editar", "reviewer": "M", "edits": {"x": 1}},
        ).status_code
        == 422
    )
    client.post(
        f"{API}/reviews/{review['id']}/decision",
        json={"decision": "rechazar", "reviewer": "M", "comment": "falso positivo"},
    )
    assert client.get(f"{API}/postings/{posting}").json()["status"] == "publicada"
    trace = client.get(f"{API}/traces/{body['threadId']}").json()
    assert trace["status"] == "completado"
    assert trace["steps"][-1]["agent"] == "orientador"


def test_decision_errors(client, use_llm, seeded):
    assert (
        client.post(
            f"{API}/reviews/no-existe/decision", json={"decision": "aprobar", "reviewer": "M"}
        ).status_code
        == 404
    )
    assert client.get(f"{API}/match-runs/no-existe").status_code == 404


def test_resume_survives_a_fresh_session(client, use_llm, seeded, monkeypatch, session_factory):
    """La pausa vive en el checkpointer: otra sesión de BD puede reanudar el hilo."""
    _no_bias(monkeypatch)
    use_llm(PostulacionLLM())
    body = _start(client)
    assert runner.is_paused(body["threadId"])
    [review] = client.get(f"{API}/reviews").json()
    client.post(
        f"{API}/reviews/{review['id']}/decision", json={"decision": "aprobar", "reviewer": "M"}
    )
    assert not runner.is_paused(body["threadId"])
    with session_factory() as s:
        assert s.get(models.ReviewTask, review["id"]).status == "aprobada"


def test_interview_slots_never_overlap():
    start = next_business_day(datetime(2026, 10, 16, 15, 0))  # viernes → lunes
    assert start.weekday() == 0 and start.hour == 9
    slots = assign_interview_slots([f"c{i}" for i in range(20)], start)
    ordered = sorted(slots.values())
    for (_, end), (nxt_start, _) in zip(ordered, ordered[1:], strict=False):
        assert end <= nxt_start
    assert all(s.weekday() < 5 for s, _ in ordered)
    assert slots["c0"][0] == start
    assert slots["c8"][0] - start >= timedelta(hours=20)


def test_real_auditor_checks_each_protected_variable(client, use_llm, seeded):
    use_llm(PostulacionLLM())
    body = _start(client)
    auditor = client.get(f"{API}/traces/{body['threadId']}").json()["steps"][2]
    assert auditor["agent"] == "auditor"
    assert "STUB" not in auditor["reason"]
    for variable in ("nombre", "genero", "corregimiento"):
        assert variable in auditor["reason"]


def test_auditor_stub_is_flagged_in_trace(client, use_llm, seeded, monkeypatch):
    monkeypatch.setattr(audit_port, "_load_impl", lambda: None)
    use_llm(PostulacionLLM())
    body = _start(client)
    auditor = client.get(f"{API}/traces/{body['threadId']}").json()["steps"][2]
    assert auditor["agent"] == "auditor"
    assert "STUB" in auditor["reason"]
