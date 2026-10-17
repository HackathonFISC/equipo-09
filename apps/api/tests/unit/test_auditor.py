"""Tests del auditor contrafactual: un test por variable, por regla de decisión y por fallo."""

import pytest

from puente_api.db.seed.loaders import read_seed_bundle
from puente_api.solvers.auditor import (
    CONTRACT_VARIABLES,
    DisparateImpact,
    ProtectedAttrs,
    audit_matching,
    audit_posting,
    audit_postings,
)
from puente_api.solvers.auditor_adapter import (
    posting_texts_from_seed,
    protected_from_seed,
)
from puente_api.solvers.matching import (
    CommuteEntry,
    MatchingParams,
    PostingIn,
    Requirement,
    TimeSlot,
    YouthIn,
    solve_matching,
)
from puente_api.solvers.matching_adapter import input_from_seed

A, B = "loc-a", "loc-b"
CAJA = "sk-caja"
WEEK = tuple(TimeSlot(day=d, start="07:00", end="17:00") for d in ("lun", "mar", "mie"))
SHIFT = tuple(TimeSlot(day=d, start="08:00", end="16:00") for d in ("lun", "mar", "mie"))
COMMUTE = {
    (A, A): CommuteEntry(minutes=10, cost_daily=0.5),
    (B, B): CommuteEntry(minutes=10, cost_daily=0.5),
    (A, B): CommuteEntry(minutes=20, cost_daily=1.0),
    (B, A): CommuteEntry(minutes=20, cost_daily=1.0),
}


def youth(i: int, loc: str = A, skill: int = 3) -> YouthIn:
    return YouthIn(
        id=f"y{i}",
        location_id=loc,
        max_commute_min=45,
        transport_budget_daily=3.0,
        availability=WEEK,
        min_salary=500.0,
        skills={CAJA: skill},
    )


def posting(i: int, loc: str = A, vacancies: int = 1) -> PostingIn:
    return PostingIn(
        id=f"p{i}",
        location_id=loc,
        schedule=SHIFT,
        salary_min=600.0,
        salary_max=600.0,
        vacancies=vacancies,
        requirements=(Requirement(skill_id=CAJA, weight=3, required=True),),
    )


PROTECTED = {
    "y1": ProtectedAttrs(display_name="Ana", gender="femenino", birth_year=2003),
    "y2": ProtectedAttrs(display_name="Luis", gender="masculino", birth_year=2001),
    "y3": ProtectedAttrs(display_name="Rosa", gender="femenino", birth_year=1999),
    "y4": ProtectedAttrs(display_name="Marcos", gender="masculino", birth_year=2004),
}


def scenario():
    ys = [youth(1), youth(2, B), youth(3), youth(4, B)]
    ps = [posting(1, A, 2), posting(2, B, 2)]
    res = solve_matching(ys, ps, COMMUTE, MatchingParams())
    return ys, ps, res


# --- Solver ciego: paridad 1 en las tres variables del contrato ---------------


@pytest.mark.parametrize("variable", CONTRACT_VARIABLES)
def test_solver_ciego_tiene_paridad_total(variable):
    ys, ps, res = scenario()
    rep = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED, variables=(variable,))
    (check,) = rep.checks
    assert check.kind == "contrafactual" and check.variable == variable
    assert check.parity == 1.0 and check.passed
    assert check.changed_youth_ids == ()
    assert rep.solves == 1 and rep.passed and not rep.needs_review


def test_audita_las_tres_variables_por_defecto():
    ys, ps, res = scenario()
    rep = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED)
    assert [c.variable for c in rep.checks] == ["nombre", "genero", "corregimiento"]
    assert rep.solves == 3


# --- Un solver con fuga de cada atributo se detecta ---------------------------


def leaky(rule):
    """Solver que usa un atributo protegido: la regla recibe (joven, protegidos) y puede
    degradar al joven. Debe detectarse porque el contrafactual cambia el atributo."""

    def solve_fn(youths, postings, commute, params, protected):
        adj = [rule(y, protected.get(y.id, ProtectedAttrs())) for y in youths]
        return solve_matching(adj, postings, commute, params)

    return solve_fn


def strip_skills(y: YouthIn) -> YouthIn:
    return y.model_copy(update={"skills": {}})


