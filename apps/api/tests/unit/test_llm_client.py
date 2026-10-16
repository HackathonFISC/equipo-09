"""LLMClient con el LLM simulado: nunca llama a un proveedor real."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from puente_api.config import Settings
from puente_api.llm import LLMClient, LLMError


class Oferta(BaseModel):
    titulo: str
    vacantes: int


class FakeLLM:
    """Devuelve las salidas en orden; si una es excepción, la lanza."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        message = SimpleNamespace(content=out)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _settings(**overrides):
    values = {
        "llm_model": "anthropic/principal",
        "llm_model_fast": "anthropic/rapido",
        "llm_fallback_model": None,
        "llm_api_key": "sk-test",
        "llm_max_retries": 2,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_structured_parses_fenced_json_and_sends_schema():
    fake = FakeLLM('```json\n{"titulo": "Cajero", "vacantes": 2}\n```')
    out = LLMClient(_settings(), completion=fake).structured("Extrae la oferta", Oferta)
    assert out == Oferta(titulo="Cajero", vacantes=2)
    call = fake.calls[0]
    assert call["model"] == "anthropic/principal"
    assert call["temperature"] == 0
    assert call["api_key"] == "sk-test"
    assert '"vacantes"' in call["messages"][0]["content"]  # JSON Schema en el system prompt


def test_retries_with_validation_feedback():
    fake = FakeLLM('{"titulo": "Cajero"}', '{"titulo": "Cajero", "vacantes": 1}')
    out = LLMClient(_settings(), completion=fake).structured("x", Oferta)
    assert out.vacantes == 1
    assert len(fake.calls) == 2
    retry = fake.calls[1]["messages"]
    assert retry[-2]["role"] == "assistant"
    assert "no cumple el esquema" in retry[-1]["content"]


def test_falls_back_to_second_model_after_retries():
    fake = FakeLLM(TimeoutError("t1"), "no es json", "{}", '{"titulo": "A", "vacantes": 3}')
    out = LLMClient(_settings(), completion=fake).structured("x", Oferta)
    assert out.vacantes == 3
    assert [c["model"] for c in fake.calls] == ["anthropic/principal"] * 3 + ["anthropic/rapido"]


def test_fallback_from_other_provider_does_not_get_primary_key():
    fake = FakeLLM(RuntimeError("caído"), '{"titulo": "A", "vacantes": 1}')
    settings = _settings(llm_fallback_model="openai/otro", llm_max_retries=0)
    LLMClient(settings, completion=fake).structured("x", Oferta)
    assert fake.calls[1]["model"] == "openai/otro"
    assert "api_key" not in fake.calls[1]


def test_model_aliases_resolve_with_fallback():
    client = LLMClient(_settings())
    assert client.resolve_models("default") == ["anthropic/principal", "anthropic/rapido"]
    assert client.resolve_models("fast") == ["anthropic/rapido", "anthropic/principal"]
    assert client.resolve_models("ollama/llama3")[0] == "ollama/llama3"


def test_all_fail_raises_or_returns_safe_default():
    client = LLMClient(_settings(llm_max_retries=0), completion=FakeLLM("x", "y"))
    with pytest.raises(LLMError):
        client.structured("x", Oferta)

    safe = Oferta(titulo="", vacantes=1)
    client = LLMClient(_settings(llm_max_retries=0), completion=FakeLLM("x", "y"))
    assert client.structured("x", Oferta, default=safe) is safe


def test_vision_sends_image_as_data_url():
    fake = FakeLLM('{"titulo": "Mesero", "vacantes": 1}')
    out = LLMClient(_settings(), completion=fake).vision("Lee la oferta", b"\x89PNG", Oferta)
    assert out.titulo == "Mesero"
    content = fake.calls[0]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "Lee la oferta"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
