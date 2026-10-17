"""Adaptadores del auditor: atributos protegidos y textos de ofertas desde seeds u ORM.

Firmas públicas::

    protected_from_seed(bundle: SeedBundle) -> dict[str, ProtectedAttrs]
    protected_from_models(youths: Iterable[models.Youth]) -> dict[str, ProtectedAttrs]
    posting_texts_from_seed(bundle, statuses=None) -> dict[str, str]
    posting_texts_from_models(postings: Iterable[models.JobPosting]) -> dict[str, str]

Las claves son los mismos ids que usa `matching_adapter` (UUID deterministas del seed o
`id` de la fila), de modo que `protected[youth.id]` siempre resuelve.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from puente_api.solvers.auditor import ProtectedAttrs

if TYPE_CHECKING:
    from puente_api.db import models
    from puente_api.db.seed.schemas import SeedBundle


def protected_from_seed(bundle: SeedBundle) -> dict[str, ProtectedAttrs]:
    from puente_api.db.seed.loaders import seed_uuid

    return {
        str(seed_uuid("youth", y.key)): ProtectedAttrs(
            display_name=y.display_name, gender=y.gender, birth_year=y.birth_year
        )
        for y in bundle.youth
    }


def protected_from_models(youths: Iterable[models.Youth]) -> dict[str, ProtectedAttrs]:
    return {
        y.id: ProtectedAttrs(display_name=y.display_name, gender=y.gender, birth_year=y.birth_year)
        for y in youths
    }


def posting_texts_from_seed(
    bundle: SeedBundle, statuses: Sequence[str] | None = None
) -> dict[str, str]:
    """Texto original de cada oferta (`raw_input`), indexado por el UUID del seed."""
    from puente_api.db.seed.loaders import seed_uuid

    return {
        str(seed_uuid("job_posting", p.key)): p.raw_input
        for p in bundle.postings
        if statuses is None or p.status in statuses
    }


def posting_texts_from_models(postings: Iterable[models.JobPosting]) -> dict[str, str]:
    return {p.id: p.raw_input for p in postings if getattr(p, "raw_input", None)}