def test_detecta_fuga_de_genero():
    ys, ps, res = scenario()
    solve_fn = leaky(lambda y, p: strip_skills(y) if p.gender == "femenino" else y)
    # La corrida base también filtra por género: se audita la corrida con el solver con fuga.
    base = solve_fn(ys, ps, COMMUTE, res.params, PROTECTED)
    rep = audit_matching(
        ys, ps, COMMUTE, base, protected=PROTECTED, variables=("genero",), solve_fn=solve_fn
    )
    (check,) = rep.checks
    assert not check.passed and check.parity < 0.95
    assert set(check.changed_youth_ids) >= {"y1", "y3"}  # las que antes eran penalizadas
    assert rep.needs_review


def test_detecta_fuga_de_nombre():
    ys, ps, res = scenario()
    solve_fn = leaky(lambda y, p: strip_skills(y) if p.display_name == "Ana" else y)
    base = solve_fn(ys, ps, COMMUTE, res.params, PROTECTED)
    rep = audit_matching(
        ys, ps, COMMUTE, base, protected=PROTECTED, variables=("nombre",), solve_fn=solve_fn
    )
    (check,) = rep.checks
    assert not check.passed
    assert "y1" in check.changed_youth_ids  # Ana pierde la penalización al rotar nombres


def test_detecta_fuga_de_corregimiento():
    ys, ps, res = scenario()

    def rule(y, p):
        return strip_skills(y) if y.location_id == B else y  # castiga a un barrio por su etiqueta

    solve_fn = leaky(rule)
    base = solve_fn(ys, ps, COMMUTE, res.params, PROTECTED)
    rep = audit_matching(
        ys,
        ps,
        COMMUTE,
        base,
        protected=PROTECTED,
        variables=("corregimiento",),
        solve_fn=solve_fn,
    )
    (check,) = rep.checks
    assert not check.passed
    assert set(check.changed_youth_ids) == {"y2", "y4"}


def test_detecta_fuga_de_edad_variable_opcional():
    ys, ps, res = scenario()
    solve_fn = leaky(lambda y, p: strip_skills(y) if (p.birth_year or 0) >= 2003 else y)
    base = solve_fn(ys, ps, COMMUTE, res.params, PROTECTED)
    rep = audit_matching(
        ys, ps, COMMUTE, base, protected=PROTECTED, variables=("edad",), solve_fn=solve_fn
    )
    assert not rep.checks[0].passed


# --- Umbral, empates y fail-safe ----------------------------------------------


def test_umbral_de_paridad_es_configurable():
    ys, ps, res = scenario()
    solve_fn = leaky(lambda y, p: strip_skills(y) if p.gender == "femenino" else y)
    base = solve_fn(ys, ps, COMMUTE, res.params, PROTECTED)
    kw = {"protected": PROTECTED, "variables": ("genero",), "solve_fn": solve_fn}
    strict = audit_matching(ys, ps, COMMUTE, base, parity_threshold=0.95, **kw)
    lax = audit_matching(ys, ps, COMMUTE, base, parity_threshold=0.0, **kw)
    assert strict.checks[0].parity == lax.checks[0].parity
    assert not strict.passed and lax.passed


def test_empate_entre_identicos_es_estable_al_rotar_nombres():
    # Dos jóvenes idénticos compiten por 1 cupo: el desempate por id es estable, así que
    # cambiar solo el nombre no mueve a nadie.
    ys = [youth(1), youth(2)]
    ps = [posting(1, A, 1)]
    res = solve_matching(ys, ps, COMMUTE, MatchingParams())
    rep = audit_matching(
        ys, ps, COMMUTE, res, protected=PROTECTED, variables=("nombre",), score_tol=1e-6
    )
    assert rep.checks[0].parity == 1.0


def test_sin_solucion_falla_de_forma_segura():
    ys, ps, res = scenario()
    bad = res.model_copy(update={"status": "TIMEOUT"})
    rep = audit_matching(ys, ps, COMMUTE, bad, protected=PROTECTED)
    assert not rep.passed and rep.solves == 0
    assert all(c.parity is None and "TIMEOUT" in c.findings[0] for c in rep.checks)


def test_deterministico_mismos_ids_y_paridad():
    ys, ps, res = scenario()
    a = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED, run_key="r1")
    b = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED, run_key="r1")
    c = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED, run_key="r2")
    assert a == b
    assert {x.id for x in a.checks}.isdisjoint({x.id for x in c.checks})


def test_sin_jovenes_no_falla():
    res = solve_matching([], [posting(1)], COMMUTE, MatchingParams())
    rep = audit_matching([], [posting(1)], COMMUTE, res)
    assert rep.passed and all(c.parity == 1.0 for c in rep.checks)


# --- Impacto dispar (4/5) ------------------------------------------------------


def _di(rep, name) -> DisparateImpact:
    return next(d for d in rep.disparate_impact if d.variable == name)


