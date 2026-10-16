"""Tests del solver de matching CP-SAT: un test por restricción + corrida sobre los seeds."""

import random

import pytest
from pydantic import ValidationError

from puente_api.solvers.matching import (
    C_BUDGET,
    C_CAPACITY,
    C_COMMUTE,
    C_COMMUTE_DATA,
    C_MIN_SCORE,
    C_ONE_PER_YOUTH,
    C_REQUIRED,
    C_SALARY,
    C_SCHEDULE,
    CommuteEntry,
    MatchingParams,
    PostingIn,
    Requirement,
    TimeSlot,
    YouthIn,
    check_pair,
    schedule_coverage,
    solve_matching,
)

A, B, C = "loc-a", "loc-b", "loc-c"
CAJA, ATENCION, EXCEL = "sk-caja", "sk-atencion", "sk-excel"
WEEK = tuple(TimeSlot(day=d, start="07:00", end="17:00") for d in ("lun", "mar", "mie"))
SHIFT = tuple(TimeSlot(day=d, start="08:00", end="16:00") for d in ("lun", "mar", "mie"))

COMMUTE = {
    (A, A): CommuteEntry(minutes=10, cost_daily=0.5),
    (A, B): CommuteEntry(minutes=50, cost_daily=2.0),
    (B, A): CommuteEntry(minutes=50, cost_daily=2.0),
    (B, B): CommuteEntry(minutes=10, cost_daily=0.5),
    (A, C): CommuteEntry(minutes=30, cost_daily=4.0),
}


def youth(id_: str = "y1", **kw: object) -> YouthIn:
    base: dict[str, object] = {
        "id": id_,
        "location_id": A,
        "max_commute_min": 45,
        "transport_budget_daily": 3.0,
        "availability": WEEK,
        "min_salary": 600.0,
        "skills": {CAJA: 3, ATENCION: 2},
    }
    return YouthIn.model_validate(base | kw)


def posting(id_: str = "p1", **kw: object) -> PostingIn:
    base: dict[str, object] = {
        "id": id_,
        "location_id": A,
        "schedule": SHIFT,
        "salary_min": 650.0,
        "salary_max": 650.0,
        "vacancies": 1,
        "requirements": (
            Requirement(skill_id=CAJA, weight=3, required=True),
            Requirement(skill_id=ATENCION, weight=2, required=False),
        ),
    }
    return PostingIn.model_validate(base | kw)


def solve(ys, ps, params=None, commute=COMMUTE):
    return solve_matching(ys, ps, commute, params or MatchingParams())


def pairs(result) -> set[tuple[str, str]]:
    return {(a.youth_id, a.posting_id) for a in result.assignments}


# --- Caso base ---------------------------------------------------------------


def test_caso_base_asigna_con_desglose_y_restricciones():
    r = solve([youth()], [posting()])
    assert r.status == "OPTIMAL"
    (a,) = r.assignments
    assert (a.youth_id, a.posting_id) == ("y1", "p1")
    assert 0 < a.score <= 1
    b = a.breakdown
    assert b.skill_coverage == pytest.approx((3 * 1.0 + 2 * 0.8) / 5, abs=1e-4)
    assert b.schedule == 1.0 and b.salary == 1.0
    names = {c.name for c in a.constraints}
    assert {C_REQUIRED, C_COMMUTE, C_BUDGET, C_SCHEDULE, C_SALARY, C_CAPACITY} <= names
    assert all(c.ok for c in a.constraints)
    assert a.slacks == ()
    assert C_CAPACITY in a.active_constraints  # 1 vacante llena → restricción activa


# --- Restricciones duras por par ----------------------------------------------


def test_habilidad_obligatoria_faltante_bloquea():
    y = youth(skills={ATENCION: 3})
    r = solve([y], [posting()])
    assert r.assignments == ()
    (u,) = r.unassigned
    assert u.reasons == {C_REQUIRED: 1}
    assert r.unfilled == {"p1": 1}


def test_habilidad_obligatoria_con_holgura_penalizada():
    y = youth(skills={ATENCION: 3})
    r = solve([y], [posting()], MatchingParams(max_missing_required=1))
    (a,) = r.assignments
    assert a.breakdown.missing_required == (CAJA,)
    assert [s.constraint for s in a.slacks] == [C_REQUIRED]
    assert a.breakdown.penalty == pytest.approx(0.3)


