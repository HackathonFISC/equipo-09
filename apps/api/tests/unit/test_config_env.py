"""Las claves estándar de proveedor puestas en `.env` llegan a LiteLLM (vía `os.environ`)."""

import os

import pytest

from puente_api.config import PROVIDER_KEY_VARS, export_provider_keys


@pytest.fixture
def clean_env(monkeypatch):
    for var in PROVIDER_KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_provider_keys_from_env_files_are_exported(tmp_path, clean_env):
    root = tmp_path / "root.env"
    root.write_text(
        "LLM_MODEL=gemini/gemini-3.8-flash\nGEMINI_API_KEY=g-root\nOPENAI_API_KEY=o-root\n",
        encoding="utf-8",
    )
    api = tmp_path / "api.env"
    api.write_text("OPENAI_API_KEY=o-api\nLLM_CACHE_DIR=.llm-cache\n", encoding="utf-8")

    exported = export_provider_keys((root, api))

    assert sorted(exported) == ["GEMINI_API_KEY", "OPENAI_API_KEY"]
    assert os.environ["GEMINI_API_KEY"] == "g-root"
    assert os.environ["OPENAI_API_KEY"] == "o-api"  # el último archivo gana, como en Settings


def test_real_environment_wins_and_empty_values_are_ignored(tmp_path, clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "del-entorno")
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=del-archivo\nGEMINI_API_KEY=\n", encoding="utf-8")

    assert export_provider_keys((env, tmp_path / "no-existe.env")) == []
    assert os.environ["ANTHROPIC_API_KEY"] == "del-entorno"
    assert "GEMINI_API_KEY" not in os.environ


def test_litellm_does_not_load_dotenv_by_itself():
    import puente_api.llm.client  # noqa: F401  (fija el modo antes de importar litellm)

    assert os.environ["LITELLM_MODE"] == "PRODUCTION"
