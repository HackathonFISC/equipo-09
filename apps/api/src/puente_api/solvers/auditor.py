"""Auditor contrafactual del matching (docs/02-requerimientos-tecnicos.md, agente 7).

Idea: el solver de matching es ciego a los atributos protegidos por construcción (`YouthIn` no
tiene nombre ni género). El auditor lo **demuestra con datos**: re-ejecuta el solver sobre
entradas contrafactuales (mismo joven, atributo protegido distinto) y mide la paridad.

    paridad(variable) = jóvenes con el mismo resultado / jóvenes auditados

Un joven tiene «el mismo resultado» si queda asignado a la misma oferta (o sigue sin asignar);
si la oferta cambia pero el puntaje es igual dentro de `score_tol`, se considera empate del
solver y no sesgo. `passed = paridad >= parity_threshold` (por defecto 0,95: se tolera un
empate aislado en ~20 jóvenes, pero no un patrón por grupo).

Contrafactuales (`variable` del contrato `AuditCheck`):

- ``nombre``: se rotan los nombres entre jóvenes (cada uno recibe el del siguiente).
- ``genero``: cada joven con género declarado pasa a otro valor distinto.
- ``corregimiento``: cada joven pasa a un corregimiento *equivalente*, un gemelo con otra
  etiqueta pero la misma fila de la matriz de traslado (mismos minutos y costos). El resultado
  solo debería cambiar si el solver usa la etiqueta además del traslado.
- ``edad`` (opcional, no está en el enum del contrato): el año de nacimiento se desplaza.

Además se calcula impacto dispar (regla de los 4/5) por género y banda de edad: **informativo**;
no cambia `passed` salvo `enforce_disparate_impact=True`.

Firmas públicas::

    audit_matching(youths, postings, commute, result, *, protected=None, variables=...,
                   parity_threshold=0.95, score_tol=1e-6, solve_fn=None, run_key="",
                   enforce_disparate_impact=False, as_of_year=2026) -> AuditReport

    audit_postings(texts: Mapping[str, str]) -> list[AuditCheck]       # kind="discriminacion"
    audit_posting(posting_id: str, text: str) -> AuditCheck

    AuditReport.checks: tuple[AuditCheck, ...]
    AuditReport.passed: bool          # todos los checks pasan
    AuditReport.needs_review: bool    # algún check falló → crear review_task `alerta_sesgo`
    AuditReport.to_api() -> list[dict]  # camelCase compatible con `AuditCheck` de openapi.yaml

`solve_fn(youths, postings, commute, params, protected) -> MatchingResult` permite auditar
cualquier solver (en tests, uno que filtra por género para verificar que se detecta).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from puente_api.guardrails import detect_discrimination
from puente_api.solvers.matching import (
    CommuteEntry,
    CommuteTable,
    MatchingParams,
    MatchingResult,
    PostingIn,
    YouthIn,
    solve_matching,
)

Variable = Literal["nombre", "genero", "corregimiento", "edad"]
CONTRACT_VARIABLES: tuple[Variable, ...] = ("nombre", "genero", "corregimiento")
AuditKind = Literal["discriminacion", "contrafactual"]

AUDIT_NAMESPACE = uuid.UUID("6b1e2d84-6f0a-4c52-9a7e-0d2f6f6a7c11")

EQUIVALENT_SUFFIX = "#cf"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProtectedAttrs(_Frozen):
    """Atributos protegidos de un joven. Viven fuera de `YouthIn`: el solver no los recibe."""

    display_name: str | None = None
    gender: str | None = None
    birth_year: int | None = None


Protected = Mapping[str, ProtectedAttrs]
SolveFn = Callable[
    [list[YouthIn], list[PostingIn], CommuteTable, MatchingParams, Protected], MatchingResult
]


class GroupRate(_Frozen):
    group: str
    total: int
    assigned: int
    rate: float


class DisparateImpact(_Frozen):
    variable: str
    groups: tuple[GroupRate, ...]
    ratio: float | None  # tasa mínima / tasa máxima; None si no hay datos suficientes
    passed: bool
    note: str = ""


class AuditCheck(_Frozen):
    id: str
    kind: AuditKind
    variable: Variable | None = None
    parity: float | None = Field(default=None, ge=0, le=1)
    passed: bool
    findings: tuple[str, ...] = ()
    posting_id: str | None = None  # solo `kind == "discriminacion"`
    changed_youth_ids: tuple[str, ...] = ()  # solo contrafactuales: quién cambió de resultado

    def to_api(self) -> dict[str, Any]:
        """Formato del schema `AuditCheck` de openapi.yaml (sin campos internos)."""
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "passed": self.passed,
            "findings": list(self.findings),
        }
        if self.variable in CONTRACT_VARIABLES:
            out["variable"] = self.variable
        if self.parity is not None:
            out["parity"] = round(self.parity, 4)
        return out


class AuditReport(_Frozen):
    checks: tuple[AuditCheck, ...]
    disparate_impact: tuple[DisparateImpact, ...] = ()
    parity_threshold: float
    solves: int = 0

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def needs_review(self) -> bool:
        return not self.passed

    def to_api(self) -> list[dict[str, Any]]:
        return [c.to_api() for c in self.checks]


# --- Contrafactuales ---------------------------------------------------------


def _blind_solve(
    youths: list[YouthIn],
    postings: list[PostingIn],
    commute: CommuteTable,
    params: MatchingParams,
    protected: Protected,
) -> MatchingResult:
    return solve_matching(youths, postings, commute, params)


class _Scenario(BaseModel):
    """Entrada contrafactual + cómo volver a los ids originales."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    youths: list[YouthIn]
    commute: dict[tuple[str, str], CommuteEntry]
    protected: dict[str, ProtectedAttrs]
    id_map: dict[str, str]  # id contrafactual → id original


