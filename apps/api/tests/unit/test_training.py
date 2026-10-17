"""Tests del solver de formación: una prueba por restricción, MIP vs greedy y seeds."""

from datetime import date

import pytest

from puente_api.db.seed.loaders import read_seed_bundle
from puente_api.solvers.matching import (
    CommuteEntry,
    MatchingParams,
    PostingIn,
    Requirement,
    TimeSlot,
    YouthIn,
    check_pair,
)
from puente_api.solvers.matching_adapter import input_from_seed
from puente_api.solvers.training import (
    CourseIn,
    SessionIn,
    TrainingParams,
    solve_training,
    solve_training_greedy,
)
from puente_api.solvers.training_adapter import courses_from_seed

HOME, CENTER, FAR, WORK = "home", "center", "far", "work"
S1, S2, S3 = "sk1", "sk2", "sk3"
EVENING = (TimeSlot(day="lun", start="18:00", end="21:00"),)
EVENING2 = (TimeSlot(day="mar", start="18:00", end="21:00"),)
ALLDAY = tuple(
    TimeSlot(day=d, start="06:00", end="22:00") for d in ("lun", "mar", "mie", "vie", "sab")
)
COMMUTE = {
    (HOME, CENTER): CommuteEntry(minutes=20, cost_daily=1.0),
    (HOME, FAR): CommuteEntry(minutes=90, cost_daily=5.0),
    (HOME, WORK): CommuteEntry(minutes=15, cost_daily=0.5),
}


def youth(**kw) -> YouthIn:
    base = {
        "id": "y",
        "location_id": HOME,
        "max_commute_min": 45,
        "transport_budget_daily": 3.0,
        "availability": ALLDAY,
        "min_salary": 500.0,
        "skills": {},
    }
    return YouthIn.model_validate(base | kw)


def posting(id_: str, skills: tuple[str, ...], vacancies: int = 1, **kw) -> PostingIn:
    base = {
        "id": id_,
        "location_id": WORK,
        "schedule": (TimeSlot(day="vie", start="08:00", end="16:00"),),
        "salary_min": 600.0,
        "salary_max": 600.0,
        "vacancies": vacancies,
        "requirements": tuple(Requirement(skill_id=s, weight=2, required=True) for s in skills),
    }
    return PostingIn.model_validate(base | kw)


def session(id_: str, sched=EVENING, total=10, taken=0, start=date(2026, 11, 2)) -> SessionIn:
    return SessionIn(id=id_, start_date=start, schedule=sched, seats_total=total, seats_taken=taken)


def course(
    id_: str, skills: tuple[str, ...], sessions, *, cost=0.0, hours=30, loc=CENTER
) -> CourseIn:
    return CourseIn(
        id=id_,
        title=f"Curso {id_}",
        center_id=f"c-{id_}",
        center_location_id=loc,
        hours=hours,
        cost=cost,
        skill_ids=skills,
        sessions=tuple(sessions),
    )


def plan(ys=None, ps=None, cs=None, **p):
    return solve_training(
        ys or youth(), ps or [posting("p1", (S1,))], cs, COMMUTE, TrainingParams(**p)
    )


def sessions_of(r) -> set[str]:
    return {it.session.id for it in r.items}


# --- Caso base ----------------------------------------------------------------


def test_caso_base_desbloquea_la_oferta():
    r = plan(cs=[course("a", (S1,), [session("a1")])])
    assert r.status == "OPTIMAL" and r.method == "mip"
    assert sessions_of(r) == {"a1"}
    assert [u.posting_id for u in r.unlocked] == ["p1"] and r.unlocked_vacancies == 1
    assert r.skills_acquired == (S1,)
    assert all(c.ok for c in r.constraints)
    assert "Curso a" in r.explanation_facts()


