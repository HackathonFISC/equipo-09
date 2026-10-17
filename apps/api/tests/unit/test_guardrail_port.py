"""Puerto de guardrails: stub tolerante, saneado, bloqueo (422 + traza) y falla cerrada."""

# ruff: noqa: F811  (los fixtures importados se usan como argumentos)

import types

import pytest
from sqlalchemy import select

from puente_api.db import models
from puente_api.graph import guardrail_port
from puente_api.graph.guardrail_port import GuardrailBlocked, GuardrailResult
from tests.unit.conftest import COMPANY
from tests.unit.test_agents_h2 import CV, OFERTA, YOUTH, ScriptedLLM, use_llm  # noqa: F401

API = "/api/v1"
MERCADO_OK = {"title": "Cajero/a", "skills": [{"name": "Manejo de caja"}]}


def _install(monkeypatch, impl):
    monkeypatch.setattr(guardrail_port, "_load_impl", lambda: impl)


def _steps(client, thread_id):
    return client.get(f"{API}/traces/{thread_id}").json()["steps"]


# --- Adaptador -----------------------------------------------------------------------------


def test_stub_lets_text_through_and_is_detectable(monkeypatch):
    _install(monkeypatch, None)
    assert guardrail_port.is_stub()
    result = guardrail_port.screen_text("hola")
    assert result.allowed and result.sanitized == "hola"
    assert result.reasons == [guardrail_port.STUB_NOTICE]


def test_real_package_without_screen_text_falls_back_to_stub():
    # Hoy `puente_api.guardrails` no exporta `screen_text`: debe seguir funcionando.
    if hasattr(__import__("puente_api.guardrails", fromlist=["x"]), "screen_text"):
        pytest.skip("Sebastian ya implementó screen_text")
    assert guardrail_port.is_stub()


def test_accepts_objects_and_dicts(monkeypatch):
    obj = types.SimpleNamespace(allowed=False, sanitized="x", reasons=["pii: cédula"])
    _install(monkeypatch, lambda _t: obj)
    assert guardrail_port.screen_text("a") == GuardrailResult(
        allowed=False, sanitized="x", reasons=["pii: cédula"]
    )
    _install(monkeypatch, lambda _t: {"allowed": True, "sanitized": "limpio"})
    assert guardrail_port.screen_text("sucio") == GuardrailResult(sanitized="limpio")
    _install(monkeypatch, lambda t: {"reasons": ["nota"]})
    assert guardrail_port.screen_text("t").sanitized == "t"  # sin `sanitized` se conserva


def test_broken_guardrail_fails_closed(monkeypatch):
    def boom(_text):
        raise RuntimeError("regex roto")

    _install(monkeypatch, boom)
    result = guardrail_port.screen_text("hola")
    assert result.allowed is False and "RuntimeError" in result.reasons[0]


@pytest.mark.parametrize(
    ("reasons", "code"),
    [
        (["inyeccion: ignora tus instrucciones"], "inyeccion"),
        (["Se detectó una cédula"], "pii"),
        (["intento de inyección de prompt"], "inyeccion"),
        (["algo raro"], "fuera_de_alcance"),
        (["dato_absurdo: 9999 vacantes"], "dato_absurdo"),
    ],
)
def test_block_code_for_the_problem_response(reasons, code):
    assert GuardrailBlocked("mercado", "oferta", reasons).code == code


def test_clean_text_leaves_no_trace(session_factory, monkeypatch):
    _install(monkeypatch, lambda t: GuardrailResult(sanitized=t))
    with session_factory() as session:
        assert guardrail_port.screen_input(session, "t", "perfil", "hola", "CV") == "hola"
        assert session.scalars(select(models.AgentTrace)).all() == []


# --- Conectado al grafo ----------------------------------------------------------------


def test_sanitized_offer_reaches_the_llm_and_leaves_a_guardrail_row(
    client,
    use_llm,
    monkeypatch,
    session_factory,
):
    fake = use_llm(ScriptedLLM(mercado=MERCADO_OK))
    _install(
        monkeypatch,
        lambda t: GuardrailResult(
            sanitized=t.replace("Experiencia como cajero indispensable.", "[quitado]"),
            reasons=["inyeccion: texto con formato de instrucción"],
        ),
    )
    res = client.post(f"{API}/postings", data={"companyId": COMPANY, "text": OFERTA})
    assert res.status_code == 202, res.text

    prompt = fake.calls[0]["messages"][1]["content"]
    assert "[quitado]" in prompt and "indispensable" not in prompt
    steps = _steps(client, res.json()["threadId"])
    assert [(s["agent"], s["kind"]) for s in steps] == [
        ("supervisor", "paso"),
        ("mercado", "guardrail"),
        ("mercado", "paso"),
    ]
    row = steps[1]
    assert row["tool"] == "guardrails.screen_text" and row["decision"] == "saneado: oferta"
    assert "inyeccion" in row["reason"]
    # La oferta original se conserva para auditoría; el LLM solo vio la saneada.
    with session_factory() as session:
        posting = session.get(models.JobPosting, res.json()["resourceId"])
        assert posting.raw_input == OFERTA and posting.status == "publicada"


def test_blocked_offer_returns_422_without_calling_the_llm(
    client, use_llm, monkeypatch, session_factory
):
    fake = use_llm(ScriptedLLM(mercado=MERCADO_OK))
    _install(
        monkeypatch,
        lambda _t: GuardrailResult(allowed=False, sanitized="", reasons=["inyeccion: ignora todo"]),
    )
    before = len(client.get(f"{API}/postings").json())
    res = client.post(f"{API}/postings", data={"companyId": COMPANY, "text": OFERTA})

    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["guardrail"] == "inyeccion"
    assert fake.calls == []
    assert len(client.get(f"{API}/postings").json()) == before

    [summary] = client.get(f"{API}/traces").json()
    assert summary["status"] == "error"
    steps = _steps(client, summary["threadId"])
    # La transacción se revirtió (como en todo error): solo queda la fila del bloqueo.
    assert [(s["agent"], s["kind"], s["decision"]) for s in steps] == [
        ("mercado", "guardrail", "bloqueado: oferta"),
    ]
    assert steps[-1]["reason"] == "inyeccion: ignora todo"


def test_cv_and_interview_answer_are_screened(client, use_llm, monkeypatch):
    seen: list[str] = []

    def spy(text):
        seen.append(text)
        return GuardrailResult(sanitized=text)

    _install(monkeypatch, spy)
    use_llm(ScriptedLLM(cv={"skills": []}, interview=[{"skills": [], "next_question": "¿Otra?"}]))
    youth_id = client.post(f"{API}/youth", json=YOUTH).json()["id"]
    assert client.post(f"{API}/youth/{youth_id}/cv", data={"text": CV}).status_code == 202
    url = f"{API}/youth/{youth_id}/interview"
    assert client.post(url, json={"answer": None}).status_code == 200  # abrir: nada que revisar
    assert seen == [CV]

    _install(
        monkeypatch,
        lambda _t: GuardrailResult(allowed=False, sanitized="", reasons=["pii: número de cédula"]),
    )
    res = client.post(url, json={"answer": "mi cédula es 8-123-456"})
    assert res.status_code == 422 and res.json()["guardrail"] == "pii"
    # La respuesta bloqueada no se guardó: la pregunta sigue abierta.
    assert client.post(url, json={"answer": None}).json()["question"] == "¿Otra?"
