"""H2 de punta a punta: oferta → agente Mercado, joven → agente Perfil, con `agent_trace`.

El LLM está simulado (sin red): `ScriptedLLM` responde según el agente que llama.
"""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from puente_api.config import Settings
from puente_api.db import models
from puente_api.graph import runner
from puente_api.graph.taxonomy import SkillIndex, evidence_in, fold, match_location
from puente_api.llm import LLMClient, get_llm
from puente_api.main import app
from tests.unit.conftest import COMPANY, LOC_A, LOC_B, SK_ATENCION, SK_CAJA, SK_EXCEL

OFERTA = """Se busca Cajero/a medio tiempo en Belisario Porras.
Experiencia como cajero indispensable. Deseable servicio al cliente.
Lunes a viernes de 8:00 a 14:00. Salario B/. 600 a 650. 2 vacantes."""

CV = """Ana Pérez. Ayudé dos años en la tienda de mi tía cobrando en la caja.
Bachiller en comercio."""


class ScriptedLLM:
    """Simula `litellm.completion`: elige la respuesta por el agente (prompt de sistema)."""

    def __init__(self, mercado=None, cv=None, interview=None):
        self.scripts = {"mercado": mercado, "cv": cv, "interview": list(interview or [])}
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs["messages"][0]["content"]
        if "Inteligencia de mercado" in system:
            out = self.scripts["mercado"]
        elif "a partir de su CV" in system:
            out = self.scripts["cv"]
        else:
            out = self.scripts["interview"].pop(0)
        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _llm(fake: ScriptedLLM) -> LLMClient:
    settings = Settings(
        llm_model="fake/modelo",
        llm_model_fast="fake/modelo",
        llm_fallback_model=None,
        llm_api_key=None,
        llm_max_retries=0,
    )
    return LLMClient(settings=settings, completion=fake)


@pytest.fixture
def use_llm():
    def _install(fake: ScriptedLLM) -> ScriptedLLM:
        app.dependency_overrides[get_llm] = lambda: _llm(fake)
        return fake

    return _install


def _trace(client, thread_id):
    res = client.get(f"/api/v1/traces/{thread_id}")
    assert res.status_code == 200
    return res.json()


# --- Mercado -----------------------------------------------------------------


def test_ingest_posting_end_to_end(client, use_llm):
    fake = use_llm(
        ScriptedLLM(
            mercado={
                "title": "Cajero/a medio tiempo",
                "skills": [
                    {"name": "cajero", "weight": 3, "required": True},
                    {"name": "Servicio al cliente", "weight": 1, "required": False},
                    {"name": "Manejo de caja", "weight": 2, "required": True},  # duplicado
                    {"name": "Soldadura submarina", "weight": 3},  # fuera de ESCO-lite
                ],
                "corregimiento": "belisario porras",
                "schedule": [{"day": "lun", "start": "08:00", "end": "14:00"}],
                "salary_min": 650,
                "salary_max": 600,
                "vacancies": 2,
                "flagged_requirements": [],
            }
        )
    )
    res = client.post("/api/v1/postings", data={"companyId": COMPANY, "text": OFERTA})
    assert res.status_code == 202, res.text
    body = res.json()
    thread_id, posting_id = body["threadId"], body["resourceId"]

    # La oferta del usuario va delimitada como datos dentro del prompt.
    user_prompt = fake.calls[0]["messages"][1]["content"]
    assert f"<oferta>\n{OFERTA}\n</oferta>" in user_prompt
    assert "Manejo de caja" in user_prompt  # el catálogo ESCO-lite viaja al LLM

    posting = client.get(f"/api/v1/postings/{posting_id}").json()
    assert posting["title"] == "Cajero/a medio tiempo"
    assert posting["status"] == "publicada"
    assert posting["inputType"] == "texto"
    assert posting["companyId"] == COMPANY
    assert posting["location"]["id"] == LOC_B
    assert posting["schedule"] == [{"day": "lun", "start": "08:00", "end": "14:00"}]
    assert (posting["salaryMin"], posting["salaryMax"]) == (600.0, 650.0)
    assert posting["vacancies"] == 2
    reqs = {r["skill"]["id"]: r for r in posting["requirements"]}
    assert set(reqs) == {SK_CAJA, SK_ATENCION}
    assert reqs[SK_CAJA] | {"skill": None} == {"skill": None, "weight": 3, "required": True}
    assert reqs[SK_ATENCION]["required"] is False
    assert posting["auditFindings"] == []

    trace = _trace(client, thread_id)
    assert trace["status"] == "completado"
    assert [s["agent"] for s in trace["steps"]] == ["supervisor", "mercado"]
    assert [s["step"] for s in trace["steps"]] == [1, 2]
    mercado = trace["steps"][1]
    assert "publicada" in mercado["decision"]
    assert "Soldadura submarina" in mercado["reason"]
    assert mercado["inputSummary"].startswith("texto: Se busca Cajero/a")
    assert mercado["durationMs"] >= 0


