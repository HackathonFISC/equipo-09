"""Solver de ruta de formación (MIP con OR-Tools CP-SAT) con respaldo greedy determinista.

Dado un joven, las ofertas publicadas y el catálogo de cursos/sesiones, elige qué sesiones
tomar para **maximizar las vacantes desbloqueadas**: ofertas que hoy el joven no puede cubrir
solo por habilidades obligatorias faltantes y que, tras la formación, cumplen todas las
restricciones duras del matching (traslado, presupuesto, horario, salario).

Modelo (todas las restricciones tienen un test unitario):

- ``una_sesion_por_curso``: Σ_s c[s] ≤ 1 por curso.
- ``cupo_sesion``: solo sesiones con ``seats_total - seats_taken ≥ 1`` (filtro previo).
- ``horario_joven``: la sesión cae dentro de la disponibilidad del joven (filtro previo;
  cobertura mínima ``min_session_coverage``).
- ``sin_solape``: dos sesiones elegidas no se pisan en día y hora.
- ``traslado_max`` / ``presupuesto_transporte``: del hogar al centro (matriz de traslado), con
  tolerancias penalizadas (holgura) en vez de descartar de golpe.
- ``dato_traslado``: debe existir el par hogar-centro.
- ``presupuesto_total``: matrículas + transporte estimado ≤ ``max_total_cost``.
- ``max_cursos`` y ``max_horas``: tamaño acotado de la ruta.
- Enlace: ``u[p] ≤ cov[k]`` para cada habilidad k de la brecha de p;
  ``cov[k] ≤ Σ c[s]`` de las sesiones que enseñan k.

Objetivo: Σ u[p]·vacantes[p]·W + progreso parcial − costo − horas − holguras. El plan vacío
siempre es factible, así que nunca hay INFEASIBLE por falta de opciones.

Respaldo: ``method="auto"`` intenta el MIP y, si no devuelve solución en el límite de tiempo,
corre el greedy (mayor ganancia marginal por costo, desempate por id) con la misma interfaz.

Firmas públicas::

    solve_training(youth: YouthIn, postings: Iterable[PostingIn], courses: Iterable[CourseIn],
                   commute: CommuteTable, params: TrainingParams | None = None
                   ) -> TrainingPlanResult
    solve_training_greedy(...)  # misma firma; sin OR-Tools
    TrainingPlanResult.to_api(plan_id: str, youth_id: str | None = None) -> dict
        # camelCase compatible con `TrainingPlan` de openapi.yaml
    TrainingPlanResult.explanation_facts() -> str   # texto determinista; el LLM solo lo verbaliza
    # Adaptadores en training_adapter.py: courses_from_seed(bundle), load_courses(session)
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from datetime import date
from typing import Any, Literal

from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict, Field

from puente_api.solvers.matching import (
    C_REQUIRED,
    CommuteTable,
    MatchingParams,
    PostingIn,
    TimeSlot,
    YouthIn,
    check_pair,
    schedule_coverage,
)

TrainingStatus = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT"]
Method = Literal["mip", "greedy"]

# Nombres estables de restricciones.
T_ONE_SESSION = "una_sesion_por_curso"
T_SEATS = "cupo_sesion"
T_AVAILABILITY = "horario_joven"
T_OVERLAP = "sin_solape"
T_COMMUTE = "traslado_max"
T_BUDGET_DAILY = "presupuesto_transporte"
T_COMMUTE_DATA = "dato_traslado"
T_TOTAL_COST = "presupuesto_total"
T_MAX_COURSES = "max_cursos"
T_MAX_HOURS = "max_horas"

W_VACANCY = 1000  # una vacante desbloqueada
W_PROGRESS = 40  # cada habilidad de brecha cubierta aunque aún no desbloquee
W_COURSE = 20  # penaliza cursos redundantes
CENTS = 100


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Entrada -----------------------------------------------------------------


class SessionIn(_Frozen):
    id: str
    start_date: date
    schedule: tuple[TimeSlot, ...]
    seats_total: int = Field(ge=1)
    seats_taken: int = Field(default=0, ge=0)

    @property
    def seats_left(self) -> int:
        return max(0, self.seats_total - self.seats_taken)


class CourseIn(_Frozen):
    id: str
    title: str
    center_id: str
    center_location_id: str
    hours: int = Field(ge=1)
    cost: float = Field(default=0.0, ge=0)
    skill_ids: tuple[str, ...]
    sessions: tuple[SessionIn, ...]


class TrainingParams(_Frozen):
    method: Literal["auto", "mip", "greedy"] = "auto"
    time_limit_s: float = Field(default=5.0, gt=0, le=60)
    seed: int = 42
    max_total_cost: float = Field(default=100.0, ge=0, description="matrículas + transporte, B/.")
    max_courses: int = Field(default=3, ge=1, le=6)
    max_total_hours: int = Field(default=240, ge=1)
    min_session_coverage: float = Field(default=1.0, ge=0, le=1)
    commute_tolerance_min: int = Field(default=0, ge=0)
    budget_tolerance: float = Field(default=0.0, ge=0)
    penalty_commute_per_min: int = Field(default=5, ge=0)
    penalty_budget_per_balboa: int = Field(default=100, ge=0)
    penalty_cost_per_balboa: int = Field(default=4, ge=0)
    penalty_per_hour: int = Field(default=1, ge=0)
    acquired_level: int = Field(default=2, ge=1, le=3)
    max_gap: int = Field(default=3, ge=1, description="habilidades faltantes máx. por oferta")
    max_sessions: int = Field(default=200, ge=1, description="tamaño acotado del MIP")
    max_postings: int = Field(default=100, ge=1)


# --- Salida ------------------------------------------------------------------


class PlanItem(_Frozen):
    order: int
    course_id: str
    course_title: str
    center_id: str
    session: SessionIn
    hours: int
    fee: float
    commute_min: int
    commute_cost_daily: float
    transport_cost: float
    skills_covered: tuple[str, ...]  # solo habilidades de brecha que aporta

    @property
    def cost(self) -> float:
        return round(self.fee + self.transport_cost, 2)


class UnlockedPosting(_Frozen):
    posting_id: str
    vacancies: int
    gap_skills: tuple[str, ...]


class ConstraintReport(_Frozen):
    name: str
    ok: bool
    value: float | None = None
    limit: float | None = None
    binding: bool = False


class SlackUsed(_Frozen):
    constraint: str
    session_id: str
    amount: float
    penalty: int


class TrainingPlanResult(_Frozen):
    status: TrainingStatus
    method: Method
    fallback_reason: str | None = None
    solve_ms: int
    objective: float | None
    items: tuple[PlanItem, ...]
    fees_cost: float
    transport_cost: float
    total_hours: int
    unlocked: tuple[UnlockedPosting, ...]
    already_eligible: tuple[str, ...]
    blocked_other: dict[str, tuple[str, ...]]  # posting → restricciones no-habilidad que fallan
    unreachable: tuple[str, ...]  # brecha sin curso factible
    skills_acquired: tuple[str, ...]
    constraints: tuple[ConstraintReport, ...]
    slacks: tuple[SlackUsed, ...]
    candidate_sessions: int
    params: TrainingParams

    @property
    def total_cost(self) -> float:
        return round(self.fees_cost + self.transport_cost, 2)

    @property
    def unlocked_vacancies(self) -> int:
        return sum(u.vacancies for u in self.unlocked)

    def explanation_facts(self) -> str:
        """Resumen determinista en español (el LLM puede reformularlo, no cambiar cifras)."""
        if not self.items:
            if self.unlocked or self.unreachable or self.blocked_other:
                return (
                    "No se encontró una ruta de formación factible con las restricciones "
                    "actuales (cupos, horario, traslado y presupuesto)."
                )
            return "No hay brechas de habilidades que cerrar con la formación disponible."
        parts = []
        for it in self.items:
            days = "/".join(sorted({s.day for s in it.session.schedule}))
            parts.append(
                f"{it.course_title} (inicia {it.session.start_date.isoformat()}, {days}, "
                f"{it.hours} h, traslado {it.commute_min} min)"
            )
        return (
            f"Ruta de {len(self.items)} curso(s): {'; '.join(parts)}. "
            f"Costo total estimado B/. {self.total_cost:.2f}. "
            f"Desbloquea {len(self.unlocked)} oferta(s) con {self.unlocked_vacancies} vacante(s)."
        )

    def to_api(self, plan_id: str, youth_id: str | None = None) -> dict[str, Any]:
        """Schema `TrainingPlan` de openapi.yaml (camelCase)."""
        return {
            "id": plan_id,
            "youthId": youth_id or "",
            "items": [
                {
                    "courseTitle": it.course_title,
                    "session": {
                        "id": it.session.id,
                        "schedule": [s.model_dump() for s in it.session.schedule],
                        "startDate": it.session.start_date.isoformat(),
                        "seatsTotal": it.session.seats_total,
                        "seatsTaken": it.session.seats_taken,
                    },
                    "commuteMin": it.commute_min,
                }
                for it in self.items
            ],
            "totalCost": self.total_cost,
            "unlockedPostings": len(self.unlocked),
            "explanation": self.explanation_facts(),
        }


# --- Preparación: brechas y sesiones candidatas ------------------------------


class _Cand(BaseModel):
    """Sesión candidata ya filtrada por restricciones duras."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    course: CourseIn
    session: SessionIn
    commute_min: int
    commute_cost: float
    transport_cost: float
    fee: float
    cost_cents: int
    slack_penalty: int
    slacks: tuple[SlackUsed, ...]
    teaches: frozenset[str]  # habilidades de brecha que enseña

    @property
    def key(self) -> str:
        return self.session.id