def test_sin_brechas_plan_vacio():
    r = plan(ys=youth(skills={S1: 3}), cs=[course("a", (S1,), [session("a1")])])
    assert r.items == () and r.already_eligible == ("p1",)
    assert "No hay brechas" in r.explanation_facts()


def test_brecha_sin_curso_queda_inalcanzable():
    r = plan(cs=[course("a", (S2,), [session("a1")])])
    assert r.items == () and r.unreachable == ("p1",)


def test_oferta_bloqueada_por_otra_restriccion_no_se_desbloquea():
    p = posting("p1", (S1,), salary_min=100.0, salary_max=200.0)  # salario < mínimo del joven
    r = plan(ps=[p], cs=[course("a", (S1,), [session("a1")])])
    assert r.items == () and "salario_minimo" in r.blocked_other["p1"]


def test_tras_la_formacion_el_par_es_elegible_en_el_matching():
    r = plan(cs=[course("a", (S1,), [session("a1")])])
    y = youth(skills={s: 2 for s in r.skills_acquired})
    ev = check_pair(y, posting("p1", (S1,)), COMMUTE, MatchingParams())
    assert ev.eligible


# --- Restricciones -------------------------------------------------------------


def test_una_sesion_por_curso():
    r = plan(cs=[course("a", (S1,), [session("a1"), session("a2", EVENING2)])])
    assert len(r.items) == 1


def test_cupo_sesion_descarta_sesion_llena():
    full = session("full", total=5, taken=5)
    r = plan(cs=[course("a", (S1,), [full, session("ok", EVENING2, total=5, taken=4)])])
    assert sessions_of(r) == {"ok"}
    r2 = plan(cs=[course("a", (S1,), [full])])
    assert r2.items == ()


def test_horario_joven_exige_disponibilidad():
    y = youth(availability=(TimeSlot(day="mar", start="08:00", end="12:00"),))
    cs = [
        course(
            "a",
            (S1,),
            [
                session("night", EVENING),
                session("day", (TimeSlot(day="mar", start="08:00", end="11:00"),)),
            ],
        )
    ]
    p = posting("p1", (S1,), schedule=(TimeSlot(day="mar", start="08:00", end="11:00"),))
    assert sessions_of(plan(ys=y, ps=[p], cs=cs)) == {"day"}
    # Con cobertura mínima 0 se acepta cualquiera.
    r = plan(
        ys=y,
        ps=[p],
        cs=[course("a", (S1,), [session("night", EVENING)])],
        min_session_coverage=0.0,
    )
    assert sessions_of(r) == {"night"}


def test_sin_solape_entre_sesiones():
    cs = [
        course("a", (S1,), [session("a1")]),
        course("b", (S2,), [session("b1")]),  # mismo día y hora que a1
    ]
    ps = [posting("p1", (S1, S2))]
    r = plan(ps=ps, cs=cs)
    assert len(r.items) <= 1 and r.unlocked == ()  # no puede tomar ambos → no desbloquea
    cs2 = [course("a", (S1,), [session("a1")]), course("b", (S2,), [session("b1", EVENING2)])]
    r2 = plan(ps=ps, cs=cs2)
    assert sessions_of(r2) == {"a1", "b1"} and len(r2.unlocked) == 1


def test_sin_solape_lo_resuelve_con_otra_sesion():
    cs = [
        course("a", (S1,), [session("a1")]),
        course("b", (S2,), [session("b1"), session("b2", EVENING2)]),
    ]
    r = plan(ps=[posting("p1", (S1, S2))], cs=cs)
    assert sessions_of(r) == {"a1", "b2"}


def test_traslado_max_filtra_centros_lejanos():
    r = plan(cs=[course("a", (S1,), [session("a1")], loc=FAR)])
    assert r.items == ()