def _others(values: Sequence[str], current: str | None) -> str:
    """Primer valor distinto de `current` (orden estable); si no hay, uno sintético."""
    for v in sorted(set(values)):
        if v != current:
            return v
    return "otro" if current != "otro" else "otro_2"


def _scenario_nombre(
    youths: list[YouthIn], commute: CommuteTable, protected: Protected
) -> _Scenario:
    """Rota los nombres entre jóvenes (cada uno recibe el del siguiente); ids intactos."""
    ordered = sorted(youths, key=lambda y: y.id)
    n = len(ordered)
    names = [protected.get(y.id, ProtectedAttrs()).display_name for y in ordered]
    new_protected: dict[str, ProtectedAttrs] = {}
    for i, y in enumerate(ordered):
        attrs = protected.get(y.id, ProtectedAttrs())
        new_protected[y.id] = attrs.model_copy(update={"display_name": names[(i + 1) % n]})
    return _Scenario(
        youths=list(youths),
        commute=dict(commute),
        protected=new_protected,
        id_map={y.id: y.id for y in youths},
    )


def _scenario_genero(
    youths: list[YouthIn], commute: CommuteTable, protected: Protected
) -> _Scenario:
    values = [a.gender for a in protected.values() if a.gender]
    new_protected: dict[str, ProtectedAttrs] = {}
    for y in youths:
        attrs = protected.get(y.id, ProtectedAttrs())
        if attrs.gender is not None:
            attrs = attrs.model_copy(update={"gender": _others(values, attrs.gender)})
        new_protected[y.id] = attrs
    return _Scenario(
        youths=list(youths),
        commute=dict(commute),
        protected=new_protected,
        id_map={y.id: y.id for y in youths},
    )


def _scenario_corregimiento(
    youths: list[YouthIn], commute: CommuteTable, protected: Protected
) -> _Scenario:
    """Cada joven se muda a un gemelo de su corregimiento: otra etiqueta, mismo traslado."""
    new_commute = dict(commute)
    new_youths: list[YouthIn] = []
    for y in youths:
        twin = f"{y.location_id}{EQUIVALENT_SUFFIX}"
        for (origin, dest), entry in commute.items():
            if origin == y.location_id:
                new_commute[(twin, dest)] = entry
        new_youths.append(y.model_copy(update={"location_id": twin}))
    return _Scenario(
        youths=new_youths,
        commute=new_commute,
        protected={y.id: protected.get(y.id, ProtectedAttrs()) for y in youths},
        id_map={y.id: y.id for y in youths},
    )