def _meetings(course: CourseIn, session: SessionIn) -> int:
    """Número estimado de encuentros: horas del curso / duración media de una franja."""
    slots = [s.end_min - s.start_min for s in session.schedule]
    per_meeting = (sum(slots) / len(slots)) / 60 if slots else 1.0
    return max(1, math.ceil(course.hours / per_meeting))


def _overlaps(a: SessionIn, b: SessionIn) -> bool:
    for x in a.schedule:
        for y in b.schedule:
            if x.day == y.day and x.start_min < y.end_min and y.start_min < x.end_min:
                return True
    return False


def _prepare(
    youth: YouthIn,
    postings: list[PostingIn],
    courses: list[CourseIn],
    commute: CommuteTable,
    params: TrainingParams,
) -> tuple[list[_Cand], dict[str, tuple[PostingIn, frozenset[str]]], dict[str, Any]]:
    """Brechas por oferta y sesiones candidatas. Devuelve (cands, gaps, info)."""
    strict = MatchingParams(max_missing_required=99)
    gaps: dict[str, tuple[PostingIn, frozenset[str]]] = {}
    already: list[str] = []
    blocked: dict[str, tuple[str, ...]] = {}
    for p in postings:
        ev = check_pair(youth, p, commute, strict)
        other = tuple(n for n in ev.violated if n != C_REQUIRED)
        if other:
            blocked[p.id] = other
            continue
        gap = frozenset(ev.breakdown.missing_required)
        if not gap:
            already.append(p.id)
        elif len(gap) <= params.max_gap:
            gaps[p.id] = (p, gap)
    gap_skills = frozenset().union(*(g for _, g in gaps.values())) if gaps else frozenset()

    cands: list[_Cand] = []
    for c in courses:
        teaches = frozenset(c.skill_ids) & gap_skills
        if not teaches:
            continue
        entry = commute.get((youth.location_id, c.center_location_id))
        if entry is None:
            continue
        over_min = max(0, entry.minutes - youth.max_commute_min)
        over_cost = round(max(0.0, entry.cost_daily - youth.transport_budget_daily), 2)
        if over_min > params.commute_tolerance_min or over_cost > params.budget_tolerance + 1e-9:
            continue
        for s in c.sessions:
            if s.seats_left < 1:
                continue
            if (
                schedule_coverage(youth.availability, s.schedule) + 1e-9
                < params.min_session_coverage
            ):
                continue
            slacks: list[SlackUsed] = []
            penalty = 0
            if over_min:
                pen = over_min * params.penalty_commute_per_min
                slacks.append(
                    SlackUsed(constraint=T_COMMUTE, session_id=s.id, amount=over_min, penalty=pen)
                )
                penalty += pen
            if over_cost:
                pen = math.ceil(over_cost * params.penalty_budget_per_balboa)
                slacks.append(
                    SlackUsed(
                        constraint=T_BUDGET_DAILY, session_id=s.id, amount=over_cost, penalty=pen
                    )
                )
                penalty += pen
            transport = round(entry.cost_daily * _meetings(c, s), 2)
            cands.append(
                _Cand(
                    course=c,
                    session=s,
                    commute_min=entry.minutes,
                    commute_cost=entry.cost_daily,
                    transport_cost=transport,
                    fee=c.cost,
                    cost_cents=round((c.cost + transport) * CENTS),
                    slack_penalty=penalty,
                    slacks=tuple(slacks),
                    teaches=teaches,
                )
            )
    cands.sort(key=lambda k: k.key)
    # Tamaño acotado: si hay demasiadas, se conservan las de menor costo/penalización.
    if len(cands) > params.max_sessions:
        cands = sorted(cands, key=lambda k: (k.cost_cents + k.slack_penalty, k.key))[
            : params.max_sessions
        ]
        cands.sort(key=lambda k: k.key)

    reachable = frozenset().union(*(k.teaches for k in cands)) if cands else frozenset()
    unreachable = tuple(sorted(pid for pid, (_, g) in gaps.items() if not g <= reachable))
    info = {"already": tuple(sorted(already)), "blocked": blocked, "unreachable": unreachable}
    return cands, gaps, info