def test_habilidad_opcional_faltante_no_bloquea_pero_baja_cobertura():
    full = check_pair(youth(), posting(), COMMUTE, MatchingParams())
    partial = check_pair(youth(skills={CAJA: 3}), posting(), COMMUTE, MatchingParams())
    assert partial.eligible
    assert partial.breakdown.missing_skills == (ATENCION,)
    assert partial.breakdown.missing_required == ()
    assert partial.breakdown.skill_coverage < full.breakdown.skill_coverage


def test_nivel_de_habilidad_pondera_cobertura():
    p = MatchingParams()
    hi = check_pair(youth(skills={CAJA: 3, ATENCION: 3}), posting(), COMMUTE, p)
    lo = check_pair(youth(skills={CAJA: 1, ATENCION: 1}), posting(), COMMUTE, p)
    assert hi.breakdown.skill_coverage == 1.0
    assert lo.breakdown.skill_coverage == pytest.approx(0.6)


def test_traslado_maximo_bloquea():
    r = solve([youth()], [posting(location_id=B)])  # 50 min > 45
    assert r.assignments == ()
    assert C_COMMUTE in r.unassigned[0].reasons


def test_traslado_con_tolerancia_usa_holgura():
    r = solve([youth()], [posting(location_id=B)], MatchingParams(commute_tolerance_min=10))
    (a,) = r.assignments
    c = a.constraint(C_COMMUTE)
    assert (c.value, c.limit, c.slack) == (50, 45, 5)
    assert a.slacks[0].constraint == C_COMMUTE and a.slacks[0].penalty == 50
    assert C_COMMUTE in a.active_constraints


def test_presupuesto_transporte_bloquea():
    y = youth(max_commute_min=60)
    r = solve([y], [posting(location_id=C)])  # B/. 4.00 > 3.00
    assert r.assignments == ()
    assert r.unassigned[0].reasons == {C_BUDGET: 1}


def test_presupuesto_con_tolerancia_usa_holgura():
    y = youth(max_commute_min=60)
    r = solve([y], [posting(location_id=C)], MatchingParams(budget_tolerance=1.0))
    (a,) = r.assignments
    assert a.constraint(C_BUDGET).slack == pytest.approx(1.0)
    assert a.slacks[0].constraint == C_BUDGET


def test_horario_incompatible_bloquea():
    night = (TimeSlot(day="lun", start="18:00", end="23:00"),)
    r = solve([youth()], [posting(schedule=night)])
    assert r.assignments == ()
    assert r.unassigned[0].reasons == {C_SCHEDULE: 1}


def test_horario_parcial_y_cobertura_minima():
    sched = (
        TimeSlot(day="lun", start="08:00", end="16:00"),
        TimeSlot(day="sab", start="08:00", end="16:00"),
    )
    assert schedule_coverage(WEEK, sched) == pytest.approx(0.5)
    assert solve([youth()], [posting(schedule=sched)]).assignments == ()
    r = solve([youth()], [posting(schedule=sched)], MatchingParams(min_schedule_coverage=0.5))
    assert r.assignments[0].breakdown.schedule == pytest.approx(0.5)


def test_horario_une_franjas_contiguas():
    split = (
        TimeSlot(day="lun", start="08:00", end="12:00"),
        TimeSlot(day="lun", start="12:00", end="16:00"),
    )
    assert schedule_coverage(split, (TimeSlot(day="lun", start="08:00", end="16:00"),)) == 1.0


def test_salario_minimo_bloquea():
    y = youth(min_salary=700.0)
    r = solve([y], [posting()])
    assert r.assignments == ()
    assert r.unassigned[0].reasons == {C_SALARY: 1}


def test_salario_en_rango_puntua_parcial():
    p = posting(salary_min=500.0, salary_max=800.0)
    ev = check_pair(youth(min_salary=650.0), p, COMMUTE, MatchingParams())
    assert ev.eligible
    assert ev.breakdown.salary == pytest.approx(0.75)
    assert check_pair(youth(min_salary=None), p, COMMUTE, MatchingParams()).breakdown.salary == 1


