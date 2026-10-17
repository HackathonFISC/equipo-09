"""Única puerta al LLM. LiteLLM elige el proveedor por el prefijo del modelo (`.env`).

El LLM extrae, redacta y explica; nunca decide restricciones. Toda salida se valida con Pydantic:
si no valida, se reintenta mostrándole el error al modelo (máx. `LLM_MAX_RETRIES`) y luego se pasa
al modelo de respaldo. Si todo falla, se devuelve `default` o se lanza `LLMError`.
"""

import base64
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from puente_api.config import Settings, get_settings
from puente_api.llm import observability

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Completion = Callable[..., Any]

# Mapa de modelos incluido en LiteLLM: sin esto, el primer `import litellm` intenta bajarlo de
# GitHub y, con la red lenta o caída (wifi del evento), tarda segundos en reintentos.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
# Códigos HTTP que no mejoran reintentando con el mismo modelo.
PERMANENT_STATUS = frozenset({400, 401, 403, 404, 422})
MAX_BACKOFF_S = 4.0


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


def status_code(exc: BaseException) -> int | None:
    """Código HTTP de un error de LiteLLM/proveedor (None si es de red o desconocido)."""
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def is_permanent(exc: BaseException) -> bool:
    """¿Reintentar con el mismo modelo es inútil? (credenciales, modelo, parámetros)."""
    return status_code(exc) in PERMANENT_STATUS


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        completion: Completion | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._completion = completion or _default_completion
        # Con un LLM simulado (tests) no se espera entre reintentos, salvo que se pida.
        self._sleep = sleep or (time.sleep if completion is None else (lambda _s: None))
        self.call_log: list[LLMCall] = []
        self._last_ms = 0
        self._last_tokens: int | None = None
        self._failures_in_a_row = 0
        self._started: float | None = None
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

    def _elapsed(self) -> float:
        return 0.0 if self._started is None else time.monotonic() - self._started

    def _blocked(self) -> str | None:
        """Motivo para no llamar al proveedor (circuito abierto o presupuesto agotado)."""
        s = self.settings
        if s.llm_circuit_failures > 0 and self._failures_in_a_row >= s.llm_circuit_failures:
            return f"circuito abierto tras {self._failures_in_a_row} fallas seguidas"
        if s.llm_budget_s > 0 and self._elapsed() >= s.llm_budget_s:
            return f"presupuesto de {s.llm_budget_s:.0f} s agotado"
        return None

    def _backoff(self, attempt: int) -> None:
        base = self.settings.llm_backoff_s
        if base <= 0:
            return
        delay = min(MAX_BACKOFF_S, base * 2**attempt) * (0.5 + random.random() / 2)
        self._sleep(delay)

    def _run(
        self,
        messages: list[dict[str, Any]],
        schema: type[T],
        model: str,
        system: str | None,
        default: T | None,
    ) -> T:
        base = [{"role": "system", "content": self._system_prompt(schema, system)}, *messages]
        cached = self._cache_get(base, schema)
        if cached is not None:
            return cached
        if self._started is None:
            self._started = time.monotonic()

        errors: list[str] = []
        for model_name in self.resolve_models(model):
            convo = list(base)
            for attempt in range(1 + self.settings.llm_max_retries):
                blocked = self._blocked()
                if blocked:
                    errors.append(blocked)
                    break
                try:
                    content = self._call(model_name, convo)
                except Exception as exc:  # errores de red/proveedor: reintento y luego respaldo
                    self._failures_in_a_row += 1
                    self.call_log.append(
                        LLMCall(model_name, False, self._last_ms, note=type(exc).__name__)
                    )
                    errors.append(f"{model_name}#{attempt}: {type(exc).__name__}: {exc}")
                    log.warning("LLM %s falló (intento %d): %s", model_name, attempt, exc)
                    if is_permanent(exc):
                        break  # clave, modelo o parámetro inválido: al modelo de respaldo
                    if attempt < self.settings.llm_max_retries:
                        self._backoff(attempt)
                    continue
                self._failures_in_a_row = 0  # el proveedor respondió
                try:
                    parsed = schema.model_validate_json(_extract_json(content))
                    self.call_log.append(
                        LLMCall(model_name, True, self._last_ms, self._last_tokens)
                    )
                    self._cache_put(base, model_name, content)
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
        raise LLMError("; ".join(errors) or "sin modelos configurados")

    def _call(self, model_name: str, messages: list[dict[str, Any]]) -> str:
        s = self.settings
        remaining = s.llm_budget_s - self._elapsed() if s.llm_budget_s > 0 else s.llm_timeout_s
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": 0,
            # Quita lo que el modelo no acepta (temperature en Claude 5.x / GPT-5) sin fallar.
            "drop_params": True,
            "timeout": max(1.0, min(s.llm_timeout_s, remaining)),
        }
        # LLM_API_KEY es del proveedor de LLM_MODEL; otros proveedores usan su variable
        # estándar (OPENAI_API_KEY, ...), que LiteLLM lee sola.
        key = s.llm_api_key
        same_provider = model_name.split("/")[0] == s.llm_model.split("/")[0]
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

    # --- Caché opcional (ensayos del demo y evals) ---------------------------

    def _cache_path(self, base: list[dict[str, Any]]) -> Path | None:
        folder = self.settings.llm_cache_dir
        if not folder:
            return None
        raw = json.dumps(base, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return Path(folder) / f"{digest}.json"

    def _cache_get(self, base: list[dict[str, Any]], schema: type[T]) -> T | None:
        path = self._cache_path(base)
        if path is None or not path.is_file():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            parsed = schema.model_validate_json(_extract_json(entry["content"]))
        except (OSError, KeyError, ValueError) as exc:  # entrada corrupta: se ignora
            log.warning("Caché LLM ilegible (%s): %s", path.name, exc)
            return None
        self.call_log.append(LLMCall(f"{entry.get('model', 'llm')} [caché]", True, 0))
        return parsed

    def _cache_put(self, base: list[dict[str, Any]], model_name: str, content: str) -> None:
        path = self._cache_path(base)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({"model": model_name, "content": content}, ensure_ascii=False)
            # Escritura atómica: dos peticiones a la vez nunca dejan un archivo a medias.
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(entry)
            os.replace(tmp, path)
        except OSError as exc:  # la caché nunca debe romper el flujo
            log.warning("No se pudo guardar la caché LLM: %s", exc)


def get_llm() -> LLMClient:
    """Dependencia de FastAPI; los tests la sustituyen por un cliente con LLM simulado."""
    return LLMClient()