def test_discriminatory_posting_is_blocked_with_review_task(client, use_llm, session_factory):
    text = "Cajera para minisúper. Solo mujeres de 18 a 25 años, buena presencia."
    use_llm(
        ScriptedLLM(
            mercado={
                "title": "Cajera",
                "skills": [{"name": "Manejo de caja"}],
                "flagged_requirements": [
                    {"kind": "genero", "text": "Solo mujeres"},
                    {"kind": "edad", "text": "de 18 a 25 años"},
                    {"kind": "estado_civil", "text": "soltera"},  # no está en el texto
                ],
            }
        )
    )
    body = client.post("/api/v1/postings", data={"companyId": COMPANY, "text": text}).json()
    posting = client.get(f"/api/v1/postings/{body['resourceId']}").json()
    assert posting["status"] == "bloqueada"
    assert posting["location"]["id"] == LOC_A  # sin corregimiento: la de la empresa
    [finding] = posting["auditFindings"]
    assert finding["kind"] == "discriminacion"
    assert finding["passed"] is False
    assert finding["variable"] == "genero"
    assert len(finding["findings"]) == 2
    assert not any("soltera" in f for f in finding["findings"])

    with session_factory() as s:
        [task] = s.scalars(select(models.ReviewTask)).all()
    assert task.kind == "bloqueo_oferta"
    assert task.subject_id == posting["id"]
    assert task.graph_thread_id == body["threadId"]
    assert _trace(client, body["threadId"])["status"] == "esperando_revision"


def test_ingest_falls_back_when_llm_output_is_invalid(client, use_llm):
    use_llm(ScriptedLLM(mercado="esto no es JSON"))
    body = client.post("/api/v1/postings", data={"companyId": COMPANY, "text": OFERTA}).json()
    posting = client.get(f"/api/v1/postings/{body['resourceId']}").json()
    assert posting["title"] == "Se busca Cajero/a medio tiempo en Belisario Porras."
    assert posting["requirements"] == []
    assert posting["status"] == "publicada"


def test_ingest_posting_from_text_file(client, use_llm):
    use_llm(ScriptedLLM(mercado={"title": "Cajero/a", "skills": [{"name": "Excel"}]}))
    files = {"file": ("oferta.txt", OFERTA.encode(), "text/plain")}
    body = client.post("/api/v1/postings", data={"companyId": COMPANY}, files=files).json()
    posting = client.get(f"/api/v1/postings/{body['resourceId']}").json()
    assert [r["skill"]["id"] for r in posting["requirements"]] == [SK_EXCEL]


def test_ingest_posting_rejects_bad_input(client, use_llm):
    use_llm(ScriptedLLM())
    url = "/api/v1/postings"
    missing = client.post(url, data={"companyId": COMPANY})
    assert missing.status_code == 422
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert client.post(url, data={"text": OFERTA}).status_code == 422
    assert client.post(url, data={"companyId": "no-existe", "text": OFERTA}).status_code == 422
    photo = client.post(
        url, data={"companyId": COMPANY}, files={"file": ("o.png", b"\x89PNG", "image/png")}
    )
    assert photo.status_code == 422
    assert photo.json()["guardrail"] == "archivo_invalido"
    big = client.post(
        url,
        data={"companyId": COMPANY},
        files={"file": ("o.pdf", b"0" * (5 * 1024 * 1024 + 1), "application/pdf")},
    )
    assert big.status_code == 413