def test_sin_dato_de_traslado_bloquea_y_oferta_sin_lugar_no():
    y = youth(location_id=C)  # no hay (C, A) en la matriz
    ev = check_pair(y, posting(), COMMUTE, MatchingParams())
    assert not ev.eligible and C_COMMUTE_DATA in ev.violated
    remote = check_pair(y, posting(location_id=None), COMMUTE, MatchingParams())
    assert remote.eligible and remote.breakdown.commute == 1.0


def test_puntaje_minimo_filtra():
    r = solve([youth(skills={CAJA: 1})], [posting()], MatchingParams(min_score=0.95))
    assert r.assignments == ()
    assert r.unassigned[0].reasons == {C_MIN_SCORE: 1}


# --- Restricciones del modelo -------------------------------------------------


def test_cupos_por_oferta():
    ys = [youth("y1"), youth("y2", skills={CAJA: 1}), youth("y3", skills={CAJA: 2})]
    r = solve(ys, [posting(vacancies=1)])
    assert pairs(r) == {("y1", "p1")}  # el de mejor puntaje
    assert len(r.unassigned) == 2
    cap = r.assignments[0].constraint(C_CAPACITY)
    assert (cap.value, cap.limit, cap.binding) == (1, 1, True)

    r2 = solve(ys, [posting(vacancies=2)])
    assert pairs(r2) == {("y1", "p1"), ("y3", "p1")}

    r3 = solve(ys, [posting(vacancies=1)], MatchingParams(shortlist_factor=3))
    assert len(r3.assignments) == 3


def test_una_asignacion_por_joven():
    ps = [posting("p1"), posting("p2", salary_min=900.0, salary_max=900.0)]
    r = solve([youth()], ps)
    assert len(r.assignments) == 1
    assert r.unfilled == {"p1": 1, "p2": 0} or r.unfilled == {"p1": 0, "p2": 1}
    assert r.assignments[0].constraint(C_ONE_PER_YOUTH).binding


def test_asignacion_global_no_codiciosa():
    # y1 sirve en p1 y p2; y2 solo en p1. El óptimo cubre ambas vacantes.
    p2 = posting("p2", requirements=(Requirement(skill_id=EXCEL, weight=1, required=True),))
    y1 = youth("y1", skills={CAJA: 3, ATENCION: 3, EXCEL: 1})
    y2 = youth("y2", skills={CAJA: 2})
    r = solve([y1, y2], [posting("p1"), p2])
    assert pairs(r) == {("y1", "p2"), ("y2", "p1")}
    assert r.unassigned == () and sum(r.unfilled.values()) == 0


def test_cupos_vacios_son_holgura_no_infactible():
    r = solve([youth(skills={})], [posting(vacancies=3)])
    assert r.status == "OPTIMAL"
    assert r.unfilled == {"p1": 3}
    kinds = sorted(s.constraint for s in r.slacks)
    assert kinds == [C_CAPACITY, C_ONE_PER_YOUTH]


def test_prefiere_par_estricto_sobre_par_con_holgura():
    near = youth("y-near")
    far = youth("y-far", location_id=B, skills={CAJA: 3, ATENCION: 3})  # 50 min
    params = MatchingParams(commute_tolerance_min=10, penalty_commute_per_min=100)
    r = solve([near, far], [posting()], params)
    assert pairs(r) == {("y-near", "p1")}


# --- Propiedades del solver ---------------------------------------------------


def test_determinista_e_independiente_del_orden():
    ys = [youth(f"y{i}", skills={CAJA: 1 + i % 3, ATENCION: 1 + (i + 1) % 3}) for i in range(8)]
    ps = [posting(f"p{j}", vacancies=1 + j % 2) for j in range(4)]
    r1 = solve(ys, ps)
    shuffled_y, shuffled_p = ys[:], ps[:]
    random.Random(7).shuffle(shuffled_y)
    random.Random(7).shuffle(shuffled_p)
    r2 = solve(shuffled_y, shuffled_p)
    assert r1.assignments == r2.assignments
    assert r1.objective == r2.objective