def _scenario_edad(youths: list[YouthIn], commute: CommuteTable, protected: Protected) -> _Scenario:
    new_protected: dict[str, ProtectedAttrs] = {}
    for y in youths:
        attrs = protected.get(y.id, ProtectedAttrs())
        if attrs.birth_year is not None:
            shift = -10 if attrs.birth_year >= 2000 else 10
            attrs = attrs.model_copy(update={"birth_year": attrs.birth_year + shift})
        new_protected[y.id] = attrs
    return _Scenario(
        youths=list(youths),
        commute=dict(commute),
        protected=new_protected,
        id_map={y.id: y.id for y in youths},
    )


_SCENARIOS: dict[Variable, Callable[[list[YouthIn], CommuteTable, Protected], _Scenario]] = {
    "nombre": _scenario_nombre,
    "genero": _scenario_genero,
    "corregimiento": _scenario_corregimiento,
    "edad": _scenario_edad,
}

_VARIABLE_LABEL: dict[str, str] = {
    "nombre": "el nombre",
    "genero": "el género",
    "corregimiento": "el corregimiento (equivalente en traslado)",
    "edad": "la edad",
}


def _outcome(result: MatchingResult) -> dict[str, tuple[str | None, float]]:
    by_y = result.by_youth()
    return {yid: (a.posting_id, a.score) for yid, a in by_y.items()}


def _changed(
    base: Mapping[str, tuple[str | None, float]],
    cf: Mapping[str, tuple[str | None, float]],
    id_map: Mapping[str, str],
    youth_ids: Iterable[str],
    score_tol: float,
) -> list[str]:
    cf_by_orig = {id_map[cid]: v for cid, v in cf.items()}
    changed = []
    for yid in sorted(youth_ids):
        b = base.get(yid)
        c = cf_by_orig.get(yid)
        if b == c:
            continue
        if b is not None and c is not None and abs(b[1] - c[1]) <= score_tol:
            continue  # empate de puntaje: no es sesgo
        changed.append(yid)
    return changed


def _check_id(run_key: str, name: str) -> str:
    return str(uuid.uuid5(AUDIT_NAMESPACE, f"{run_key}:{name}"))


# --- Impacto dispar ----------------------------------------------------------


def _age_band(birth_year: int, as_of_year: int) -> str:
    age = as_of_year - birth_year
    return "18-22" if age <= 22 else "23-25" if age <= 25 else "26+"


def _disparate_impact(
    variable: str,
    group_of: Callable[[str], str | None],
    youth_ids: Iterable[str],
    assigned: set[str],
    min_group: int,
    min_assigned: int = 5,
    threshold: float = 0.8,
) -> DisparateImpact:
    totals: dict[str, int] = defaultdict(int)
    hits: dict[str, int] = defaultdict(int)
    for yid in youth_ids:
        g = group_of(yid)
        if g is None:
            continue
        totals[g] += 1
        hits[g] += yid in assigned
    groups = tuple(
        GroupRate(group=g, total=totals[g], assigned=hits[g], rate=hits[g] / totals[g])
        for g in sorted(totals)
    )
    sized = [g for g in groups if g.total >= min_group]
    if len(sized) < 2 or sum(g.assigned for g in sized) < min_assigned:
        return DisparateImpact(
            variable=variable,
            groups=groups,
            ratio=None,
            passed=True,
            note=(
                f"datos insuficientes (≥2 grupos con ≥{min_group} jóvenes y ≥{min_assigned} "
                "asignaciones)"
            ),
        )
    top = max(g.rate for g in sized)
    low = min(g.rate for g in sized)
    ratio = 1.0 if top == 0 else low / top
    return DisparateImpact(variable=variable, groups=groups, ratio=ratio, passed=ratio >= threshold)


# --- API pública -------------------------------------------------------------