# --- Perfil ------------------------------------------------------------------

YOUTH = {
    "displayName": "Ana",
    "birthYear": 2005,
    "gender": "femenino",
    "locationId": LOC_B,
    "maxCommuteMin": 60,
    "transportBudgetDaily": 3.5,
    "minSalary": 550,
    "studying": False,
    "availability": [{"day": "lun", "start": "08:00", "end": "14:00"}],
}


def test_profile_end_to_end(client, use_llm):
    fake = use_llm(
        ScriptedLLM(
            cv={
                "skills": [
                    {"name": "Manejo de caja", "level": 2, "evidence": "cobrando en la caja"},
                    {"name": "Hojas de cálculo", "level": 3, "evidence": "experta en Excel"},
                ]
            },
            interview=[
                {"skills": [], "next_question": "¿Usas la computadora o el celular para algo?"},
                {
                    "skills": [
                        {"name": "Excel", "level": 1, "evidence": "hago listas en Excel"},
                        {"name": "Atención al cliente", "level": 2, "evidence": "inventado"},
                    ],
                    "next_question": "¿Has atendido clientes?",
                },
                {
                    "skills": [
                        {
                            "name": "Atención al cliente",
                            "level": 2,
                            "evidence": "atendía a los clientes",
                        }
                    ],
                    "next_question": None,
                },
            ],
        )
    )

    created = client.post("/api/v1/youth", json=YOUTH)
    assert created.status_code == 201, created.text
    youth = created.json()
    youth_id = youth["id"]
    assert youth["skills"] == []
    assert youth["isSynthetic"] is False
    assert youth["availability"] == YOUTH["availability"]

    # CV: solo sobrevive la habilidad cuya evidencia es literal.
    cv = client.post(f"/api/v1/youth/{youth_id}/cv", data={"text": CV})
    assert cv.status_code == 202, cv.text
    assert cv.json()["resourceId"] == youth_id
    [skill] = client.get(f"/api/v1/youth/{youth_id}").json()["skills"]
    assert skill["skill"]["id"] == SK_CAJA
    assert (skill["level"], skill["source"]) == (2, "cv")
    assert skill["evidence"] == "cobrando en la caja"
    cv_trace = _trace(client, cv.json()["threadId"])
    assert [s["agent"] for s in cv_trace["steps"]] == ["supervisor", "perfil"]
    assert "Hojas de cálculo (evidencia no literal)" in cv_trace["steps"][1]["reason"]

    # Entrevista: inicio, dos respuestas, cierre con perfil final.
    url = f"/api/v1/youth/{youth_id}/interview"
    first = client.post(url, json={"answer": None}).json()
    assert first == {
        "done": False,
        "question": "¿Usas la computadora o el celular para algo?",
        "index": 1,
        "discoveredSkills": [],
    }
    # Los huecos frente a la demanda (oferta publicada pide Atención al cliente) llegan al LLM.
    assert (
        "Huecos frente a lo que piden las ofertas: Atención al cliente"
        in (fake.calls[-1]["messages"][1]["content"])
    )
    # Reinicio idempotente: repite la pregunta abierta sin llamar al LLM.
    n_calls = len(fake.calls)
    assert client.post(url, json={}).json()["index"] == 1
    assert len(fake.calls) == n_calls

    second = client.post(url, json={"answer": "Sí, hago listas en Excel para la tienda"}).json()
    assert second["done"] is False
    assert second["index"] == 2
    assert [s["skill"]["id"] for s in second["discoveredSkills"]] == [SK_EXCEL]
    assert second["discoveredSkills"][0]["source"] == "entrevista"

    final = client.post(url, json={"answer": "En la tienda atendía a los clientes"}).json()
    assert final["done"] is True
    assert "question" not in final
    assert {s["skill"]["id"] for s in final["discoveredSkills"]} == {
        SK_CAJA,
        SK_EXCEL,
        SK_ATENCION,
    }

    profile = client.get(f"/api/v1/youth/{youth_id}").json()
    by_id = {s["skill"]["id"]: s for s in profile["skills"]}
    assert by_id[SK_ATENCION]["evidence"] == "atendía a los clientes"
    assert by_id[SK_CAJA]["source"] == "cv"

    trace = _trace(client, f"entrevista-{youth_id}")
    assert trace["status"] == "completado"
    assert [s["agent"] for s in trace["steps"]] == ["supervisor", "perfil"] * 4
    assert "entrevista completa" in trace["steps"][-1]["decision"]


