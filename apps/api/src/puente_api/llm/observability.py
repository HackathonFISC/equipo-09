"""Langfuse opcional vía el callback de LiteLLM, más el contexto de traza de cada llamada.

Se activa solo si existen `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` (valores reales, no
`changeme`) y el paquete `langfuse` está instalado (extra `langfuse`). Sin eso no se hace nada:
la trazabilidad obligatoria vive en `agent_trace` (ver `puente_api.tracing`).

Cada llamada al LLM lleva en `metadata` el hilo del grafo (`session_id`/`trace_id`), el agente
(`trace_name`, `generation_name`, `tags`), así que en Langfuse un hilo es una traza y cada nodo
una generación. Por defecto NO se envía el contenido de los mensajes (CVs de jóvenes, datos
personales): solo modelo, latencia, tokens y errores. `LANGFUSE_LOG_CONTENT=true` lo habilita.
"""

import importlib.util
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from puente_api.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceContext:
    thread_id: str
    agent: str


# Lo fija `tracing.traced` mientras un nodo trabaja; `LLMClient` lo lee al llamar al modelo.
trace_context: ContextVar[TraceContext | None] = ContextVar("puente_trace_context", default=None)

_enabled: bool | None = None


def _real(value: str | None) -> bool:
    return bool(value) and "changeme" not in (value or "").lower()


def langfuse_configured(settings: Settings) -> bool:
    return _real(settings.langfuse_public_key) and _real(settings.langfuse_secret_key)


def ensure_configured(settings: Settings) -> bool:
    """Registra el callback de Langfuse una sola vez por proceso. Devuelve si quedó activo."""
    global _enabled
    if _enabled is not None:
        return _enabled
    _enabled = False
    if not langfuse_configured(settings):
        return False
    if importlib.util.find_spec("langfuse") is None:
        log.warning(
            "LANGFUSE_* definidas pero falta el paquete `langfuse` (uv sync --extra langfuse); "
            "se continúa solo con agent_trace"
        )
        return False
    try:
        import litellm

        # LiteLLM lee estas variables del entorno, no de `Settings`.
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key or ""
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key or ""
        if settings.langfuse_host:
            os.environ["LANGFUSE_HOST"] = settings.langfuse_host
        for attr in ("success_callback", "failure_callback"):
            callbacks = list(getattr(litellm, attr, []) or [])
            if "langfuse" not in callbacks:
                setattr(litellm, attr, [*callbacks, "langfuse"])
        litellm.turn_off_message_logging = not settings.langfuse_log_content
    except Exception:  # la observabilidad nunca debe romper el flujo
        log.exception("No se pudo activar Langfuse; se continúa solo con agent_trace")
        return False
    _enabled = True
    return True


def is_enabled() -> bool:
    return bool(_enabled)


def reset_for_tests() -> None:
    global _enabled
    _enabled = None


def langfuse_metadata() -> dict[str, Any]:
    """`metadata` de la llamada a LiteLLM; vacío si Langfuse está apagado o no hay contexto."""
    ctx = trace_context.get()
    if not _enabled or ctx is None:
        return {}
    return {
        "trace_id": ctx.thread_id,
        "session_id": ctx.thread_id,
        "trace_name": f"puente.{ctx.agent}",
        "generation_name": ctx.agent,
        "tags": ["puente", ctx.agent],
    }
