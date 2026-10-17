"""Redacción de PII sensible: cédula panameña, teléfono y correo.

La redacción es determinista (regex). Los placeholders no conservan ningún dígito ni dominio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from puente_api.guardrails.injection import strip_invisible

PII_PLACEHOLDER = {"cedula": "[CÉDULA]", "telefono": "[TELÉFONO]", "correo": "[CORREO]"}


@dataclass(frozen=True)
class PiiSpan:
    kind: str  # cedula | telefono | correo
    start: int
    end: int


# Cédula: 8-123-4567, PE-12-345, E-8-12345, N-12-345, 4-AV-123-456, 8-NT-2-123.
_CEDULA = re.compile(
    r"(?<![\w-])(?:\d{1,2}(?:\s?-\s?(?:AV|PI|NT))?|PE|E|N)\s?-\s?\d{1,4}\s?-\s?\d{2,6}(?![\w-])",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
# Móvil 6xxx-xxxx, fijo 2xx/3xx/5xx/7xx-xxxx, con prefijo opcional +507 / 507.
_PHONE = re.compile(
    r"(?<![\w-])(?:\(?\+?507\)?[\s.-]?)?(?:6\d{3}[\s.-]?\d{4}|[2357]\d{2}[\s.-]?\d{4})(?![\w-])"
)


def find_pii(text: str) -> list[PiiSpan]:
    """Spans de PII sobre `strip_invisible(text)`; la cédula tiene prioridad sobre el teléfono."""
    clean = strip_invisible(text or "")
    spans: list[PiiSpan] = []
    for kind, pattern in (("cedula", _CEDULA), ("correo", _EMAIL), ("telefono", _PHONE)):
        for m in pattern.finditer(clean):
            if any(m.start() < s.end and s.start < m.end() for s in spans):
                continue
            spans.append(PiiSpan(kind, m.start(), m.end()))
    return sorted(spans, key=lambda s: s.start)