def test_interview_minimum_turns_use_fallback_question(client, use_llm):
    # El LLM quiere cerrar de inmediato; el código exige un mínimo de turnos.
    use_llm(ScriptedLLM(interview=["basura", {"skills": [], "next_question": None}]))
    youth_id = client.post("/api/v1/youth", json=YOUTH).json()["id"]
    url = f"/api/v1/youth/{youth_id}/interview"
    first = client.post(url, json={"answer": None}).json()
    assert first["done"] is False and first["question"]
    second = client.post(url, json={"answer": "No sé qué decir"}).json()
    assert second["done"] is False
    assert second["index"] == 2


def test_youth_validation_and_not_found(client, use_llm):
    use_llm(ScriptedLLM())
    bad_year = client.post("/api/v1/youth", json=YOUTH | {"birthYear": 1950})
    assert bad_year.status_code == 422
    assert bad_year.headers["content-type"].startswith("application/problem+json")
    bad_loc = client.post("/api/v1/youth", json=YOUTH | {"locationId": "no-existe"})
    assert bad_loc.status_code == 422
    bad_slot = YOUTH | {"availability": [{"day": "lun", "start": "8am", "end": "14:00"}]}
    assert client.post("/api/v1/youth", json=bad_slot).status_code == 422

    missing = "00000000-0000-0000-0000-999999999999"
    assert client.get(f"/api/v1/youth/{missing}").status_code == 404
    assert client.post(f"/api/v1/youth/{missing}/cv", data={"text": CV}).status_code == 404
    assert client.post(f"/api/v1/youth/{missing}/interview", json={}).status_code == 404

    youth_id = client.post("/api/v1/youth", json=YOUTH).json()["id"]
    assert client.post(f"/api/v1/youth/{youth_id}/cv", data={}).status_code == 422
    no_question = client.post(f"/api/v1/youth/{youth_id}/interview", json={"answer": "hola"})
    assert no_question.status_code == 422
    assert "answer = null" in no_question.json()["detail"]
    assert client.get("/api/v1/traces/no-existe").status_code == 404


# --- Piezas deterministas ----------------------------------------------------


def test_runner_records_error_trace(session_factory):
    with session_factory() as s:
        with pytest.raises(ValueError):
            runner.run(s, _llm(ScriptedLLM()), "profile.cv", {"youth_id": "x", "text": "t"}, "t-1")
        rows = s.scalars(select(models.AgentTrace).where(models.AgentTrace.thread_id == "t-1"))
        rows = sorted(rows, key=lambda r: int(r.step))
    assert [(r.agent, r.decision) for r in rows] == [("perfil", "error")]
    assert "no existe" in rows[0].reason


def test_taxonomy_helpers(session_factory):
    assert fold("  Atención   al Cliente! ") == "atencion al cliente"
    assert evidence_in("cobrando en la CAJA", CV)
    assert not evidence_in("", CV)
    with session_factory() as s:
        index = SkillIndex.load(s)
        assert index.match("servicio al cliente").id == SK_ATENCION
        assert index.match("Atencion al clientes").id == SK_ATENCION  # difuso
        assert index.match("excel").id == SK_EXCEL
        assert index.match("Piloto de avión") is None
        assert match_location(s, "Bella vista").id == LOC_A
        assert match_location(s, "Marte") is None
        assert match_location(s, None) is None
