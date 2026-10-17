"""Configuración por entorno. Lee `.env` de apps/api o de la raíz del monorepo."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[2]
# En Docker la API vive en /app sin el monorepo encima: entonces no hay raíz aparte.
_REPO_ROOT = _API_DIR.parents[1] if len(_API_DIR.parents) > 1 else _API_DIR
ENV_FILES = (_REPO_ROOT / ".env", _API_DIR / ".env")

# Variables estándar de proveedor que LiteLLM lee de `os.environ` (respaldo de otro proveedor
# distinto al de LLM_MODEL). pydantic-settings no exporta lo que lee de `.env`, así que
# `export_provider_keys` las copia al entorno.
PROVIDER_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "OLLAMA_API_BASE",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./puente.db"
    # Archivo SQLite de los checkpoints del grafo (pausas HITL). Vacío = junto a la BD SQLite,
    # o en memoria si la BD es Postgres. En Docker conviene fijarlo en un volumen.
    checkpoint_path: str | None = None
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # LLM vía LiteLLM: el prefijo del modelo define el proveedor.
    llm_model: str = "anthropic/claude-sonnet-5-5"
    llm_model_fast: str = "anthropic/claude-haiku-5-5"
    llm_fallback_model: str | None = None
    llm_api_key: str | None = None
    llm_max_retries: int = 2
    llm_timeout_s: float = 60.0
    # Endurecimiento (H5): espera exponencial entre reintentos, circuito por petición,
    # presupuesto de tiempo por petición y caché opcional de respuestas (demo y evals).
    llm_backoff_s: float = 0.5
    llm_circuit_failures: int = 4
    llm_budget_s: float = 45.0
    llm_cache_dir: str | None = None

    # Langfuse (opcional): solo se activa con ambas claves. Ver `llm.observability`.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
    langfuse_log_content: bool = False


def export_provider_keys(env_files: tuple[Path, ...] = ENV_FILES) -> list[str]:
    """Copia a `os.environ` las claves de proveedor definidas en `.env` sin pisar las existentes.

    Igual que en `Settings`, el último archivo gana (apps/api/.env sobre el de la raíz), y una
    variable ya definida en el entorno real (p. ej. Docker) gana sobre ambos.
    """
    exported: list[str] = []
    for path in reversed(env_files):
        if not path.is_file():
            continue
        for name, value in dotenv_values(path, encoding="utf-8").items():
            if name in PROVIDER_KEY_VARS and value and name not in os.environ:
                os.environ[name] = value
                exported.append(name)
    return exported


@lru_cache
def get_settings() -> Settings:
    export_provider_keys()
    return Settings()
