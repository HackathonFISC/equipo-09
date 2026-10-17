"""Genera `results.md` a partir de los casos: `uv run python -m tests.evals.report`."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from tests.evals.runner import CaseResult, run_all

OUT = Path(__file__).parent / "results.md"
CATEGORY_LABEL = {
    "matching": "Matching (restricciones duras)",
    "auditor": "Auditor contrafactual y discriminación",
    "guardrails": "Guardrails de entrada",
    "formacion": "Ruta de formación",
}


def _rate(ok: int, n: int) -> str:
    return f"{ok}/{n} ({(100 * ok / n) if n else 100:.0f} %)"


def _ok(rs: list[CaseResult]) -> int:
    return sum(r.passed for r in rs)


def build(results: list[CaseResult]) -> str:
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)

    lines = [
        "# Resultados de evals",
        "",
        "Generado con `uv run python -m tests.evals.report` (no editar a mano). "
        "Los evals son deterministas: usan los solvers OR-Tools y los guardrails directamente, "
        "sin LLM, sin red y sin base de datos.",
        "",
        "## Métrica",
        "",
        "Un caso **pasa** cuando su salida coincide con `expected` (métrica de la columna "
        "«Métrica» de cada caso) y se cumplen las invariantes transversales: "
        "0 restricciones duras violadas en las asignaciones y 0 fugas de PII o instrucciones "
        "embebidas en `sanitized`. La puntuación por categoría es casos pasados / casos totales.",
        "",
        "## Resumen por categoría",
        "",
        "| Categoría | Casos | Pasan | Exactitud |",
        "|---|---:|---:|---:|",
    ]
    total_ok = 0
    for cat, rs in by_cat.items():
        ok = sum(r.passed for r in rs)
        total_ok += ok
        lines.append(
            f"| {CATEGORY_LABEL.get(cat, cat)} | {len(rs)} | {ok} | {_rate(ok, len(rs))} |"
        )
    lines.append(
        f"| **Total** | **{len(results)}** | **{total_ok}** | **{_rate(total_ok, len(results))}** |"
    )

    guards = by_cat.get("guardrails", [])
    attacks = [r for r in guards if r.case["expected"]["reasons_prefix"]]
    benign = [r for r in guards if not r.case["expected"]["reasons_prefix"]]
    lines += [
        "",
        "## Métricas de guardrails",
        "",
        f"- Ataques o PII detectados (recall): {_rate(_ok(attacks), len(attacks))}",
        f"- Textos legítimos sin falsos positivos: {_rate(_ok(benign), len(benign))}",
        "",
        "## Detalle por caso",
        "",
        "| Caso | Categoría | Métrica | Resultado |",
        "|---|---|---|---|",
    ]
    for r in results:
        mark = "PASA" if r.passed else "FALLA: " + "; ".join(r.problems)
        lines.append(f"| `{r.id}` | {r.category} | {r.case['metric']} | {mark} |")

    lines += [
        "",
        "## Cómo reproducirlos",
        "",
        "```bash",
        "pnpm --filter api evals                      # pytest tests/evals (un test por caso)",
        "cd apps/api && uv run python -m tests.evals.report   # regenera este archivo",
        "```",
        "",
        "Los casos viven en `apps/api/tests/evals/cases/*.json` (uno por categoría; "
        "`_world.json` es la tabla de traslados compartida). Para añadir un caso, agrega un "
        "objeto con `id`, `category`, `type`, `description`, `metric`, `input` y `expected`; "
        "los tipos válidos son `matching`, `audit_matching`, `audit_posting`, `guardrail` y "
        "`training` (ver `runner.py`). Los controles positivos del auditor "
        "(`audit-02`, `audit-03`) usan solvers sesgados a propósito para comprobar que el "
        "contrafactual detecta el sesgo.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    results = run_all()
    OUT.write_text(build(results), encoding="utf-8", newline="\n")
    failed = [r.id for r in results if not r.passed]
    print(f"{len(results) - len(failed)}/{len(results)} casos pasan -> {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
