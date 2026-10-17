"""Ejecutor determinista de evals: lee `cases/*.json` y llama a solvers y guardrails directamente.

Sin LLM, sin red, sin BD. Cada caso tiene `id`, `category`, `type`, `description`, `metric`,
`input` y `expected`; `run_case` devuelve un `CaseResult` con `passed` y la lista de
discrepancias (vacía si pasa). Los archivos que empiezan por «_» no son casos (`_world.json`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from puente_api.guardrails import screen_text
from puente_api.solvers.auditor import ProtectedAttrs, audit_matching, audit_posting
from puente_api.solvers.matching import (
    CommuteEntry,
    CommuteTable,
    MatchingParams,
    MatchingResult,
    PostingIn,
    TimeSlot,
    YouthIn,
    solve_matching,
)
from puente_api.solvers.training import CourseIn, TrainingParams, solve_training

CASES_DIR = Path(__file__).parent / "cases"


@dataclass
class CaseResult:
    case: dict[str, Any]
    passed: bool
    problems: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.case["id"]

    @property
    def category(self) -> str:
        return self.case["category"]


# --- Carga -------------------------------------------------------------------


def load_cases(cases_dir: Path = CASES_DIR) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(cases_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        cases.extend(json.loads(path.read_text(encoding="utf-8")))
    return cases


def _world() -> dict[str, Any]:
    return json.loads((CASES_DIR / "_world.json").read_text(encoding="utf-8"))


# --- Conversión de entradas compactas -----------------------------------------


def _slots(raw: list[str] | list[dict[str, str]]) -> list[TimeSlot]:
    """«lun,mar 08:00-16:00» → un TimeSlot por día."""
    out: list[TimeSlot] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(TimeSlot.model_validate(item))
            continue
        days, rng = item.split(" ")
        start, end = rng.split("-")
        out.extend(TimeSlot(day=d, start=start, end=end) for d in days.split(","))  # type: ignore[arg-type]
    return out


def _expand(obj: dict[str, Any]) -> dict[str, Any]:
    obj = dict(obj)
    for key in ("availability", "schedule"):
        if key in obj:
            obj[key] = _slots(obj[key])
    return obj


def _commute(spec: str | list[list[Any]]) -> CommuteTable:
    rows = _world()["commute"][spec] if isinstance(spec, str) else spec
    return {(a, b): CommuteEntry(minutes=m, cost_daily=c) for a, b, m, c in rows}


def _youths(raw: list[dict[str, Any]]) -> list[YouthIn]:
    return [YouthIn.model_validate(_expand(y)) for y in raw]


def _postings(raw: list[dict[str, Any]]) -> list[PostingIn]:
    return [PostingIn.model_validate(_expand(p)) for p in raw]


def _params(spec: str | None) -> MatchingParams:
    return MatchingParams.relaxed() if spec == "relaxed" else MatchingParams()


# --- Solvers sesgados a propósito (controles positivos del auditor) -----------


def _biased_gender(ys, ps, commute, params, protected) -> MatchingResult:
    kept = [y for y in ys if protected.get(y.id, ProtectedAttrs()).gender != "femenino"]
    return solve_matching(kept, ps, commute, params)


def _biased_name(ys, ps, commute, params, protected) -> MatchingResult:
    kept = [y for y in ys if protected.get(y.id, ProtectedAttrs()).display_name != "Zoila"]
    return solve_matching(kept, ps, commute, params)


_SOLVERS: dict[str, Callable[..., MatchingResult] | None] = {
    "blind": None,
    "biased_gender": _biased_gender,
    "biased_name": _biased_name,
}


# --- Manejadores por tipo ------------------------------------------------------


def _run_matching(inp: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    result = solve_matching(
        _youths(inp["youths"]),
        _postings(inp["postings"]),
        _commute(inp["commute"]),
        _params(inp.get("params")),
    )
    problems: list[str] = []
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        problems.append(f"estado del solver: {result.status}")
    by_youth = result.by_youth()
    # Métrica transversal: ninguna asignación puede violar una restricción dura sin holgura.
    for a in result.assignments:
        bad = [c.name for c in a.constraints if not c.ok]
        if bad:
            problems.append(f"{a.youth_id}→{a.posting_id} viola {bad}")
    for yid, pid in exp.get("assignments", {}).items():
        got = by_youth[yid].posting_id if yid in by_youth else None
        if got != pid:
            problems.append(f"{yid}: esperado {pid}, obtenido {got}")
    if "assigned_count" in exp and len(result.assignments) != exp["assigned_count"]:
        problems.append(
            f"asignados: esperado {exp['assigned_count']}, obtenido {len(result.assignments)}"
        )
    for pid, cap in exp.get("max_load", {}).items():
        load = sum(1 for a in result.assignments if a.posting_id == pid)
        if load > cap:
            problems.append(f"{pid}: {load} asignados > {cap} vacantes")
    if "slacks" in exp:
        got_slacks = sorted({s.constraint for s in result.slacks})
        if got_slacks != sorted(exp["slacks"]):
            problems.append(f"holguras: esperado {sorted(exp['slacks'])}, obtenido {got_slacks}")
        if any(s.penalty <= 0 for s in result.slacks):
            problems.append("hay holguras sin penalización")
    return problems


def _run_audit_matching(inp: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    ys, ps, commute = _youths(inp["youths"]), _postings(inp["postings"]), _commute(inp["commute"])
    params = MatchingParams()
    protected = {k: ProtectedAttrs.model_validate(v) for k, v in inp["protected"].items()}
    solve_fn = _SOLVERS[inp["solver"]]
    # La corrida base usa el mismo solver que los contrafactuales (el que se audita).
    base = (solve_fn or (lambda *a: solve_matching(*a[:4])))(ys, ps, commute, params, protected)
    report = audit_matching(
        ys,
        ps,
        commute,
        base,
        protected=protected,
        solve_fn=solve_fn,
        parity_threshold=inp["parity_threshold"],
    )
    checks = {c.variable: c for c in report.checks}
    problems: list[str] = []
    for var, want in exp.get("passed", {}).items():
        if checks[var].passed != want:
            problems.append(f"{var}: passed esperado {want}, obtenido {checks[var].passed}")
    for var, want in exp.get("parity", {}).items():
        got = checks[var].parity
        if got is None or abs(got - want) > 1e-9:
            problems.append(f"{var}: paridad esperada {want}, obtenida {got}")
    for var, limit in exp.get("parity_below", {}).items():
        got = checks[var].parity
        if got is None or got >= limit:
            problems.append(f"{var}: paridad {got} debía ser < {limit}")
    return problems


def _run_audit_posting(inp: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    from puente_api.guardrails import detect_discrimination

    check = audit_posting("p", inp["text"])
    kinds = sorted(detect_discrimination(inp["text"]).kinds)
    problems: list[str] = []
    if check.passed != exp["passed"]:
        problems.append(f"passed esperado {exp['passed']}, obtenido {check.passed}")
    missing = set(exp["kinds"]) - set(kinds)
    if missing:
        problems.append(f"faltan hallazgos {sorted(missing)} (obtenidos {kinds})")
    if not exp["kinds"] and kinds:
        problems.append(f"hallazgos inesperados {kinds}")
    return problems


def _run_guardrail(inp: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    res = screen_text(inp["text"], source=inp["source"])
    problems: list[str] = []
    if res.allowed != exp["allowed"]:
        problems.append(f"allowed esperado {exp['allowed']}, obtenido {res.allowed}")
    for prefix in exp["reasons_prefix"]:
        if not any(r.startswith(prefix) for r in res.reasons):
            problems.append(f"falta razón «{prefix}» (razones: {res.reasons})")
    if not exp["reasons_prefix"] and res.reasons and exp["allowed"]:
        problems.append(f"razones inesperadas: {res.reasons}")
    for frag in exp["sanitized_excludes"]:
        if frag in res.sanitized:
            problems.append(f"fuga en sanitized: «{frag}»")
    for frag in exp["sanitized_contains"]:
        if frag not in res.sanitized:
            problems.append(f"sanitized no contiene «{frag}»")
    return problems


def _run_training(inp: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    courses = []
    for c in inp["courses"]:
        c = dict(c)
        c["sessions"] = [_expand(s) for s in c["sessions"]]
        courses.append(CourseIn.model_validate(c))
    result = solve_training(
        _youths([inp["youth"]])[0],
        _postings(inp["postings"]),
        courses,
        _commute(inp["commute"]),
        TrainingParams(**inp["params"]),
    )
    problems: list[str] = []
    got_sessions = sorted(it.session.id for it in result.items)
    if got_sessions != sorted(exp["session_ids"]):
        problems.append(f"sesiones: esperado {sorted(exp['session_ids'])}, obtenido {got_sessions}")
    got_unlocked = sorted(u.posting_id for u in result.unlocked)
    if got_unlocked != sorted(exp["unlocked"]):
        problems.append(
            f"desbloqueadas: esperado {sorted(exp['unlocked'])}, obtenido {got_unlocked}"
        )
    bad = [c.name for c in result.constraints if not c.ok]
    if bad:
        problems.append(f"restricciones del plan violadas: {bad}")
    return problems


_HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], list[str]]] = {
    "matching": _run_matching,
    "audit_matching": _run_audit_matching,
    "audit_posting": _run_audit_posting,
    "guardrail": _run_guardrail,
    "training": _run_training,
}


def run_case(case: dict[str, Any]) -> CaseResult:
    problems = _HANDLERS[case["type"]](case["input"], case["expected"])
    return CaseResult(case=case, passed=not problems, problems=problems)


def run_all(cases: list[dict[str, Any]] | None = None) -> list[CaseResult]:
    return [run_case(c) for c in (cases if cases is not None else load_cases())]
