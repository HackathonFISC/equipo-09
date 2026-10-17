"""Configuración por entorno. Lee `.env` de apps/api o de la raíz del monorepo."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./puente.db"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