def audit_matching(
    youths: Iterable[YouthIn],
    postings: Iterable[PostingIn],
    commute: CommuteTable,
    result: MatchingResult,
    *,
    protected: Protected | None = None,
    variables: Sequence[Variable] = CONTRACT_VARIABLES,
    parity_threshold: float = 0.95,
    score_tol: float = 1e-6,
    solve_fn: SolveFn | None = None,
    run_key: str = "",
    enforce_disparate_impact: bool = False,
    min_group_size: int = 3,
    as_of_year: int = 2026,
) -> AuditReport:
    """Audita una corrida de matching con contrafactuales. Pura: no toca BD ni LLM.

    Re-ejecuta el solver (`solve_fn`, por defecto `solve_matching`) una vez por variable con
    los mismos parámetros de `result`. Si `result` no tiene solución, cada check falla con el
    motivo (política fail-safe: sin evidencia no se declara «sin sesgo»).
    """
    ys = sorted(youths, key=lambda y: y.id)
    ps = sorted(postings, key=lambda p: p.id)
    prot: Protected = protected or {}
    solve = solve_fn or _blind_solve
    params = result.params

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        checks = tuple(
            AuditCheck(
                id=_check_id(run_key, v),
                kind="contrafactual",
                variable=v,
                passed=False,
                findings=(f"No se pudo auditar: el solver terminó en {result.status}.",),
            )
            for v in variables
        )
        return AuditReport(checks=checks, parity_threshold=parity_threshold)

    base = _outcome(result)
    youth_ids = [y.id for y in ys]
    checks: list[AuditCheck] = []
    solves = 0
    for variable in variables:
        scenario = _SCENARIOS[variable](ys, commute, prot)
        cf_result = solve(scenario.youths, ps, scenario.commute, params, scenario.protected)
        solves += 1
        if cf_result.status not in ("OPTIMAL", "FEASIBLE"):
            checks.append(
                AuditCheck(
                    id=_check_id(run_key, variable),
                    kind="contrafactual",
                    variable=variable,
                    passed=False,
                    findings=(f"El solver contrafactual terminó en {cf_result.status}.",),
                )
            )
            continue
        changed = _changed(base, _outcome(cf_result), scenario.id_map, youth_ids, score_tol)
        total = len(youth_ids)
        parity = 1.0 if total == 0 else (total - len(changed)) / total
        findings = [
            f"{total - len(changed)} de {total} jóvenes mantienen su resultado al cambiar "
            f"{_VARIABLE_LABEL[variable]} (paridad {parity:.0%}, umbral {parity_threshold:.0%})."
        ]
        if changed:
            findings.append(
                "Cambian de resultado: "
                + ", ".join(changed[:10])
                + ("…" if len(changed) > 10 else "")
            )
        checks.append(
            AuditCheck(
                id=_check_id(run_key, variable),
                kind="contrafactual",
                variable=variable,
                parity=parity,
                passed=parity >= parity_threshold,
                findings=tuple(findings),
                changed_youth_ids=tuple(changed),
            )
        )

    # Impacto dispar sobre el resultado base.
    assigned = {a.youth_id for a in result.assignments}
    impacts: list[DisparateImpact] = []
    di_inputs: list[tuple[str, Callable[[str], str | None]]] = [
        ("genero", lambda yid: prot.get(yid, ProtectedAttrs()).gender),
        (
            "edad",
            lambda yid: (
                None
                if prot.get(yid, ProtectedAttrs()).birth_year is None
                else _age_band(prot[yid].birth_year or 0, as_of_year)
            ),
        ),
    ]
    for name, group_of in di_inputs:
        di = _disparate_impact(name, group_of, youth_ids, assigned, min_group_size)
        impacts.append(di)
        if di.ratio is not None and not di.passed:
            note = (
                f"Aviso de impacto dispar por {name}: razón de tasas de asignación "
                f"{di.ratio:.2f} < 0,80 (regla de los 4/5)."
            )
            for i, c in enumerate(checks):
                if c.variable == name:
                    updates: dict[str, Any] = {"findings": (*c.findings, note)}
                    if enforce_disparate_impact:
                        updates["passed"] = False
                    checks[i] = c.model_copy(update=updates)
    return AuditReport(
        checks=tuple(checks),
        disparate_impact=tuple(impacts),
        parity_threshold=parity_threshold,
        solves=solves,
    )


def audit_posting(posting_id: str, text: str, *, run_key: str = "") -> AuditCheck:
    """Check `kind="discriminacion"` de una oferta (reglas de `guardrails`, no LLM)."""
    report = detect_discrimination(text)
    return AuditCheck(
        id=_check_id(run_key, f"posting:{posting_id}"),
        kind="discriminacion",
        passed=not report.discriminatory,
        findings=tuple(report.messages()),
        posting_id=posting_id,
    )


def audit_postings(texts: Mapping[str, str], *, run_key: str = "") -> list[AuditCheck]:
    """Un `AuditCheck` de discriminación por oferta, en orden de id."""
    return [audit_posting(pid, texts[pid], run_key=run_key) for pid in sorted(texts)]