def many(n_f: int, n_m: int):
    ys, prot = [], {}
    for i in range(n_f + n_m):
        ys.append(youth(i))
        female = i < n_f
        prot[f"y{i}"] = ProtectedAttrs(
            gender="femenino" if female else "masculino", birth_year=2002
        )
    return ys, prot


def test_impacto_dispar_se_calcula_por_genero_y_es_informativo():
    # 12 jóvenes (6/6), 6 cupos; las mujeres tienen mejor habilidad → ellas ocupan los cupos.
    ys, prot = many(6, 6)
    ys = [
        y.model_copy(update={"skills": {CAJA: 3 if prot[y.id].gender == "femenino" else 1}})
        for y in ys
    ]
    ps = [posting(1, A, 6)]
    res = solve_matching(ys, ps, COMMUTE, MatchingParams())
    rep = audit_matching(ys, ps, COMMUTE, res, protected=prot, variables=("genero",))
    di = _di(rep, "genero")
    assert di.ratio == 0.0 and not di.passed
    # Informativo: el aviso aparece pero `passed` sigue siendo True (paridad contrafactual 1).
    assert rep.checks[0].passed
    assert any("impacto dispar" in f for f in rep.checks[0].findings)
    strict = audit_matching(
        ys, ps, COMMUTE, res, protected=prot, variables=("genero",), enforce_disparate_impact=True
    )
    assert not strict.checks[0].passed


def test_impacto_dispar_con_pocos_datos_no_alarma():
    ys, prot = many(2, 2)
    res = solve_matching(ys, [posting(1, A, 1)], COMMUTE, MatchingParams())
    rep = audit_matching(ys, [posting(1, A, 1)], COMMUTE, res, protected=prot)
    di = _di(rep, "genero")
    assert di.ratio is None and di.passed and "insuficientes" in di.note


# --- Contrato con openapi (AuditCheck) -----------------------------------------


def test_to_api_cumple_el_schema_audit_check():
    ys, ps, res = scenario()
    out = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED).to_api()
    assert len(out) == 3
    for item in out:
        assert set(item) <= {"id", "kind", "variable", "parity", "passed", "findings"}
        assert {"id", "kind", "passed"} <= set(item)
        assert item["kind"] in ("discriminacion", "contrafactual")
        assert item["variable"] in ("nombre", "genero", "corregimiento")
        assert 0 <= item["parity"] <= 1
        assert all(isinstance(f, str) for f in item["findings"])


def test_variable_edad_no_sale_en_el_contrato():
    ys, ps, res = scenario()
    out = audit_matching(ys, ps, COMMUTE, res, protected=PROTECTED, variables=("edad",)).to_api()
    assert "variable" not in out[0]


# --- Discriminación en ofertas -------------------------------------------------


def test_audit_posting_bloquea_oferta_discriminatoria():
    c = audit_posting("p1", "Mujeres de 18 a 25 años, buena presencia")
    assert c.kind == "discriminacion" and not c.passed and c.posting_id == "p1"
    assert len(c.findings) >= 3
    out = c.to_api()
    assert out["passed"] is False and "variable" not in out and "parity" not in out


def test_audit_posting_oferta_limpia():
    c = audit_posting("p2", "Cajero/a de minisúper. Mayores de 18 años. B/. 650.")
    assert c.passed and c.findings == ()


def test_audit_postings_ordena_por_id():
    checks = audit_postings({"b": "Solo varones", "a": "Cajero/a"})
    assert [c.posting_id for c in checks] == ["a", "b"]


# --- Con los seeds --------------------------------------------------------------


def test_seeds_paridad_y_discriminacion():
    bundle = read_seed_bundle()
    inp = input_from_seed(bundle)
    res = solve_matching(inp.youths, inp.postings, inp.commute, MatchingParams.relaxed())
    rep = audit_matching(
        inp.youths, inp.postings, inp.commute, res, protected=protected_from_seed(bundle)
    )
    assert rep.passed
    assert all(c.parity == 1.0 for c in rep.checks)
    texts = posting_texts_from_seed(bundle)
    flagged = {c.posting_id for c in audit_postings(texts) if not c.passed}
    labels = {p.posting for p in bundle.discrimination_labels if p.discriminatory}
    from puente_api.db.seed.loaders import seed_uuid

    assert flagged == {str(seed_uuid("job_posting", k)) for k in labels}


def test_el_solver_es_ciego_por_construccion():
    forbidden = {"display_name", "name", "gender", "genero", "sexo", "birth_year", "age", "edad"}
    assert forbidden.isdisjoint(YouthIn.model_fields)
    assert forbidden.isdisjoint(PostingIn.model_fields)