def test_traslado_con_tolerancia_es_holgura_penalizada():
    cs = [course("a", (S1,), [session("a1")], loc=FAR)]
    y2 = youth(max_commute_min=60, transport_budget_daily=9.0)
    assert plan(ys=y2, cs=cs).items == ()
    r = plan(ys=y2, cs=cs, commute_tolerance_min=30, max_total_cost=500)
    assert len(r.items) == 1
    assert [s.constraint for s in r.slacks] == ["traslado_max"] and r.slacks[0].amount == 30


def test_presupuesto_transporte_diario():
    y = youth(transport_budget_daily=0.5)  # el viaje cuesta 1.0 al día
    cs = [course("a", (S1,), [session("a1")])]
    assert plan(ys=y, cs=cs).items == ()
    r = plan(ys=y, cs=cs, budget_tolerance=1.0)
    assert len(r.items) == 1 and r.slacks[0].constraint == "presupuesto_transporte"


def test_dato_traslado_faltante_descarta():
    r = plan(cs=[course("a", (S1,), [session("a1")], loc="isla-sin-dato")])
    assert r.items == ()


def test_presupuesto_total_incluye_matricula_y_transporte():
    cs = [course("a", (S1,), [session("a1")], cost=50.0)]
    ok = plan(cs=cs, max_total_cost=200)
    assert ok.fees_cost == 50.0 and ok.transport_cost > 0
    assert ok.total_cost == pytest.approx(50.0 + ok.transport_cost)
    assert plan(cs=cs, max_total_cost=50.0).items == ()  # 50 de matrícula + transporte > 50


def test_presupuesto_total_elige_la_opcion_mas_barata():
    cs = [
        course("cara", (S1,), [session("c1")], cost=80.0),
        course("barata", (S1,), [session("b1", EVENING2)], cost=0.0),
    ]
    assert sessions_of(plan(cs=cs)) == {"b1"}


def test_max_cursos():
    ps = [posting("p1", (S1, S2, S3))]
    cs = [
        course("a", (S1,), [session("a1")]),
        course("b", (S2,), [session("b1", EVENING2)]),
        course("c", (S3,), [session("c1", (TimeSlot(day="mie", start="18:00", end="21:00"),))]),
    ]
    assert len(plan(ps=ps, cs=cs, max_courses=3).unlocked) == 1
    r = plan(ps=ps, cs=cs, max_courses=2)
    assert len(r.items) <= 2 and r.unlocked == ()


def test_max_horas():
    cs = [course("a", (S1,), [session("a1")], hours=100)]
    assert plan(cs=cs, max_total_hours=100).items
    assert plan(cs=cs, max_total_hours=99).items == ()


def test_prioriza_mas_vacantes_desbloqueadas():
    ps = [posting("chica", (S1,), vacancies=1), posting("grande", (S2,), vacancies=5)]
    cs = [course("a", (S1,), [session("a1")]), course("b", (S2,), [session("b1")])]  # se pisan
    r = plan(ps=ps, cs=cs)
    assert sessions_of(r) == {"b1"} and r.unlocked_vacancies == 5


def test_un_curso_puede_desbloquear_varias_ofertas():
    ps = [posting("p1", (S1,)), posting("p2", (S1, S2))]
    cs = [course("a", (S1, S2), [session("a1")])]
    r = plan(ps=ps, cs=cs)
    assert [u.posting_id for u in r.unlocked] == ["p1", "p2"]


def test_no_toma_cursos_que_no_aportan():
    cs = [course("a", (S1,), [session("a1")]), course("inutil", (S3,), [session("i1", EVENING2)])]
    assert sessions_of(plan(cs=cs)) == {"a1"}


# --- Respaldo greedy ----------------------------------------------------------


def test_greedy_misma_interfaz_y_restricciones():
    cs = [course("a", (S1,), [session("a1")]), course("b", (S2,), [session("b1")])]
    ps = [posting("p1", (S1,)), posting("p2", (S2,))]
    g = solve_training_greedy(youth(), ps, cs, COMMUTE, TrainingParams())
    assert g.method == "greedy" and len(g.items) == 1  # solape: solo uno
    assert all(c.ok for c in g.constraints)


