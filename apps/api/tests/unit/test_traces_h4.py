"""H4: línea de tiempo enriquecida, listado de hilos, Langfuse opcional y migración de columnas."""

import json
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text

from puente_api.config import Settings
from puente_api.db.session import init_db
from puente_api.llm import LLMClient, observability
from puente_api.tracing import record_trace, traced
from tests.unit.test_hitl_h3 import (  # noqa: F401  (fixtures)
    API,
    PostulacionLLM,
    _no_bias,
    _start,
    seeded,
    use_llm,
)


def _trace(client, thread):
    res = client.get(f"{API}/traces/{thread}")
    assert res.status_code == 200, res.text
    return res.json()


# --- /traces/{threadId} enriquecido --------------------------------------------------------


def test_trace_describes_each_node_and_the_hitl_pause(client, use_llm, seeded, monkeypatch):  # noqa: F811
    _no_bias(monkeypatch)
    use_llm(PostulacionLLM())
    thread = _start(client)["threadId"]

    trace = _trace(client, thread)
    by_agent = {s["agent"]: s for s in trace["steps"]}
    assert by_agent["supervisor"]["tool"] == "reglas fijas"
    assert by_agent["matching"]["tool"] == "OR-Tools CP-SAT"
    assert by_agent["matching"]["outputSummary"].startswith("corrida ")
    assert by_agent["auditor"]["tool"].startswith("auditor contrafactual")
    assert by_agent["postulacion"]["tool"].startswith("verificador de habilidades + llm: fake/")
    assert all(s["durationMs"] is not None and s["decision"] for s in trace["steps"])
    assert [s["step"] for s in trace["steps"]] == list(range(1, len(trace["steps"]) + 1))

    last = trace["steps"][-1]
    assert last["kind"] == "pausa_hitl" and last["agent"] == "orientador"
    assert trace["status"] == "esperando_revision"
    assert len(trace["pendingReviewIds"]) == 1
    assert trace["totalDurationMs"] >= 0

    review_id = trace["pendingReviewIds"][0]
    res = client.post(
        f"{API}/reviews/{review_id}/decision", json={"decision": "aprobar", "reviewer": "Marta"}
    )
    assert res.status_code == 202, res.text
    done = _trace(client, thread)
    assert done["status"] == "completado" and done["pendingReviewIds"] == []
    # La pausa no se duplica al reanudar (el nodo se vuelve a ejecutar desde el inicio).
    assert [s["kind"] for s in done["steps"]].count("pausa_hitl") == 1
    human = done["steps"][-1]
    assert human["kind"] == "decision_humana" and "Marta" in human["decision"]
    assert human["tool"] == "revisión humana (HITL)"


def test_listing_threads_with_status_filter(client, use_llm, seeded, monkeypatch):  # noqa: F811
    _no_bias(monkeypatch)
    use_llm(PostulacionLLM())
    thread = _start(client)["threadId"]

    rows = client.get(f"{API}/traces").json()
    assert [r["threadId"] for r in rows] == [thread]
    row = rows[0]
    assert row["status"] == "esperando_revision"
    assert row["agents"] == ["supervisor", "matching", "auditor", "postulacion", "orientador"]
    assert row["stepCount"] == 5 and row["lastDecision"].startswith("pausa")

    assert client.get(f"{API}/traces", params={"status": "completado"}).json() == []
    waiting = client.get(f"{API}/traces", params={"status": "esperando_revision", "limit": 1})
    assert [r["threadId"] for r in waiting.json()] == [thread]
    assert client.get(f"{API}/traces", params={"limit": 0}).status_code == 422


def test_listing_is_empty_without_threads(client):
    assert client.get(f"{API}/traces").json() == []


def test_unknown_thread_is_404(client):
    assert client.get(f"{API}/traces/no-existe").status_code == 404


# --- LLMClient: registro de llamadas -------------------------------------------------------


class _Out:
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    def __call__(self, **_kwargs):
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=out))],
            usage=SimpleNamespace(total_tokens=42),
        )


def _llm(*outputs, **overrides):
    settings = Settings(
        _env_file=None,
        llm_model="fake/principal",
        llm_model_fast="fake/principal",
        llm_max_retries=0,
        **overrides,
    )
    return LLMClient(settings, completion=_Out(*outputs))


def test_traced_records_model_tokens_and_degradation(session_factory):
    from pydantic import BaseModel

    class Out(BaseModel):
        ok: bool

    llm = _llm(json.dumps({"ok": True}), "no es json")
    with session_factory() as session:
        with traced(session, "t-llm", "mercado", llm):
            llm.structured("a", Out)
        with traced(session, "t-llm", "mercado", llm):
            assert llm.structured("b", Out, default=Out(ok=False)) == Out(ok=False)
        first, second = _rows(session, "t-llm")
    assert first.tool.startswith("llm: fake/principal (1 llamada(s)")
    assert first.tool.endswith("42 tokens)")
    assert first.reason is None
    assert "valor por defecto seguro" in second.reason


def _rows(session, thread_id):
    from sqlalchemy import select

    from puente_api.db import models

    rows = session.scalars(
        select(models.AgentTrace).where(models.AgentTrace.thread_id == thread_id)
    ).all()
    return sorted(rows, key=lambda r: int(r.step))