def test_tamano_acotado():
    with pytest.raises(ValueError, match="Tamaño fuera de límite"):
        solve([youth(f"y{i}") for i in range(3)], [posting()], MatchingParams(max_youths=2))


def test_limite_de_pares_por_joven():
    ps = [posting(f"p{j}") for j in range(5)]
    r = solve([youth()], ps, MatchingParams(max_pairs_per_youth=2))
    assert r.eligible_pairs == 2


def test_variables_sensibles_no_entran_al_solver():
    with pytest.raises(ValidationError):
        youth(gender="femenino")
    with pytest.raises(ValidationError):
        youth(display_name="Ana")


# --- Seeds completos ----------------------------------------------------------


@pytest.fixture(scope="module")
def seed_input():
    from puente_api.db.seed.loaders import read_seed_bundle
    from puente_api.solvers.matching_adapter import input_from_seed

    return input_from_seed(read_seed_bundle())


def _hard_violations(result, inp):
    yi = {y.id: y for y in inp.youths}
    pi = {p.id: p for p in inp.postings}
    bad = []
    for a in result.assignments:
        ev = check_pair(yi[a.youth_id], pi[a.posting_id], inp.commute, result.params)
        bad += [(a.youth_id, a.posting_id, n) for n in ev.violated]
    return bad


@pytest.mark.parametrize("params", [MatchingParams(), MatchingParams.relaxed()])
def test_seeds_completos_dentro_del_limite(seed_input, params):
    from puente_api.db.seed.loaders import seed_uuid
    from puente_api.solvers.matching_adapter import run_params, to_match_result_rows

    r = solve_matching(seed_input.youths, seed_input.postings, seed_input.commute, params)
    assert r.status == "OPTIMAL"
    assert r.solve_ms < params.time_limit_s * 1000
    assert _hard_violations(r, seed_input) == []
    assigned = [a.youth_id for a in r.assignments]
    assert len(assigned) == len(set(assigned))
    counts: dict[str, int] = {}
    for a in r.assignments:
        counts[a.posting_id] = counts.get(a.posting_id, 0) + 1
    vac = {p.id: p.vacancies for p in seed_input.postings}
    assert all(n <= vac[pid] for pid, n in counts.items())
    assert len(r.assignments) + len(r.unassigned) == len(seed_input.youths)

    # Persona del demo: Ana → cajero/a de minisúper en Barrio Colón.
    ana = str(seed_uuid("youth", "ana"))
    cajera = str(seed_uuid("job_posting", "cajera-minisuper-barrio-colon"))
    assert r.by_youth()[ana].posting_id == cajera

    rows = to_match_result_rows(r, run_id="run-1")
    assert len(rows) == len(r.assignments)
    assert {"skillCoverage", "commute", "cost", "schedule", "salary", "missingSkills"} <= set(
        rows[0]["score_breakdown"]
    )
    assert {"commuteMin", "dailyCost", "scheduleOverlap", "salaryOk"} <= set(
        rows[0]["constraints_checked"]
    )
    assert run_params(r)["solver_status"] == "OPTIMAL"


def test_seeds_relajado_registra_holguras(seed_input):
    strict = solve_matching(seed_input.youths, seed_input.postings, seed_input.commute)
    relaxed = solve_matching(
        seed_input.youths, seed_input.postings, seed_input.commute, MatchingParams.relaxed()
    )
    assert len(relaxed.assignments) >= len(strict.assignments)
    pair_slacks = [s for a in relaxed.assignments for s in a.slacks]
    assert all(s.constraint in {C_REQUIRED, C_COMMUTE, C_BUDGET} for s in pair_slacks)


def test_adaptador_desde_bd_equivale_a_seeds(seed_input):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from puente_api.db import models
    from puente_api.db.seed.loaders import seed_database
    from puente_api.solvers.matching_adapter import load_matching_input

    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session)
        session.commit()
        db_input = load_matching_input(session)
    engine.dispose()
    r_seed = solve_matching(seed_input.youths, seed_input.postings, seed_input.commute)
    r_db = solve_matching(db_input.youths, db_input.postings, db_input.commute)
    assert pairs(r_db) == pairs(r_seed)
    assert r_db.objective == r_seed.objective
