"""Guardrails en código (no en el prompt).

API pública:

    from puente_api.guardrails import screen_text, GuardrailResult, detect_discrimination

    screen_text(text: str, *, source: "posting" | "cv" | "interview" = "posting") -> GuardrailResult
        GuardrailResult.allowed: bool        # False = no enviar al LLM / revisión humana
        GuardrailResult.sanitized: str       # sin PII ni instrucciones embebidas
        GuardrailResult.reasons: list[str]   # inyeccion_prompt:…, pii_redactada:…, discriminacion:…
    detect_discrimination(text: str) -> DiscriminationReport
"""

from puente_api.guardrails.discrimination_rules import (
    DiscriminationKind,
    DiscriminationReport,
    DiscriminationSpan,
    detect_discrimination,
)
from puente_api.guardrails.injection import InjectionSpan, detect_injection
from puente_api.guardrails.pii import PiiSpan, find_pii
from puente_api.guardrails.screen import GuardrailResult, screen_text

__all__ = [
    "DiscriminationKind",
    "DiscriminationReport",
    "DiscriminationSpan",
    "GuardrailResult",
    "InjectionSpan",
    "PiiSpan",
    "detect_discrimination",
    "detect_injection",
    "find_pii",
    "screen_text",
]