def test_record_trace_rejects_unknown_agent(session_factory):
    with session_factory() as session, pytest.raises(ValueError):
        record_trace(session, "t", "desconocido")


# --- Langfuse opcional ---------------------------------------------------------------------


@pytest.fixture
def clean_langfuse(monkeypatch):
    import litellm

    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(litellm, "success_callback", [])
    monkeypatch.setattr(litellm, "failure_callback", [])
    monkeypatch.setattr(litellm, "turn_off_message_logging", False)
    observability.reset_for_tests()
    yield litellm
    observability.reset_for_tests()


def _settings(**kw):
    return Settings(_env_file=None, **kw)


def test_langfuse_is_off_without_keys(clean_langfuse):
    assert observability.ensure_configured(_settings()) is False
    assert clean_langfuse.success_callback == []
    assert observability.langfuse_metadata() == {}


@pytest.mark.parametrize("public,secret", [("pk-lf-changeme", "sk-lf-changeme"), ("pk-lf-1", None)])
def test_langfuse_ignores_placeholder_or_partial_keys(clean_langfuse, public, secret):
    settings = _settings(langfuse_public_key=public, langfuse_secret_key=secret)
    assert observability.ensure_configured(settings) is False
    assert clean_langfuse.success_callback == []


def test_langfuse_needs_the_package(clean_langfuse, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda _name: None)
    settings = _settings(langfuse_public_key="pk-lf-1", langfuse_secret_key="sk-lf-1")
    assert observability.ensure_configured(settings) is False
    assert clean_langfuse.success_callback == []


def test_langfuse_registers_litellm_callback_and_thread_metadata(clean_langfuse, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda _name: object())
    settings = _settings(
        langfuse_public_key="pk-lf-1", langfuse_secret_key="sk-lf-1", langfuse_host="http://lf.test"
    )
    assert observability.ensure_configured(settings) is True
    assert observability.ensure_configured(settings) is True  # idempotente
    assert clean_langfuse.success_callback == ["langfuse"]
    assert clean_langfuse.failure_callback == ["langfuse"]
    assert clean_langfuse.turn_off_message_logging is True  # sin contenido por defecto
    assert os.environ["LANGFUSE_HOST"] == "http://lf.test"
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY")
    monkeypatch.delenv("LANGFUSE_HOST")

    seen: list[dict] = []

    def fake(**kwargs):
        seen.append(kwargs)
        message = SimpleNamespace(content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    from pydantic import BaseModel

    class Out(BaseModel):
        ok: bool

    llm = LLMClient(_settings(llm_model="fake/m", llm_model_fast="fake/m"), completion=fake)
    llm.structured("sin contexto", Out)
    assert "metadata" not in seen[-1]
    with observability_context("hilo-1", "perfil"):
        llm.structured("con contexto", Out)
    meta = seen[-1]["metadata"]
    assert meta["session_id"] == meta["trace_id"] == "hilo-1"
    assert meta["trace_name"] == "puente.perfil" and meta["generation_name"] == "perfil"


class observability_context:  # noqa: N801
    def __init__(self, thread_id, agent):
        self.ctx = observability.TraceContext(thread_id, agent)

    def __enter__(self):
        self.token = observability.trace_context.set(self.ctx)

    def __exit__(self, *_exc):
        observability.trace_context.reset(self.token)


def test_trace_rows_carry_the_langfuse_trace_id_only_when_enabled(
    clean_langfuse, monkeypatch, session_factory
):
    from pydantic import BaseModel

    class Out(BaseModel):
        ok: bool

    llm = _llm('{"ok": true}', '{"ok": true}')
    with session_factory() as session:
        with traced(session, "t-off", "perfil", llm) as trace:
            llm.structured("a", Out)
            trace.decision = "x"
        monkeypatch.setattr("importlib.util.find_spec", lambda _name: object())
        observability.ensure_configured(
            _settings(langfuse_public_key="pk-lf-1", langfuse_secret_key="sk-lf-1")
        )
        for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
            monkeypatch.delenv(var, raising=False)
        with traced(session, "t-on", "perfil", llm) as trace:
            llm.structured("a", Out)
            trace.decision = "x"
        with traced(session, "t-det", "matching", llm) as trace:  # sin llamadas al LLM
            trace.decision = "x"
        [off] = _rows(session, "t-off")
        [on] = _rows(session, "t-on")
        [det] = _rows(session, "t-det")
    assert off.langfuse_trace_id is None
    assert on.langfuse_trace_id == "t-on"
    assert det.langfuse_trace_id is None


# --- Columnas nuevas en una BD existente ---------------------------------------------------


def test_init_db_adds_new_trace_columns_to_an_old_database():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE agent_trace (id VARCHAR(36) PRIMARY KEY, thread_id VARCHAR(64), "
                "agent VARCHAR(40), step VARCHAR(80), input_summary TEXT, decision TEXT, "
                "reason TEXT, duration_ms INTEGER, langfuse_trace_id VARCHAR(64), "
                "created_at DATETIME)"
            )
        )
        conn.execute(text("INSERT INTO agent_trace (id, thread_id) VALUES ('1', 't')"))
    init_db(engine)
    init_db(engine)  # idempotente
    cols = {c["name"] for c in inspect(engine).get_columns("agent_trace")}
    assert {"output_summary", "tool", "kind"} <= cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT kind FROM agent_trace")).scalar() == "paso"
    engine.dispose()
