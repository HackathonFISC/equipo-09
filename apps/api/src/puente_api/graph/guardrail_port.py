"""Puerto de guardrails de entrada (los implementa Sebastian en `puente_api.guardrails`).

Interfaz que el grafo espera de él, en `puente_api/guardrails/__init__.py`:

    def screen_text(text: str, *, source: Literal["posting", "cv", "interview"]) -> GuardrailResult

    GuardrailResult:
        allowed: bool          # False = no se llama al LLM y la petición se rechaza (422)
        sanitized: str         # texto a usar en lugar del original (igual si no hubo cambios)
        reasons: list[str]     # por qué se bloqueó o saneó, en español, para la traza

Se acepta un objeto con esos atributos o un dict. Para que el 422 lleve el campo `guardrail` del
contrato (`inyeccion | fuera_de_alcance | dato_absurdo | archivo_invalido | pii`), conviene que
cada razón empiece con ese código: `"inyeccion: pide ignorar las instrucciones"`. Si no, se
infiere por palabras clave y, en último caso, se usa `fuera_de_alcance`.

Mientras `screen_text` no exista se usa un NO-OP (deja pasar todo y lo dice en `reasons`; no se
deja traza por ese motivo). Si la implementación real lanza una excepción se BLOQUEA (falla
cerrado): un guardrail roto nunca debe dejar pasar texto sin revisar.

En ofertas (`source="posting"`) la discriminación NO bloquea aquí: el agente Mercado la detecta,
cita el texto literal y abre la revisión humana. Solo bloquean inyección y texto fuera de límites.

La traza queda en `agent_trace` (`kind = guardrail`) cuando el texto se sanea o se bloquea.
"""

import inspect
from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from puente_api.problems import Guardrail
from puente_api.tracing import record_trace

TOOL = "guardrails.screen_text"
Source = Literal["posting", "cv", "interview"]
DISCRIMINATION_PREFIX = "discriminacion:"
STUB_NOTICE = "STUB: guardrails no instalados; el texto no se revisó"
_CODES: tuple[Guardrail, ...] = (
    "inyeccion",
    "fuera_de_alcance",
    "dato_absurdo",
    "archivo_invalido",
    "pii",
)
_KEYWORDS: dict[str, Guardrail] = {
    "inyecci": "inyeccion",
    "injection": "inyeccion",
    "instrucciones": "inyeccion",
    "pii": "pii",
    "dato personal": "pii",
    "cédula": "pii",
    "cedula": "pii",
    "absurd": "dato_absurdo",
    "archivo": "archivo_invalido",
}


class GuardrailResult(BaseModel):
    allowed: bool = True
    sanitized: str
    reasons: list[str] = Field(default_factory=list)

    @classmethod
    def from_any(cls, raw: Any, original: str) -> "GuardrailResult":
        def get(key: str) -> Any:
            return raw.get(key) if isinstance(raw, Mapping) else getattr(raw, key, None)

        allowed, sanitized = get("allowed"), get("sanitized")
        return cls(
            allowed=True if allowed is None else bool(allowed),
            sanitized=original if sanitized is None else str(sanitized),
            reasons=[str(r) for r in (get("reasons") or [])],
        )


class GuardrailBlocked(Exception):  # noqa: N818  (es un resultado de negocio, no un fallo)
    """El texto de entrada fue bloqueado: se responde 422 con `guardrail` y queda en la traza."""

    def __init__(self, agent: str, label: str, reasons: list[str]) -> None:
        self.agent, self.label, self.reasons = agent, label, reasons
        super().__init__(f"Entrada bloqueada por guardrails ({label}): {'; '.join(reasons)}")

    @property
    def code(self) -> Guardrail:
        for reason in self.reasons:
            head = reason.split(":", 1)[0].strip().lower()
            if head in _CODES:
                return head  # type: ignore[return-value]
        lowered = " ".join(self.reasons).lower()
        for needle, code in _KEYWORDS.items():
            if needle in lowered:
                return code
        return "fuera_de_alcance"


def _stub(text: str) -> GuardrailResult:
    return GuardrailResult(allowed=True, sanitized=text, reasons=[STUB_NOTICE])


def _load_impl() -> Callable[..., Any] | None:
    try:
        module = import_module("puente_api.guardrails")
    except ImportError:
        return None
    impl = getattr(module, "screen_text", None)
    return impl if callable(impl) else None


def _accepts_source(impl: Callable[..., Any]) -> bool:
    try:
        return "source" in inspect.signature(impl).parameters
    except (TypeError, ValueError):
        return False


def is_stub() -> bool:
    return _load_impl() is None


def screen_text(text: str, source: Source = "posting") -> GuardrailResult:
    impl = _load_impl()
    if impl is None:
        return _stub(text)
    try:
        raw = impl(text, source=source) if _accepts_source(impl) else impl(text)
        result = GuardrailResult.from_any(raw, text)
    except Exception as exc:  # un guardrail roto bloquea, no deja pasar
        return GuardrailResult(
            allowed=False,
            sanitized="",
            reasons=[f"fuera_de_alcance: falló la revisión de seguridad ({type(exc).__name__})"],
        )
    if source == "posting" and not result.allowed:
        # La discriminación en ofertas la resuelve Mercado con revisión humana, no un 422.
        others = [r for r in result.reasons if not r.startswith(DISCRIMINATION_PREFIX)]
        if len(others) < len(result.reasons) and not any(_blocks(r) for r in others):
            result = result.model_copy(update={"allowed": True})
    return result


def _blocks(reason: str) -> bool:
    """Razones que bloquean por sí solas; la PII redactada solo sanea."""
    return not reason.startswith("pii")


def screen_input(
    session: Session,
    thread_id: str,
    agent: str,
    text: str,
    label: str,
    *,
    source: Source = "posting",
) -> str:
    """Revisa el texto libre antes de dárselo al LLM. Devuelve el texto que se debe usar.

    - Bloqueado: lanza `GuardrailBlocked` (el ejecutor del grafo deja la traza y responde 422).
    - Saneado o con advertencias: deja una fila `guardrail` y devuelve el texto saneado.
    - Limpio: no deja rastro (el nodo ya traza su propia entrada).
    """
    result = screen_text(text, source)
    if not result.allowed:
        raise GuardrailBlocked(agent, label, result.reasons)
    reasons = [r for r in result.reasons if r != STUB_NOTICE]
    changed = result.sanitized != text
    if changed or reasons:
        record_trace(
            session,
            thread_id,
            agent,
            kind="guardrail",
            tool=TOOL,
            input_summary=f"{label}: {len(text)} caracteres",
            output_summary=f"{len(result.sanitized)} caracteres tras revisar",
            decision=f"{'saneado' if changed else 'advertencia'}: {label}",
            reason="; ".join(reasons) or "el guardrail modificó el texto",
            duration_ms=0,
        )
    return result.sanitized
