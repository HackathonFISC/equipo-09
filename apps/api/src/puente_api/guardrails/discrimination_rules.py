"""Reglas de discriminación en ofertas de empleo (docs/02-requerimientos-tecnicos.md §5).

Son reglas deterministas sobre texto: el LLM nunca decide si una oferta es discriminatoria,
solo puede explicarla. Cada regla tiene un `rule_id` estable y un test unitario.

Firma pública::

    detect_discrimination(text: str) -> DiscriminationReport

    DiscriminationReport.discriminatory: bool      # True = bloquear con HITL
    DiscriminationReport.findings: tuple[DiscriminationSpan, ...]
    DiscriminationReport.kinds: frozenset[str]
    DiscriminationReport.messages() -> list[str]   # texto para `audit_check.findings`

Controles de precisión (NO se marcan, requisitos legítimos): «mayores de 18 años» (mínimo
legal), licencia de conducir, carné de manipulador de alimentos, certificaciones técnicas.

Los patrones se aplican sobre el texto en minúsculas y sin tildes (mapeo 1:1 de caracteres,
así los índices apuntan al texto original).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

DiscriminationKind = Literal[
    "edad",
    "genero",
    "apariencia",
    "foto",
    "estado_civil",
    "embarazo",
    "residencia",
    "nacionalidad",
]

LEGAL_MIN_AGE = 18


class DiscriminationSpan(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: DiscriminationKind
    rule_id: str
    text: str  # fragmento del texto original
    start: int
    end: int


_KIND_LABEL: dict[str, str] = {
    "edad": "Restricción de edad",
    "genero": "Restricción de género",
    "apariencia": "Requisito de apariencia",
    "foto": "Solicitud de foto",
    "estado_civil": "Estado civil o hijos",
    "embarazo": "Prueba o estado de embarazo",
    "residencia": "Restricción de residencia",
    "nacionalidad": "Restricción de nacionalidad",
}


class DiscriminationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[DiscriminationSpan, ...] = ()

    @property
    def discriminatory(self) -> bool:
        return bool(self.findings)

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(f.kind for f in self.findings)

    def messages(self) -> list[str]:
        """Una línea por hallazgo, apta para `audit_check.findings`."""
        return [f"{_KIND_LABEL[f.kind]}: «{f.text.strip()}»" for f in self.findings]


def _fold(text: str) -> str:
    """Minúsculas y sin tildes, preservando la longitud (índices válidos en el original)."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFD", ch)[0]
        low = base.lower()
        out.append(low if len(low) == 1 else base)
    return "".join(out)


def _accept_all(_m: re.Match[str]) -> bool:
    return True


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    kind: DiscriminationKind
    pattern: re.Pattern[str]
    # Permite descartar coincidencias legítimas (p. ej. «mayores de 18 años»).
    accept: Callable[[re.Match[str]], bool] = _accept_all


