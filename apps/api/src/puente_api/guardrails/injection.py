"""Detección de inyección de prompt en texto no confiable (CV, entrevista, ofertas).

Todo texto de usuarios o de terceros es DATO, nunca instrucción (OWASP LLM01). Estas reglas
son deterministas y viven en código: ningún LLM decide si un texto es una inyección.

Las reglas se aplican sobre el texto sin tildes y en minúsculas, tras quitar caracteres
invisibles (cero ancho, bidi). Los índices devueltos apuntan al texto sin invisibles
(`strip_invisible`), que es la base de `screen_text`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from puente_api.guardrails.discrimination_rules import _fold

# Caracteres invisibles usados para ocultar instrucciones o romper patrones.
_INVISIBLE = re.compile("[​‌‍⁠﻿‪-‮⁦-⁩]")


@dataclass(frozen=True)
class InjectionSpan:
    rule_id: str
    start: int
    end: int
    text: str


def strip_invisible(text: str) -> str:
    return _INVISIBLE.sub("", text)


def _re(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


_W = r"(?:\s+\S+){0,3}?"  # hasta 3 palabras de relleno entre términos clave

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignorar_instrucciones",
        _re(
            r"\b(?:ignora|ignore|olvida|forget|disregard|omite|descarta|desobedece)\w*"
            + _W
            + r"\s+(?:instrucciones|instructions|prompts?|reglas|rules|indicaciones|lo\s+anterior|"
            r"previous|prior|above)\b"
        ),
    ),
    (
        "nuevas_instrucciones",
        _re(
            r"\b(?:nuevas?\s+instrucciones|new\s+instructions|a\s+partir\s+de\s+ahora|"
            r"from\s+now\s+on)\b"
        ),
    ),
    (
        "cambio_de_rol",
        _re(
            r"\b(?:ahora\s+eres|eres\s+ahora|you\s+are\s+now|act\s+as|actua\s+como|"
            r"finge\s+(?:ser|que)|pretend\s+(?:to\s+be|you)|haz\s+de\s+cuenta\s+que)\b"
        ),
    ),
    (
        "extraccion_prompt",
        _re(
            r"\b(?:revela|muestra|imprime|repite|reveal|show|print|repeat|dime|dame)\w*"
            + _W
            + r"\s+(?:tu|el|your|the)\s+(?:system\s+)?(?:prompt|instrucciones(?:\s+iniciales)?|"
            r"instructions)\b|\bsystem\s+prompt\b|\bprompt\s+del\s+sistema\b"
        ),
    ),
    (
        "tokens_de_plantilla",
        _re(
            r"</?\s*(?:system|assistant|user|instructions?)\s*>|\[/?inst\]|<<\s*sys\s*>>|"
            r"<\|(?:im_start|im_end|system|endoftext)\|>|#{2,}\s*(?:system|instruction)s?\b"
        ),
    ),
    (
        "jailbreak",
        _re(
            r"\b(?:dan\s+mode|modo\s+dan|developer\s+mode|modo\s+desarrollador|jailbreak|"
            r"sin\s+restricciones|without\s+(?:any\s+)?restrictions|do\s+anything\s+now)\b"
        ),
    ),
    (
        "manipular_resultado",
        _re(
            r"\b(?:asigna|asignar|recomienda|recomendar|selecciona|seleccionar|contrata|"
            r"califica|puntua|rank|score|rate|hire|assign|recommend)\w*"
            + _W
            + r"\s+(?:a\s+)?(?:este|esta|el|la|this|the)\s+(?:candidat[oa]|postulante|joven|"
            r"perfil|cv|curriculum|candidate|applicant)\b|"
            r"\b(?:puntaje|score|puntuacion)\s*(?:de|=|:|a)?\s*(?:1(?:[.,]0+)?|100\s*%?|maximo|"
            r"perfecto)\b"
        ),
    ),
    (
        "saltar_controles",
        _re(
            r"\b(?:omite|salta|saltate|bypass|skip|desactiva|disable)\w*"
            + _W
            + r"\s+(?:la\s+|el\s+|los\s+|las\s+|the\s+)?(?:revision|aprobacion|auditoria|"
            r"guardrails?|validaciones?|filtros?|approval|review|audit|safety)\b"
        ),
    ),
    (
        "ejecutar_herramienta",
        _re(
            r"\b(?:ejecuta|llama\s+a|invoca|call|run|execute|invoke)\s+(?:la\s+|the\s+)?"
            r"(?:herramienta|tool|funcion|function|comando|command)\b"
        ),
    ),
    (
        "exfiltracion",
        _re(
            r"\b(?:envia|enviar|manda|send|forward|exfiltra\w*|filtra)\b"
            + _W
            + r"\s+(?:los\s+|las\s+|todos?\s+)?(?:datos|correos?|emails?|cedulas?|contrasenas?|"
            r"passwords?|data)\b|https?://\S+\?\S*(?:data|token|key)="
        ),
    ),
)


def detect_injection(text: str) -> list[InjectionSpan]:
    """Hallazgos de inyección sobre `strip_invisible(text)`, ordenados y sin solapes."""
    clean = strip_invisible(text or "")
    folded = _fold(clean)
    spans: list[InjectionSpan] = []
    for rule_id, pattern in _RULES:
        for m in pattern.finditer(folded):
            spans.append(InjectionSpan(rule_id, m.start(), m.end(), clean[m.start() : m.end()]))
    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    out: list[InjectionSpan] = []
    for s in spans:
        if out and s.start < out[-1].end:
            continue
        out.append(s)
    return out