def _plan_value(
    chosen: list[_Cand], gaps: dict[str, tuple[PostingIn, frozenset[str]]], params: TrainingParams
) -> tuple[int, list[str], frozenset[str]]:
    """Valor entero del plan (misma función que el objetivo del MIP) y ofertas desbloqueadas."""
    cov = frozenset().union(*(k.teaches for k in chosen)) if chosen else frozenset()
    unlocked = sorted(pid for pid, (_, g) in gaps.items() if g <= cov)
    value = sum(gaps[pid][0].vacancies * W_VACANCY for pid in unlocked)
    value += W_PROGRESS * len(cov)
    value -= sum(
        k.cost_cents // CENTS * params.penalty_cost_per_balboa
        + k.course.hours * params.penalty_per_hour
        + W_COURSE
        + k.slack_penalty
        for k in chosen
    )
    return value, unlocked, cov


def _feasible_to_add(chosen: list[_Cand], new: _Cand, params: TrainingParams) -> bool:
    if len(chosen) + 1 > params.max_courses:
        return False
    if any(k.course.id == new.course.id for k in chosen):
        return False
    if any(_overlaps(k.session, new.session) for k in chosen):
        return False
    cost = sum(k.cost_cents for k in chosen) + new.cost_cents
    if cost > round(params.max_total_cost * CENTS):
        return False
    hours = sum(k.course.hours for k in chosen) + new.course.hours
    return hours <= params.max_total_hours


