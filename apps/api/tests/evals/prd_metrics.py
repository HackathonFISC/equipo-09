"""Métricas de éxito del PRD (docs/01-prd.md §8) medidas sobre los datos semilla.

Complementan los casos de `cases/*.json`: aquellos son escenarios pequeños y controlados; estas
métricas corren los mismos solvers y reglas sobre los 40 jóvenes, 25 ofertas y 25 etiquetas del
seed. Deterministas: sin LLM, sin red y sin base de datos. La métrica de extracción con LLM
(F1) vive aparte, en `llm_extraction.py`, porque necesita un proveedor configurado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from puente_api.db.seed.loaders import read_seed_bundle, seed_uuid
from puente_api.db.seed.schemas import SeedBundle
from puente_api.guardrails import detect_discrimination
from puente_api.solvers.auditor import audit_matching
from puente_api.solvers.auditor_adapter import protected_from_seed
from puente_api.solvers.matching import MatchingParams, MatchingResult, check_pair, solve_matching
from puente_api.solvers.matching_adapter import MatchingInput, input_from_seed

LLM_RESULTS = Path(__file__).parent / "results-llm.md"


@dataclass(frozen=True)
class Metric:
    name: str
    target: str
    value: str
    passed: bool | None  # None = informativa o no medida
    how: str


def _pct(num: int, den: int) -> str:
    return f"{num}/{den} ({100 * num / den:.0f} %)" if den else "sin datos"


def strict_violations(
    inp: MatchingInput, result: MatchingResult, names: dict[str, str] | None = None
) -> list[str]:
    """Re-verifica cada asignación con el preset ESTRICTO (sin holguras), independiente del
    solver: traslado ≤ máximo, costo ≤ presupuesto, horario, salario y habilidades obligatorias.
    """
    names = names or {}
    strict = MatchingParams()
    youths = {y.id: y for y in inp.youths}
    postings = {p.id: p for p in inp.postings}
    out = []
    for a in result.assignments:
        ev = check_pair(youths[a.youth_id], postings[a.posting_id], inp.commute, strict)
        if ev.violated:
            who = names.get(a.youth_id, a.youth_id[:8])
            what = names.get(a.posting_id, a.posting_id[:8])
            out.append(f"{who} → {what}: {', '.join(ev.violated)}")
    return out


def _names(bundle: SeedBundle) -> dict[str, str]:
    """UUID del seed → nombre legible, para que la tabla diga «Ana → Cajero/a», no un id."""
    out = {str(seed_uuid("youth", y.key)): y.display_name for y in bundle.youth}
    out.update({str(seed_uuid("job_posting", p.key)): p.title for p in bundle.postings})
    return out


def matching_metrics(bundle: SeedBundle) -> list[Metric]:
    inp = input_from_seed(bundle)
    names = _names(bundle)
    strict = solve_matching(inp.youths, inp.postings, inp.commute, MatchingParams())
    demo = solve_matching(inp.youths, inp.postings, inp.commute, MatchingParams.relaxed())
    strict_bad = strict_violations(inp, strict, names)
    demo_bad = strict_violations(inp, demo, names)
    metrics = [
        Metric(
            "Matches que violan restricciones duras (preset estricto)",
            "0",
            f"{len(strict_bad)} de {len(strict.assignments)} asignaciones",
            not strict_bad,
            "Seed completo con `MatchingParams()`; cada asignación se re-verifica con "
            "`check_pair` estricto, independiente del solver.",
        ),
        Metric(
            "Asignaciones con holgura en el preset del demo (`relaxed`)",
            "informativa",
            f"{len(demo_bad)} de {len(demo.assignments)} asignaciones",
            None,
            "El nodo Matching usa `MatchingParams.relaxed()`: tolera 15 min, B/. 1.00 y 1 "
            "habilidad obligatoria, penalizados. "
            + ("Casos: " + "; ".join(demo_bad) if demo_bad else "Ninguna usó holgura."),
        ),
    ]
    protected = protected_from_seed(bundle)
    report = audit_matching(inp.youths, inp.postings, inp.commute, demo, protected=protected)
    for check in report.checks:
        parity = check.parity if check.parity is not None else 0.0
        metrics.append(
            Metric(
                f"Paridad contrafactual: {check.variable}",
                "≥ 95 %",
                f"{100 * parity:.0f} % ({len(inp.youths)} jóvenes, "
                f"{len(demo.assignments)} con asignación)",
                parity >= 0.95,
                "Se re-ejecuta el solver del demo cambiando la variable y se cuenta qué "
                "fracción de jóvenes conserva su resultado. Con pocas asignaciones la "
                "paridad es poco exigente: los no asignados siguen sin asignar.",
            )
        )
    return metrics


def discrimination_metrics(bundle: SeedBundle) -> list[Metric]:
    texts = {p.key: p.raw_input for p in bundle.postings}
    tp = fp = fn = tn = 0
    kinds_expected = kinds_found = 0
    misses: list[str] = []
    for label in bundle.discrimination_labels:
        report = detect_discrimination(texts[label.posting])
        if label.discriminatory and report.discriminatory:
            tp += 1
        elif label.discriminatory:
            fn += 1
            misses.append(label.posting)
        elif report.discriminatory:
            fp += 1
            misses.append(f"{label.posting} (falso positivo)")
        else:
            tn += 1
        expected = {f.kind for f in label.findings}
        kinds_expected += len(expected)
        kinds_found += len(expected & set(report.kinds))
    detail = "Errores: " + ", ".join(misses) if misses else "Sin errores."
    return [
        Metric(
            "Detección de ofertas discriminatorias (recall)",
            "≥ 90 %",
            _pct(tp, tp + fn),
            (tp + fn) > 0 and tp / (tp + fn) >= 0.9,
            f"Reglas deterministas sobre las 25 ofertas etiquetadas a mano. {detail}",
        ),
        Metric(
            "Detección de ofertas discriminatorias (precisión)",
            "informativa",
            _pct(tp, tp + fp),
            None,
            f"Incluye {tn} ofertas limpias y los controles de precisión del seed.",
        ),
        Metric(
            "Tipos de requisito discriminatorio detectados",
            "informativa",
            _pct(kinds_found, kinds_expected),
            None,
            "Por oferta: tipos esperados (edad, género, apariencia…) que las reglas encontraron.",
        ),
    ]


def llm_metric() -> Metric:
    """Lee el F1 de `results-llm.md` si alguien corrió el eval con LLM; si no, queda pendiente."""
    if LLM_RESULTS.is_file():
        for line in LLM_RESULTS.read_text(encoding="utf-8").splitlines():
            if line.startswith("F1_OFERTAS="):
                value = float(line.split("=", 1)[1])
                return Metric(
                    "Extracción de habilidades de ofertas (F1)",
                    "≥ 0.80",
                    f"{value:.2f}",
                    value >= 0.8,
                    "LLM real sobre las 25 ofertas del seed vs. requisitos etiquetados "
                    "(ver `results-llm.md`).",
                )
    return Metric(
        "Extracción de habilidades de ofertas (F1)",
        "≥ 0.80",
        "no medido",
        None,
        "Requiere un proveedor LLM: `uv run python -m tests.evals.llm_extraction`.",
    )


def all_metrics(bundle: SeedBundle | None = None) -> list[Metric]:
    bundle = bundle or read_seed_bundle()
    return [*matching_metrics(bundle), *discrimination_metrics(bundle), llm_metric()]