def _re(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


def _age_over_min(m: re.Match[str]) -> bool:
    """«mayores de 18 años» es el mínimo legal; cualquier otro tope o rango discrimina."""
    text = m.group(0)
    nums = [int(n) for n in re.findall(r"\d{2}", text)]
    return not (len(nums) == 1 and nums[0] <= LEGAL_MIN_AGE and "mayor" in text)


_INCLUSIVE = r"(?!\s*(?:/|\())"  # excluye «cajero/a» y «cajero(a)»

_RULES: tuple[_Rule, ...] = (
    # --- Edad ---
    _Rule("edad_rango", "edad", _re(r"\b(?:de|entre)\s+\d{2}\s+(?:a|y|hasta)\s+\d{2}\s+anos?\b")),
    _Rule(
        "edad_tope",
        "edad",
        _re(
            r"\b(?:menor(?:es)?|mayor(?:es)?)\s+de\s+\d{2}(?:\s+anos?)?\b(?!\s+de\s+experiencia)|"
            r"\b(?:maximo|minimo|hasta)\s+\d{2}\s+anos\b(?!\s+de\s+experiencia)"
        ),
        _age_over_min,
    ),
    _Rule(
        "edad_expresion",
        "edad",
        _re(r"\b(?:edad\s+(?:maxima|minima|entre)\b|\d{2}\s+anos\s+de\s+edad)"),
    ),
    # --- Género ---
    _Rule(
        "genero_explicito",
        "genero",
        _re(
            r"\b(?:solo\s+|solamente\s+|unicamente\s+|exclusivamente\s+)?"
            r"(?:mujeres|varones|hombres|damas|caballeros|"
            r"sexo\s+(?:femenino|masculino)|genero\s+(?:femenino|masculino))\b"
        ),
    ),
    _Rule(
        "genero_titulo_femenino",
        "genero",
        _re(
            r"\b(?:meseras?|cajeras?|camareras?|secretarias?|azafatas?|vendedoras?)\b"
            + _INCLUSIVE
            + r"|\b(?:recepcionista|asistente|vendedor|cajero)\s+(?:soltera|casada)\b"
        ),
    ),
    # --- Apariencia ---
    _Rule(
        "apariencia",
        "apariencia",
        _re(
            r"\b(?:buena|excelente|agradable|optima)\s+(?:presencia|presentacion|apariencia)\b|"
            r"\b(?:presentacion|apariencia|aspecto)\s+(?:personal|fisic[oa])\b|"
            r"\b(?:bien\s+parecid[oa]s?|atractiv[oa]s?|buen\s+aspecto|estatura|"
            r"peso\s+(?:proporcional|ideal))\b"
        ),
    ),
    # --- Foto ---
    _Rule("foto", "foto", _re(r"\b(?:fotos?|fotografias?)\b")),
    # --- Estado civil / hijos ---
    _Rule(
        "estado_civil",
        "estado_civil",
        _re(
            r"\b(?:solter[oa]s?|casad[oa]s?|divorciad[oa]s?|viud[oa]s?|estado\s+civil|"
            r"sin\s+hijos|sin\s+compromisos?|sin\s+cargas?\s+familiares?|con\s+hijos)\b"
        ),
    ),
    # --- Embarazo ---
    _Rule(
        "embarazo",
        "embarazo",
        _re(
            r"\b(?:prueba|test|examen)\s+de\s+(?:embarazo|gravidez)\b|\bembarazad[ao]s?\b|"
            r"\bestado\s+de\s+gestacion\b"
        ),
    ),
    # --- Residencia (barrio o corregimiento como filtro) ---
    _Rule(
        "residencia",
        "residencia",
        _re(
            r"\bno\s+residentes?\s+(?:de|en)\b|"
            r"\bresidentes?\s+(?:de|en|del)\s+(?!panama\b)[a-z]|"
            r"\bque\s+(?:viva|vivan|resida|residan)\s+en\b"
        ),
    ),
    # --- Nacionalidad ---
    _Rule(
        "nacionalidad",
        "nacionalidad",
        _re(
            r"\b(?:solo|solamente|unicamente|exclusivamente)\s+(?:de\s+nacionalidad\s+)?"
            r"(?:panamen[oa]s?|nacionales)\b|\bno\s+(?:se\s+aceptan\s+)?extranjer[oa]s?\b|"
            r"\bnacionalidad\s+(?:panamena|requerida)\b"
        ),
    ),
)


def detect_discrimination(text: str) -> DiscriminationReport:
    """Aplica todas las reglas y devuelve los hallazgos ordenados por posición.

    Determinista y sin red; texto vacío o sin coincidencias → `discriminatory == False`.
    Las coincidencias solapadas del mismo `kind` se fusionan en una (la primera/más larga).
    """
    text = text or ""
    folded = _fold(text)
    raw: list[DiscriminationSpan] = []
    for rule in _RULES:
        for m in rule.pattern.finditer(folded):
            if not rule.accept(m):
                continue
            start, end = m.span()
            while start < end and not text[start].strip():
                start += 1
            raw.append(
                DiscriminationSpan(
                    kind=rule.kind,
                    rule_id=rule.rule_id,
                    text=text[start:end],
                    start=start,
                    end=end,
                )
            )
    raw.sort(key=lambda s: (s.start, -(s.end - s.start), s.rule_id))
    merged: list[DiscriminationSpan] = []
    for s in raw:
        if any(k.kind == s.kind and s.start < k.end for k in merged):
            continue  # solapada con una anterior del mismo tipo
        merged.append(s)
    return DiscriminationReport(findings=tuple(merged))