# --- Resultado ---------------------------------------------------------------


def _build_result(
    *,
    status: TrainingStatus,
    method: Method,
    chosen: list[_Cand],
    gaps: dict[str, tuple[PostingIn, frozenset[str]]],
    info: dict[str, Any],
    cands: list[_Cand],
    params: TrainingParams,
    solve_ms: int,
    objective: float | None,
    fallback_reason: str | None = None,
) -> TrainingPlanResult:
    chosen = sorted(chosen, key=lambda k: (k.session.start_date, k.key))
    _, unlocked_ids, cov = _plan_value(chosen, gaps, params)
    items = tuple(
        PlanItem(
            order=i + 1,
            course_id=k.course.id,
            course_title=k.course.title,
            center_id=k.course.center_id,
            session=k.session,
            hours=k.course.hours,
            fee=k.fee,
            commute_min=k.commute_min,
            commute_cost_daily=k.commute_cost,
            transport_cost=k.transport_cost,
            skills_covered=tuple(sorted(k.teaches)),
        )
        for i, k in enumerate(chosen)
    )
    fees = round(sum(k.fee for k in chosen), 2)
    transport = round(sum(k.transport_cost for k in chosen), 2)
    hours = sum(k.course.hours for k in chosen)
    total = fees + transport
    reports = (
        ConstraintReport(
            name=T_ONE_SESSION,
            ok=len({k.course.id for k in chosen}) == len(chosen),
            value=len(chosen),
            limit=len(chosen),
        ),
        ConstraintReport(
            name=T_OVERLAP,
            ok=not any(
                _overlaps(a.session, b.session)
                for i, a in enumerate(chosen)
                for b in chosen[i + 1 :]
            ),
        ),
        ConstraintReport(
            name=T_TOTAL_COST,
            ok=total <= params.max_total_cost + 1e-9,
            value=round(total, 2),
            limit=params.max_total_cost,
            binding=abs(total - params.max_total_cost) < 0.005,
        ),
        ConstraintReport(
            name=T_MAX_COURSES,
            ok=len(chosen) <= params.max_courses,
            value=len(chosen),
            limit=params.max_courses,
            binding=len(chosen) == params.max_courses,
        ),
        ConstraintReport(
            name=T_MAX_HOURS,
            ok=hours <= params.max_total_hours,
            value=hours,
            limit=params.max_total_hours,
            binding=hours == params.max_total_hours,
        ),
        ConstraintReport(
            name=T_SEATS, ok=all(k.session.seats_left >= 1 for k in chosen), value=len(chosen)
        ),
    )
    return TrainingPlanResult(
        status=status,
        method=method,
        fallback_reason=fallback_reason,
        solve_ms=solve_ms,
        objective=objective,
        items=items,
        fees_cost=fees,
        transport_cost=transport,
        total_hours=hours,
        unlocked=tuple(
            UnlockedPosting(
                posting_id=pid,
                vacancies=gaps[pid][0].vacancies,
                gap_skills=tuple(sorted(gaps[pid][1])),
            )
            for pid in unlocked_ids
        ),
        already_eligible=info["already"],
        blocked_other=info["blocked"],
        unreachable=info["unreachable"],
        skills_acquired=tuple(sorted(cov)),
        constraints=reports,
        slacks=tuple(s for k in chosen for s in k.slacks),
        candidate_sessions=len(cands),
        params=params,
    )


