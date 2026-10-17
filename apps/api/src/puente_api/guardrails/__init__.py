"""Guardrails en código (no en el prompt).

API pública:

    from puente_api.guardrails import detect_discrimination, DiscriminationReport

    detect_discrimination(text: str) -> DiscriminationReport
"""

from puente_api.guardrails.discrimination_rules import (
    DiscriminationKind,
    DiscriminationReport,
    DiscriminationSpan,
    detect_discrimination,
)

__all__ = [
    "DiscriminationKind",
    "DiscriminationReport",
    "DiscriminationSpan",
    "detect_discrimination",
]
