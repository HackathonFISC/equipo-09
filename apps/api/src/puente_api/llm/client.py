"""Única puerta al LLM. LiteLLM elige el proveedor por el prefijo del modelo (`.env`).

El LLM extrae, redacta y explica; nunca decide restricciones. Toda salida se valida con Pydantic:
si no valida, se reintenta mostrándole el error al modelo (máx. `LLM_MAX_RETRIES`) y luego se pasa
al modelo de respaldo. Si todo falla, se devuelve `default` o se lanza `LLMError`.
"""

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from puente_api.config import Settings, get_settings
from puente_api.llm import observability

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Completion = Callable[..., Any]

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMError(RuntimeError):
    """Ningún modelo devolvió una salida válida."""


@dataclass(frozen=True)
class LLMCall:
    """Una llamada al proveedor (o el uso del valor por defecto), para `agent_trace`."""

    model: str
    ok: bool
    duration_ms: int
    tokens: int | None = None
    note: str | None = None


def _default_completion(**kwargs: Any) -> Any:
    import litellm  # import diferido: tarda en cargar y los tests no lo necesitan.

    return litellm.completion(**kwargs)


def _extract_json(content: str) -> str:
    text = _FENCE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


class LLMClient:
    def __init__(
        self, settings: Settings | None = None, completion: Completion | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self._completion = completion or _default_completion
        self.call_log: list[LLMCall] = []
        self._last_ms = 0
        self._last_tokens: int | None = None
        if completion is None:  # con un LLM simulado (tests) nunca se toca la red
            observability.ensure_configured(self.settings)

    # --- API pública ---------------------------------------------------------

    def structured(
        self,
        prompt: str,
        schema: type[T],
        model: str = "default",
        *,
        system: str | None = None,
        default: T | None = None,
    ) -> T:
        """Texto → instancia validada de `schema`."""
        return self._run([{"role": "user", "content": prompt}], schema, model, system, default)

    def vision(
        self,
        prompt: str,
        image: bytes,
        schema: type[T],
        model: str = "default",
        *,
        mime_type: str = "image/png",
        system: str | None = None,
        default: T | None = None,
    ) -> T:
        """Imagen (foto de oferta, CV escaneado) + instrucción → instancia validada de `schema`."""
        data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode()}"
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        return self._run([{"role": "user", "content": content}], schema, model, system, default)

    # --- Internos ------------------------------------------------------------

    def resolve_models(self, model: str) -> list[str]:
        """Alias `default`/`fast` → modelo de `.env`, seguido del respaldo (sin duplicados)."""
        s = self.settings
        primary = {"default": s.llm_model, "fast": s.llm_model_fast}.get(model, model)
        fallback = s.llm_fallback_model or (
            s.llm_model_fast if primary != s.llm_model_fast else s.llm_model
        )
        return [primary] if fallback == primary else [primary, fallback]

    def _system_prompt(self, schema: type[BaseModel], system: str | None) -> str:
        json_schema = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        contract = (
            "Responde únicamente con un objeto JSON válido, sin texto adicional, "
            f"que cumpla este JSON Schema:\n{json_schema}"
        )
        return f"{system}\n\n{contract}" if system else contract

    def _run(
        self,
        messages: list[dict[str, Any]],
        schema: type[T],
        model: str,
        system: str | None,
        default: T | None,
    ) -> T:
        base = [{"role": "system", "content": self._system_prompt(schema, system)}, *messages]
        errors: list[str] = []
        for model_name in self.resolve_models(model):
            convo = list(base)
            for attempt in range(1 + self.settings.llm_max_retries):
                try:
                    content = self._call(model_name, convo)
                except Exception as exc:  # errores de red/proveedor: reintento y luego respaldo
                    self.call_log.append(
                        LLMCall(model_name, False, self._last_ms, note=type(exc).__name__)
                    )
                    errors.append(f"{model_name}#{attempt}: {type(exc).__name__}: {exc}")
                    log.warning("LLM %s falló (intento %d): %s", model_name, attempt, exc)
                    continue
                try:
                    parsed = schema.model_validate_json(_extract_json(content))
                    self.call_log.append(
                        LLMCall(model_name, True, self._last_ms, self._last_tokens)
                    )
                    return parsed
                except ValidationError as exc:
                    self.call_log.append(
                        LLMCall(
                            model_name, False, self._last_ms, self._last_tokens, "salida inválida"
                        )
                    )
                    errors.append(f"{model_name}#{attempt}: salida inválida")
                    log.warning("LLM %s salida inválida (intento %d)", model_name, attempt)
                    convo += [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": "Tu respuesta no cumple el esquema. Errores:\n"
                            f"{exc.errors(include_url=False)}\nDevuelve solo el JSON corregido.",
                        },
                    ]
        if default is not None:
            self.call_log.append(LLMCall("(valor por defecto)", False, 0, note="sin salida válida"))
            log.error("LLM sin salida válida; se usa el valor por defecto. %s", errors)
            return default
        raise LLMError("; ".join(errors))

    def _call(self, model_name: str, messages: list[dict[str, Any]]) -> str:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": 0,
            "timeout": self.settings.llm_timeout_s,
        }
        # LLM_API_KEY es del proveedor de LLM_MODEL; otros proveedores usan su variable
        # estándar (OPENAI_API_KEY, ...), que LiteLLM lee sola.
        key = self.settings.llm_api_key
        same_provider = model_name.split("/")[0] == self.settings.llm_model.split("/")[0]
        if key and key != "changeme" and same_provider:
            kwargs["api_key"] = key
        metadata = observability.langfuse_metadata()
        if metadata:
            kwargs["metadata"] = metadata
        start = time.perf_counter()
        self._last_tokens = None
        try:
            response = self._completion(**kwargs)
        finally:
            self._last_ms = int((time.perf_counter() - start) * 1000)
        usage = getattr(response, "usage", None)
        total = getattr(usage, "total_tokens", None)
        self._last_tokens = total if isinstance(total, int) else None
        content = response.choices[0].message.content
        if not content:
            raise LLMError("respuesta vacía")
        return content


def get_llm() -> LLMClient:
    """Dependencia de FastAPI; los tests la sustituyen por un cliente con LLM simulado."""
    return LLMClient()