# --- MIP ---------------------------------------------------------------------


def _solve_mip(
    cands: list[_Cand],
    gaps: dict[str, tuple[PostingIn, frozenset[str]]],
    params: TrainingParams,
) -> tuple[TrainingStatus, list[_Cand], float | None]:
    model = cp_model.CpModel()
    c = {k.key: model.new_bool_var(f"c_{k.key}") for k in cands}

    by_course: dict[str, list[_Cand]] = {}
    for k in cands:
        by_course.setdefault(k.course.id, []).append(k)
    for ks in by_course.values():
        model.add(sum(c[k.key] for k in ks) <= 1)  # una_sesion_por_curso

    for i, a in enumerate(cands):  # sin_solape
        for b in cands[i + 1 :]:
            if a.course.id != b.course.id and _overlaps(a.session, b.session):
                model.add(c[a.key] + c[b.key] <= 1)

    model.add(sum(c.values()) <= params.max_courses)  # max_cursos
    model.add(  # presupuesto_total
        sum(c[k.key] * k.cost_cents for k in cands) <= round(params.max_total_cost * CENTS)
    )
    model.add(  # max_horas
        sum(c[k.key] * k.course.hours for k in cands) <= params.max_total_hours
    )

    skills = sorted(frozenset().union(*(g for _, g in gaps.values())) if gaps else frozenset())
    cov = {s: model.new_bool_var(f"cov_{s}") for s in skills}
    for s in skills:
        model.add(cov[s] <= sum(c[k.key] for k in cands if s in k.teaches))
    unlocked = {pid: model.new_bool_var(f"u_{pid}") for pid in sorted(gaps)}
    for pid, (_, gap) in gaps.items():
        for s in gap:
            model.add(unlocked[pid] <= cov[s])

    model.maximize(
        sum(unlocked[pid] * gaps[pid][0].vacancies * W_VACANCY for pid in unlocked)
        + W_PROGRESS * sum(cov.values())
        - sum(
            c[k.key]
            * (
                k.cost_cents // CENTS * params.penalty_cost_per_balboa
                + k.course.hours * params.penalty_per_hour
                + W_COURSE
                + k.slack_penalty
            )
            for k in cands
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = params.time_limit_s
    solver.parameters.random_seed = params.seed
    solver.parameters.num_workers = 1
    code = solver.solve(model)
    if code == cp_model.OPTIMAL:
        status: TrainingStatus = "OPTIMAL"
    elif code == cp_model.FEASIBLE:
        status = "FEASIBLE"
    elif code == cp_model.INFEASIBLE:
        status = "INFEASIBLE"
    else:
        return "TIMEOUT", [], None
    chosen = [k for k in cands if solver.value(c[k.key])]
    return status, chosen, solver.objective_value


# --- Greedy ------------------------------------------------------------------


def _solve_greedy(
    cands: list[_Cand],
    gaps: dict[str, tuple[PostingIn, frozenset[str]]],
    params: TrainingParams,
) -> list[_Cand]:
    """Greedy determinista: añade la sesión de mayor ganancia marginal por costo."""
    chosen: list[_Cand] = []
    current, _, _ = _plan_value(chosen, gaps, params)
    while True:
        best: tuple[float, str, _Cand] | None = None
        for k in cands:
            if k in chosen or not _feasible_to_add(chosen, k, params):
                continue
            value, _, _ = _plan_value([*chosen, k], gaps, params)
            gain = value - current
            if gain <= 0:
                continue
            rank = (gain / (1 + k.cost_cents / CENTS), k.key)
            if (
                best is None
                or rank[0] > best[0] + 1e-12
                or (abs(rank[0] - best[0]) <= 1e-12 and rank[1] < best[1])
            ):
                best = (rank[0], rank[1], k)
        if best is None:
            return chosen
        chosen.append(best[2])
        current, _, _ = _plan_value(chosen, gaps, params)


# --- API pública -------------------------------------------------------------


def _inputs(
    youth: YouthIn,
    postings: Iterable[PostingIn],
    courses: Iterable[CourseIn],
    commute: CommuteTable,
    params: TrainingParams,
):
    ps = sorted(postings, key=lambda p: p.id)
    cs = sorted(courses, key=lambda c: c.id)
    if len(ps) > params.max_postings:
        raise ValueError(f"Tamaño fuera de límite: {len(ps)} ofertas (máx. {params.max_postings})")
    if len({p.id for p in ps}) != len(ps) or len({c.id for c in cs}) != len(cs):
        raise ValueError("ids de ofertas o cursos repetidos")
    return _prepare(youth, ps, cs, commute, params)


def solve_training_greedy(
    youth: YouthIn,
    postings: Iterable[PostingIn],
    courses: Iterable[CourseIn],
    commute: CommuteTable,
    params: TrainingParams | None = None,
) -> TrainingPlanResult:
    """Ruta de formación con el greedy determinista (misma interfaz que `solve_training`)."""
    params = params or TrainingParams()
    t0 = time.perf_counter()
    cands, gaps, info = _inputs(youth, postings, courses, commute, params)
    chosen = _solve_greedy(cands, gaps, params)
    value, _, _ = _plan_value(chosen, gaps, params)
    return _build_result(
        status="FEASIBLE",
        method="greedy",
        chosen=chosen,
        gaps=gaps,
        info=info,
        cands=cands,
        params=params,
        solve_ms=round((time.perf_counter() - t0) * 1000),
        objective=float(value) + 0.0,
    )


def solve_training(
    youth: YouthIn,
    postings: Iterable[PostingIn],
    courses: Iterable[CourseIn],
    commute: CommuteTable,
    params: TrainingParams | None = None,
) -> TrainingPlanResult:
    """Ruta de formación óptima (MIP) con respaldo greedy.

    ``params.method``: ``"mip"`` (solo MIP), ``"greedy"`` o ``"auto"`` (MIP y, si no devuelve
    solución a tiempo, greedy; el motivo queda en ``fallback_reason``).
    """
    params = params or TrainingParams()
    if params.method == "greedy":
        return solve_training_greedy(youth, postings, courses, commute, params)
    t0 = time.perf_counter()
    cands, gaps, info = _inputs(youth, postings, courses, commute, params)
    status, chosen, obj = _solve_mip(cands, gaps, params)
    ms = round((time.perf_counter() - t0) * 1000)
    if status in ("OPTIMAL", "FEASIBLE"):
        return _build_result(
            status=status,
            method="mip",
            chosen=chosen,
            gaps=gaps,
            info=info,
            cands=cands,
            params=params,
            solve_ms=ms,
            objective=obj,
        )
    if params.method == "auto":
        g = _solve_greedy(cands, gaps, params)
        value, _, _ = _plan_value(g, gaps, params)
        return _build_result(
            status="FEASIBLE",
            method="greedy",
            chosen=g,
            gaps=gaps,
            info=info,
            cands=cands,
            params=params,
            solve_ms=round((time.perf_counter() - t0) * 1000),
            objective=float(value) + 0.0,
            fallback_reason=f"MIP terminó en {status}",
        )
    return _build_result(
        status=status,
        method="mip",
        chosen=[],
        gaps=gaps,
        info=info,
        cands=cands,
        params=params,
        solve_ms=ms,
        objective=None,
    )
