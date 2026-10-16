"""Solver de matching joven ↔ vacante con CP-SAT (OR-Tools).

Interfaz pura y determinista: recibe modelos Pydantic, devuelve `MatchingResult`. No toca la
BD ni el LLM (el adaptador desde SQLAlchemy/seeds vive en `matching_adapter.py`).

Modelo
------
Variables `x[y,p] ∈ {0,1}` solo para pares elegibles (filtro previo por restricciones duras).

Restricciones duras (filtran pares; ver `check_pair`):
- ``habilidades_obligatorias``: el joven tiene cada habilidad con `required=True`
  (se toleran hasta `max_missing_required` faltantes, con penalización).
- ``traslado_max``: minutos de traslado ≤ `max_commute_min` del joven (+ tolerancia penalizada).
- ``presupuesto_transporte``: costo diario ≤ `transport_budget_daily` (+ tolerancia penalizada).
- ``horario``: la disponibilidad cubre al menos `min_schedule_coverage` del horario de la oferta.
- ``salario_minimo``: `salary_max` de la oferta ≥ `min_salary` del joven.
- ``puntaje_minimo``: puntaje ≥ `min_score`.
- ``dato_traslado``: existe el par origen-destino en la matriz.

Restricciones del modelo (con holguras penalizadas, nunca INFEASIBLE):
- ``una_asignacion_por_joven``: Σ_p x[y,p] + sin_asignar[y] = 1.
- ``cupos_oferta``: Σ_y x[y,p] + cupos_vacios[p] = vacantes[p] · `shortlist_factor`.

Objetivo: maximizar Σ x·(puntaje·1000 − penalización_par) − Σ holguras·penalización.

Puntaje (0..1) = suma ponderada de cobertura de habilidades, traslado, costo, horario y
salario. `display_name` y `gender` nunca entran al solver: `YouthIn` no los tiene.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable, Mapping
from typing import Literal

from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict, Field, model_validator

Day = Literal["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
SolverStatus = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT"]

SCALE = 1000  # puntajes 0..1 → enteros 0..1000 para CP-SAT

# Nombres de restricciones (claves estables para el auditor y la UI).
C_REQUIRED = "habilidades_obligatorias"
C_COMMUTE = "traslado_max"
C_BUDGET = "presupuesto_transporte"
C_SCHEDULE = "horario"
C_SALARY = "salario_minimo"
C_MIN_SCORE = "puntaje_minimo"
C_COMMUTE_DATA = "dato_traslado"
C_ONE_PER_YOUTH = "una_asignacion_por_joven"
C_CAPACITY = "cupos_oferta"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Entrada -----------------------------------------------------------------


class TimeSlot(_Frozen):
    day: Day
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @property
    def start_min(self) -> int:
        h, m = self.start.split(":")
        return int(h) * 60 + int(m)

    @property
    def end_min(self) -> int:
        h, m = self.end.split(":")
        return int(h) * 60 + int(m)


class YouthIn(_Frozen):
    """Joven tal como lo ve el solver (sin nombre ni género)."""

    id: str
    location_id: str
    max_commute_min: int = Field(ge=0)
    transport_budget_daily: float = Field(ge=0)
    availability: tuple[TimeSlot, ...] = ()
    min_salary: float | None = Field(default=None, ge=0)
    skills: dict[str, int] = Field(default_factory=dict, description="skill_id → nivel 1..3")


class Requirement(_Frozen):
    skill_id: str
    weight: int = Field(default=1, ge=1, le=3)
    required: bool = True


class PostingIn(_Frozen):
    id: str
    location_id: str | None = None  # None = sin lugar fijo (traslado 0)
    schedule: tuple[TimeSlot, ...] = ()
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    vacancies: int = Field(default=1, ge=1)
    requirements: tuple[Requirement, ...] = ()


class CommuteEntry(_Frozen):
    minutes: int = Field(ge=0)
    cost_daily: float = Field(ge=0)


CommuteTable = Mapping[tuple[str, str], CommuteEntry]


class ScoreWeights(_Frozen):
    skill_coverage: float = 0.5
    commute: float = 0.15
    cost: float = 0.1
    schedule: float = 0.15
    salary: float = 0.1

    @model_validator(mode="after")
    def _positive_total(self) -> ScoreWeights:
        if self.total <= 0:
            raise ValueError("la suma de pesos del puntaje debe ser > 0")
        return self

    @property
    def total(self) -> float:
        return self.skill_coverage + self.commute + self.cost + self.schedule + self.salary


class MatchingParams(_Frozen):
    time_limit_s: float = Field(default=5.0, gt=0, le=60)
    seed: int = 42
    num_workers: int = Field(default=1, ge=1, le=8, description="1 = determinista")
    weights: ScoreWeights = ScoreWeights()
    level_factor: dict[int, float] = Field(default_factory=lambda: {1: 0.6, 2: 0.8, 3: 1.0})
    # Tolerancias de restricciones duras (holgura penalizada); 0 = estricta.
    commute_tolerance_min: int = Field(default=0, ge=0)
    budget_tolerance: float = Field(default=0.0, ge=0)
    max_missing_required: int = Field(default=0, ge=0)
    min_schedule_coverage: float = Field(default=1.0, ge=0, le=1)
    min_score: float = Field(default=0.0, ge=0, le=1)
    # Penalizaciones (en unidades de puntaje ×1000).
    penalty_commute_per_min: int = Field(default=10, ge=0)
    penalty_budget_per_balboa: int = Field(default=200, ge=0)
    penalty_missing_required: int = Field(default=300, ge=0)
    penalty_unassigned_youth: int = Field(default=100, ge=0)
    penalty_unfilled_vacancy: int = Field(default=100, ge=0)
    # Tamaño acotado.
    shortlist_factor: int = Field(default=1, ge=1, le=5)
    max_youths: int = Field(default=200, ge=1)
    max_postings: int = Field(default=100, ge=1)
    max_pairs_per_youth: int = Field(default=15, ge=1)

    @classmethod
    def relaxed(cls, **overrides: object) -> MatchingParams:
        """Preset del demo: tolera 1 habilidad obligatoria faltante, 15 min y B/. 1.00 de
        exceso, todo penalizado (queda registrado como holgura en cada asignación)."""
        base: dict[str, object] = {
            "max_missing_required": 1,
            "commute_tolerance_min": 15,
            "budget_tolerance": 1.0,
        }
        return cls.model_validate(base | overrides)


# --- Salida ------------------------------------------------------------------


class ScoreBreakdown(_Frozen):
    skill_coverage: float
    commute: float
    cost: float
    schedule: float
    salary: float
    missing_skills: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()
    penalty: float = 0.0  # en unidades de puntaje (0..1)


class ConstraintCheck(_Frozen):
    name: str
    ok: bool
    value: float | None = None
    limit: float | None = None
    slack: float = 0.0  # cuánto se excede el límite (0 si se cumple estrictamente)
    binding: bool = False  # la restricción está en su límite (activa)


class SlackUsed(_Frozen):
    constraint: str
    amount: float
    penalty: int
    subject_id: str | None = None


class Assignment(_Frozen):
    youth_id: str
    posting_id: str
    score: float
    breakdown: ScoreBreakdown
    constraints: tuple[ConstraintCheck, ...]
    slacks: tuple[SlackUsed, ...] = ()

    @property
    def active_constraints(self) -> list[str]:
        return [c.name for c in self.constraints if c.binding or c.slack > 0]

    def constraint(self, name: str) -> ConstraintCheck:
        return next(c for c in self.constraints if c.name == name)


class PairEvaluation(_Frozen):
    youth_id: str
    posting_id: str
    eligible: bool
    score: float
    breakdown: ScoreBreakdown
    constraints: tuple[ConstraintCheck, ...]
    penalty: int  # ×1000

    @property
    def violated(self) -> list[str]:
        return [c.name for c in self.constraints if not c.ok]


class UnassignedYouth(_Frozen):
    youth_id: str
    eligible_postings: int
    reasons: dict[str, int] = Field(
        default_factory=dict, description="restricción → nº de ofertas que la incumplen"
    )


class MatchingResult(_Frozen):
    status: SolverStatus
    solve_ms: int
    objective: float | None
    assignments: tuple[Assignment, ...]
    unassigned: tuple[UnassignedYouth, ...]
    unfilled: dict[str, int]  # posting_id → cupos vacíos
    slacks: tuple[SlackUsed, ...]
    eligible_pairs: int
    params: MatchingParams

    def by_youth(self) -> dict[str, Assignment]:
        return {a.youth_id: a for a in self.assignments}


# --- Evaluación de un par ----------------------------------------------------


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def schedule_coverage(availability: Iterable[TimeSlot], schedule: Iterable[TimeSlot]) -> float:
    """Fracción de minutos del horario de la oferta cubiertos por la disponibilidad."""
    sched = list(schedule)
    total = sum(s.end_min - s.start_min for s in sched)
    if total <= 0:
        return 1.0
    by_day: dict[str, list[tuple[int, int]]] = {}
    for a in availability:
        by_day.setdefault(a.day, []).append((a.start_min, a.end_min))
    covered = 0
    for s in sched:
        # Unir franjas del mismo día y medir la intersección con la franja de la oferta.
        intervals = sorted(by_day.get(s.day, []))
        merged: list[list[int]] = []
        for a, b in intervals:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            covered += max(0, min(b, s.end_min) - max(a, s.start_min))
    return covered / total


def _salary_component(youth: YouthIn, posting: PostingIn) -> tuple[float, bool]:
    if youth.min_salary is None or (posting.salary_min is None and posting.salary_max is None):
        return 1.0, True
    lo = posting.salary_min if posting.salary_min is not None else posting.salary_max
    hi = posting.salary_max if posting.salary_max is not None else posting.salary_min
    assert lo is not None and hi is not None
    if lo >= youth.min_salary:
        return 1.0, True
    if hi < youth.min_salary:
        return 0.0, False
    # El mínimo del joven cae dentro del rango: 0.5..1 según cuánto del rango lo cumple.
    return 0.5 + 0.5 * (hi - youth.min_salary) / (hi - lo), True


def check_pair(
    youth: YouthIn, posting: PostingIn, commute: CommuteTable, params: MatchingParams
) -> PairEvaluation:
    """Evalúa un par: puntaje desglosado + cada restricción dura (con holgura si aplica)."""
    w = params.weights
    checks: list[ConstraintCheck] = []
    penalty = 0

    # Habilidades
    req_w = sum(r.weight for r in posting.requirements)
    got = 0.0
    missing: list[str] = []
    missing_req: list[str] = []
    for r in posting.requirements:
        lvl = youth.skills.get(r.skill_id)
        if lvl is None:
            missing.append(r.skill_id)
            if r.required:
                missing_req.append(r.skill_id)
        else:
            got += r.weight * params.level_factor.get(lvl, 1.0)
    skill_cov = got / req_w if req_w else 1.0
    n_miss = len(missing_req)
    req_ok = n_miss <= params.max_missing_required
    if req_ok and n_miss:
        penalty += n_miss * params.penalty_missing_required
    checks.append(
        ConstraintCheck(
            name=C_REQUIRED,
            ok=req_ok,
            value=n_miss,
            limit=0,
            slack=float(n_miss),
        )
    )

    # Traslado y costo
    if posting.location_id is None:
        entry: CommuteEntry | None = CommuteEntry(minutes=0, cost_daily=0.0)
    else:
        entry = commute.get((youth.location_id, posting.location_id))
    checks.append(ConstraintCheck(name=C_COMMUTE_DATA, ok=entry is not None))
    if entry is None:
        minutes, cost = math.inf, math.inf
        commute_score = cost_score = 0.0
        checks.append(ConstraintCheck(name=C_COMMUTE, ok=False, limit=youth.max_commute_min))
        checks.append(ConstraintCheck(name=C_BUDGET, ok=False, limit=youth.transport_budget_daily))
    else:
        minutes, cost = entry.minutes, entry.cost_daily
        over_min = max(0, minutes - youth.max_commute_min)
        commute_ok = over_min <= params.commute_tolerance_min
        if commute_ok and over_min:
            penalty += over_min * params.penalty_commute_per_min
        checks.append(
            ConstraintCheck(
                name=C_COMMUTE,
                ok=commute_ok,
                value=minutes,
                limit=youth.max_commute_min,
                slack=float(over_min),
                binding=minutes == youth.max_commute_min,
            )
        )
        over_cost = round(max(0.0, cost - youth.transport_budget_daily), 2)
        budget_ok = over_cost <= params.budget_tolerance + 1e-9
        if budget_ok and over_cost:
            penalty += math.ceil(over_cost * params.penalty_budget_per_balboa)
        checks.append(
            ConstraintCheck(
                name=C_BUDGET,
                ok=budget_ok,
                value=cost,
                limit=youth.transport_budget_daily,
                slack=over_cost,
                binding=abs(cost - youth.transport_budget_daily) < 1e-9,
            )
        )
        commute_score = (
            _clamp01(1 - minutes / youth.max_commute_min) if youth.max_commute_min else 0.0
        )
        if youth.transport_budget_daily > 0:
            cost_score = _clamp01(1 - cost / youth.transport_budget_daily)
        else:
            cost_score = 1.0 if cost == 0 else 0.0

    # Horario
    cov = schedule_coverage(youth.availability, posting.schedule)
    checks.append(
        ConstraintCheck(
            name=C_SCHEDULE,
            ok=cov + 1e-9 >= params.min_schedule_coverage,
            value=round(cov, 4),
            limit=params.min_schedule_coverage,
            binding=abs(cov - params.min_schedule_coverage) < 1e-9,
        )
    )

    # Salario
    salary_score, salary_ok = _salary_component(youth, posting)
    checks.append(
        ConstraintCheck(
            name=C_SALARY,
            ok=salary_ok,
            value=posting.salary_max,
            limit=youth.min_salary,
            binding=salary_ok
            and youth.min_salary is not None
            and posting.salary_max is not None
            and abs(posting.salary_max - youth.min_salary) < 1e-9,
        )
    )

    score = (
        w.skill_coverage * skill_cov
        + w.commute * commute_score
        + w.cost * cost_score
        + w.schedule * cov
        + w.salary * salary_score
    ) / w.total
    score = round(score, 4)
    checks.append(
        ConstraintCheck(
            name=C_MIN_SCORE,
            ok=score + 1e-9 >= params.min_score,
            value=score,
            limit=params.min_score,
        )
    )

    breakdown = ScoreBreakdown(
        skill_coverage=round(skill_cov, 4),
        commute=round(commute_score, 4),
        cost=round(cost_score, 4),
        schedule=round(cov, 4),
        salary=round(salary_score, 4),
        missing_skills=tuple(missing),
        missing_required=tuple(missing_req),
        penalty=round(penalty / SCALE, 4),
    )
    return PairEvaluation(
        youth_id=youth.id,
        posting_id=posting.id,
        eligible=all(c.ok for c in checks),
        score=score,
        breakdown=breakdown,
        constraints=tuple(checks),
        penalty=penalty,
    )


def _pair_slacks(ev: PairEvaluation, params: MatchingParams) -> tuple[SlackUsed, ...]:
    out = []
    for c in ev.constraints:
        if c.slack <= 0:
            continue
        if c.name == C_COMMUTE:
            pen = int(c.slack) * params.penalty_commute_per_min
        elif c.name == C_BUDGET:
            pen = math.ceil(c.slack * params.penalty_budget_per_balboa)
        elif c.name == C_REQUIRED:
            pen = int(c.slack) * params.penalty_missing_required
        else:
            continue
        out.append(SlackUsed(constraint=c.name, amount=c.slack, penalty=pen))
    return tuple(out)


# --- Solver ------------------------------------------------------------------

_STATUS: dict[int, SolverStatus] = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "INFEASIBLE",
    cp_model.UNKNOWN: "TIMEOUT",
}


def solve_matching(
    youths: Iterable[YouthIn],
    postings: Iterable[PostingIn],
    commute: CommuteTable,
    params: MatchingParams | None = None,
) -> MatchingResult:
    """Asigna cada joven a lo sumo a una vacante maximizando el puntaje ponderado.

    Determinista: ordena por id, un solo worker y semilla fija. Nunca devuelve INFEASIBLE
    por falta de candidatos: los cupos vacíos y los jóvenes sin asignar son holguras.
    """
    params = params or MatchingParams()
    ys = sorted(youths, key=lambda y: y.id)
    ps = sorted(postings, key=lambda p: p.id)
    if len(ys) > params.max_youths or len(ps) > params.max_postings:
        raise ValueError(
            f"Tamaño fuera de límite: {len(ys)} jóvenes (máx. {params.max_youths}), "
            f"{len(ps)} ofertas (máx. {params.max_postings})"
        )
    if len({y.id for y in ys}) != len(ys) or len({p.id for p in ps}) != len(ps):
        raise ValueError("ids de jóvenes u ofertas repetidos")

    t0 = time.perf_counter()
    evals: dict[tuple[str, str], PairEvaluation] = {}
    reasons: dict[str, dict[str, int]] = {}
    for y in ys:
        cands: list[PairEvaluation] = []
        rs: dict[str, int] = {}
        for p in ps:
            ev = check_pair(y, p, commute, params)
            if ev.eligible:
                cands.append(ev)
            else:
                for name in ev.violated:
                    rs[name] = rs.get(name, 0) + 1
        # Cota de tamaño: solo los mejores pares por joven (desempate por id → determinista).
        cands.sort(key=lambda e: (-(e.score * SCALE - e.penalty), e.posting_id))
        for ev in cands[: params.max_pairs_per_youth]:
            evals[(y.id, ev.posting_id)] = ev
        reasons[y.id] = rs

    model = cp_model.CpModel()
    x = {k: model.new_bool_var(f"x_{k[0]}_{k[1]}") for k in evals}
    unassigned = {y.id: model.new_bool_var(f"u_{y.id}") for y in ys}
    capacity = {p.id: p.vacancies * params.shortlist_factor for p in ps}
    unfilled = {p.id: model.new_int_var(0, capacity[p.id], f"v_{p.id}") for p in ps}

    by_y: dict[str, list[cp_model.IntVar]] = {y.id: [] for y in ys}
    by_p: dict[str, list[cp_model.IntVar]] = {p.id: [] for p in ps}
    for (yid, pid), var in x.items():
        by_y[yid].append(var)
        by_p[pid].append(var)
    for y in ys:
        model.add(sum(by_y[y.id]) + unassigned[y.id] == 1)
    for p in ps:
        model.add(sum(by_p[p.id]) + unfilled[p.id] == capacity[p.id])

    model.maximize(
        sum(x[k] * (round(ev.score * SCALE) - ev.penalty) for k, ev in evals.items())
        - params.penalty_unassigned_youth * sum(unassigned.values())
        - params.penalty_unfilled_vacancy * sum(unfilled.values())
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = params.time_limit_s
    solver.parameters.random_seed = params.seed
    solver.parameters.num_workers = params.num_workers
    code = solver.solve(model)
    status = _STATUS.get(code, "TIMEOUT")
    solve_ms = round((time.perf_counter() - t0) * 1000)

    if status not in ("OPTIMAL", "FEASIBLE"):
        return MatchingResult(
            status=status,
            solve_ms=solve_ms,
            objective=None,
            assignments=(),
            unassigned=tuple(
                UnassignedYouth(
                    youth_id=y.id,
                    eligible_postings=sum(1 for k in evals if k[0] == y.id),
                    reasons=reasons[y.id],
                )
                for y in ys
            ),
            unfilled=dict(capacity),
            slacks=(),
            eligible_pairs=len(evals),
            params=params,
        )

    filled = {p.id: capacity[p.id] - solver.value(unfilled[p.id]) for p in ps}
    assignments: list[Assignment] = []
    all_slacks: list[SlackUsed] = []
    for (yid, pid), ev in evals.items():
        if not solver.value(x[(yid, pid)]):
            continue
        cap_check = ConstraintCheck(
            name=C_CAPACITY,
            ok=True,
            value=filled[pid],
            limit=capacity[pid],
            binding=filled[pid] == capacity[pid],
        )
        one_check = ConstraintCheck(name=C_ONE_PER_YOUTH, ok=True, value=1, limit=1, binding=True)
        slacks = tuple(
            s.model_copy(update={"subject_id": f"{yid}:{pid}"}) for s in _pair_slacks(ev, params)
        )
        all_slacks.extend(slacks)
        assignments.append(
            Assignment(
                youth_id=yid,
                posting_id=pid,
                score=ev.score,
                breakdown=ev.breakdown,
                constraints=(*ev.constraints, cap_check, one_check),
                slacks=slacks,
            )
        )

    un_list: list[UnassignedYouth] = []
    for y in ys:
        if solver.value(unassigned[y.id]):
            un_list.append(
                UnassignedYouth(
                    youth_id=y.id,
                    eligible_postings=sum(1 for k in evals if k[0] == y.id),
                    reasons=reasons[y.id],
                )
            )
            all_slacks.append(
                SlackUsed(
                    constraint=C_ONE_PER_YOUTH,
                    amount=1,
                    penalty=params.penalty_unassigned_youth,
                    subject_id=y.id,
                )
            )
    unfilled_out = {p.id: int(solver.value(unfilled[p.id])) for p in ps}
    for pid, n in unfilled_out.items():
        if n:
            all_slacks.append(
                SlackUsed(
                    constraint=C_CAPACITY,
                    amount=n,
                    penalty=n * params.penalty_unfilled_vacancy,
                    subject_id=pid,
                )
            )

    assignments.sort(key=lambda a: (-a.score, a.youth_id))
    return MatchingResult(
        status=status,
        solve_ms=solve_ms,
        objective=solver.objective_value / SCALE,
        assignments=tuple(assignments),
        unassigned=tuple(un_list),
        unfilled=unfilled_out,
        slacks=tuple(all_slacks),
        eligible_pairs=len(evals),
        params=params,
    )
