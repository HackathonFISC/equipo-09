"""Normalización determinista a catálogos: habilidades ESCO-lite y corregimientos.

El LLM propone nombres en texto libre; aquí el código decide a qué fila del catálogo
corresponden (coincidencia exacta de etiqueta o alias, y luego similitud difusa con umbral).
Lo que no alcanza el umbral se descarta: nunca se inventan habilidades.
"""

import difflib
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from puente_api.db import models

SKILL_CUTOFF = 0.82
LOCATION_CUTOFF = 0.85


def fold(text: str) -> str:
    """Minúsculas, sin acentos ni signos, espacios simples."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() else " " for ch in plain)
    return " ".join(cleaned.split())


@dataclass(frozen=True)
class SkillIndex:
    by_key: dict[str, models.Skill]
    labels: list[str]

    @classmethod
    def load(cls, session: Session) -> "SkillIndex":
        by_key: dict[str, models.Skill] = {}
        for skill in session.scalars(select(models.Skill).order_by(models.Skill.label_es)):
            for name in [skill.label_es, *(skill.aliases or [])]:
                key = fold(name)
                if key:
                    by_key.setdefault(key, skill)
        labels = sorted({s.label_es for s in by_key.values()})
        return cls(by_key=by_key, labels=labels)

    def match(self, name: str) -> models.Skill | None:
        key = fold(name)
        if not key:
            return None
        if key in self.by_key:
            return self.by_key[key]
        close = difflib.get_close_matches(key, list(self.by_key), n=1, cutoff=SKILL_CUTOFF)
        return self.by_key[close[0]] if close else None


def match_location(session: Session, name: str | None) -> models.Location | None:
    if not name or not fold(name):
        return None
    locations = list(session.scalars(select(models.Location)))
    by_key = {fold(loc.corregimiento): loc for loc in locations}
    key = fold(name)
    if key in by_key:
        return by_key[key]
    close = difflib.get_close_matches(key, list(by_key), n=1, cutoff=LOCATION_CUTOFF)
    return by_key[close[0]] if close else None


def evidence_in(evidence: str, source: str) -> bool:
    """La evidencia debe ser un fragmento literal (módulo acentos/espacios) del texto fuente."""
    needle = fold(evidence)
    return bool(needle) and needle in fold(source)
