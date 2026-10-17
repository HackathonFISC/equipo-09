"""Pantalla de entrada única para texto no confiable.

    screen_text(text: str, *, source: Source = "posting") -> GuardrailResult

Se aplica, en este orden y sin LLM:
1. Inyección de prompt (cualquier fuente): bloquea y neutraliza las instrucciones embebidas.
2. PII (cédula, teléfono, correo): se redacta en `sanitized`; no bloquea por sí sola.
3. Discriminación (solo `source="posting"`): bloquea ofertas con criterios prohibidos.
   No se aplica a CV ni entrevistas: allí «casada» o «25 años» son datos del joven, no criterios.

`allowed == False` significa que el texto NO debe llegar al LLM ni publicarse sin revisión
humana; `sanitized` es siempre seguro de usar (sin PII ni instrucciones embebidas).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from puente_api.guardrails.discrimination_rules import detect_discrimination
from puente_api.guardrails.injection import detect_injection, strip_invisible
from puente_api.guardrails.pii import PII_PLACEHOLDER, find_pii

Source = Literal["posting", "cv", "interview"]

INJECTION_PLACEHOLDER = "[instrucción bloqueada]"
MAX_CHARS = 20_000


class GuardrailResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    sanitized: str
    reasons: list[str] = Field(default_factory=list)


def _replace(text: str, edits: list[tuple[int, int, str]]) -> str:
    out, pos = [], 0
    for start, end, repl in sorted(edits):
        out.append(text[pos:start])
        out.append(repl)
        pos = end
    out.append(text[pos:])
    return "".join(out)


def screen_text(text: str, *, source: Source = "posting") -> GuardrailResult:
    """Evalúa y sanea `text`. Determinista; nunca lanza por contenido hostil."""
    clean = strip_invisible(text or "")
    reasons: list[str] = []
    allowed = True

    if len(clean) > MAX_CHARS:
        clean = clean[:MAX_CHARS]
        allowed = False
        reasons.append(f"texto_demasiado_largo: más de {MAX_CHARS} caracteres")

    edits: list[tuple[int, int, str]] = []
    inj = detect_injection(clean)
    for s in inj:
        edits.append((s.start, s.end, INJECTION_PLACEHOLDER))
        reasons.append(f"inyeccion_prompt:{s.rule_id}: «{s.text.strip()}»")
    if inj:
        allowed = False

    for p in find_pii(clean):
        if any(p.start < e and st < p.end for st, e, _ in edits):
            continue  # ya cubierto por una instrucción bloqueada
        edits.append((p.start, p.end, PII_PLACEHOLDER[p.kind]))
        reasons.append(f"pii_redactada:{p.kind}")

    if source == "posting":
        report = detect_discrimination(clean)
        if report.discriminatory:
            allowed = False
            reasons.extend(f"discriminacion:{m}" for m in report.messages())

    return GuardrailResult(allowed=allowed, sanitized=_replace(clean, edits), reasons=reasons)