def test_mip_nunca_es_peor_que_greedy():
    # Caso trampa: el greedy toma el curso grande y bloquea la combinación óptima.
    ps = [posting("p1", (S1, S2), vacancies=3), posting("p2", (S3,), vacancies=1)]
    cs = [
        course("c3", (S3,), [session("c3", EVENING)]),
        course("c1", (S1,), [session("c1", EVENING2)]),
        course("c2", (S2,), [session("c2", (TimeSlot(day="mie", start="18:00", end="21:00"),))]),
    ]
    mip = plan(ps=ps, cs=cs, max_courses=2)
    gr = plan(ps=ps, cs=cs, max_courses=2, method="greedy")
    assert mip.objective >= gr.objective
    assert mip.unlocked_vacancies >= gr.unlocked_vacancies


def test_auto_cae_a_greedy_si_el_mip_no_responde(monkeypatch):
    import puente_api.solvers.training as t

    monkeypatch.setattr(t, "_solve_mip", lambda *a, **k: ("TIMEOUT", [], None))
    r = plan(cs=[course("a", (S1,), [session("a1")])])
    assert r.method == "greedy" and "TIMEOUT" in (r.fallback_reason or "")
    assert sessions_of(r) == {"a1"}
    with_mip = solve_training(
        youth(),
        [posting("p1", (S1,))],
        [course("a", (S1,), [session("a1")])],
        COMMUTE,
        TrainingParams(method="mip"),
    )
    assert with_mip.status == "TIMEOUT" and with_mip.items == ()


def test_determinista():
    cs = [course("a", (S1,), [session("a1"), session("a2", EVENING2)])]
    assert plan(cs=cs).model_dump() | {"solve_ms": 0} == plan(cs=cs).model_dump() | {"solve_ms": 0}


def test_tamano_acotado():
    with pytest.raises(ValueError, match="fuera de límite"):
        plan(ps=[posting(f"p{i}", (S1,)) for i in range(3)], cs=[], max_postings=2)
    with pytest.raises(ValueError, match="repetidos"):
        plan(cs=[course("a", (S1,), [session("a1")]), course("a", (S1,), [session("a2")])])


# --- Contrato ------------------------------------------------------------------


def test_to_api_cumple_training_plan():
    r = plan(cs=[course("a", (S1,), [session("a1")], cost=10.0)])
    out = r.to_api("plan-1", "y")
    assert set(out) == {"id", "youthId", "items", "totalCost", "unlockedPostings", "explanation"}
    (item,) = out["items"]
    assert item["courseTitle"] == "Curso a" and item["commuteMin"] == 20
    assert set(item["session"]) == {"id", "schedule", "startDate", "seatsTotal", "seatsTaken"}
    assert item["session"]["startDate"] == "2026-11-02"
    assert out["unlockedPostings"] == 1 and out["totalCost"] >= 10.0


# --- Seeds ---------------------------------------------------------------------


def test_seeds_cupos_respetados_y_mip_ge_greedy():
    bundle = read_seed_bundle()
    inp = input_from_seed(bundle)
    courses = courses_from_seed(bundle)
    seats = {s.id: s.seats_left for c in courses for s in c.sessions}
    with_plan = 0
    for y in inp.youths:
        mip = solve_training(y, inp.postings, courses, inp.commute)
        gr = solve_training_greedy(y, inp.postings, courses, inp.commute)
        assert mip.status == "OPTIMAL"
        assert all(seats[it.session.id] >= 1 for it in mip.items)
        assert mip.total_cost <= mip.params.max_total_cost + 1e-9
        assert len(mip.items) <= mip.params.max_courses
        assert mip.unlocked_vacancies >= gr.unlocked_vacancies
        assert all(c.ok for c in mip.constraints)
        with_plan += bool(mip.items)
    assert with_plan >= 5
