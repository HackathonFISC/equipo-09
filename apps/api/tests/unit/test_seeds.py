"""Integridad de los datos semilla (db/seed) y del loader."""

import csv
import json
from collections import Counter

import pytest

from puente_api.db.seed import SEED_DIR, build_commute_matrix, build_rows, build_youth, read_seed_bundle, seed_uuid
from puente_api.db.seed.loaders import TABLE_ORDER


@pytest.fixture(scope="module")
def bundle():
    return read_seed_bundle()


@pytest.fixture(scope="module")
def rows(bundle):
    return build_rows(bundle)


# --- Conteos (doc 05 §3 y plan H1) -------------------------------------------------


def test_counts(bundle):
    assert len(bundle.locations) == 50
    assert len(bundle.skills) == 150
    assert len(bundle.postings) == 25
    assert len(bundle.courses) == 12
    assert len(bundle.youth) == 40
    assert len(bundle.training_centers) >= 1
    assert len(bundle.companies) >= 1


def test_locations_cover_target_districts(bundle):
    distritos = {x.distrito for x in bundle.locations}
    assert {"Panamá", "San Miguelito", "Arraiján", "La Chorrera"} <= distritos
    provincias = {x.provincia for x in bundle.locations}
    assert provincias == {"Panamá", "Panamá Oeste"}


# --- Matriz de traslado ------------------------------------------------------------


def test_commute_matrix_is_complete(bundle):
    keys = {x.key for x in bundle.locations}
    pairs = {(c.origin, c.dest) for c in bundle.commute}
    assert len(pairs) == len(bundle.commute), "pares repetidos"
    assert pairs == {(a, b) for a in keys for b in keys}


def test_commute_matrix_is_symmetric(bundle):
    by_pair = {(c.origin, c.dest): c for c in bundle.commute}
    for (a, b), c in by_pair.items():
        back = by_pair[(b, a)]
        assert (c.minutes, c.cost_daily, c.mode) == (back.minutes, back.cost_daily, back.mode), (a, b)


def test_commute_diagonal_is_cheapest_from_origin(bundle):
    by_origin: dict[str, list] = {}
    for c in bundle.commute:
        by_origin.setdefault(c.origin, []).append(c)
    for origin, trips in by_origin.items():
        self_trip = next(t for t in trips if t.dest == origin)
        assert self_trip.minutes == min(t.minutes for t in trips), origin


def test_commute_matrix_matches_generator():
    """El CSV versionado coincide con build_commute_matrix (evita ediciones a mano que derivan)."""
    with open(SEED_DIR / "commute_matrix.csv", encoding="utf-8", newline="") as f:
        committed = list(csv.DictReader(f))
    expected = [{k: str(v) for k, v in r.items()} for r in build_commute_matrix.build()]
    assert committed == expected


# --- Claves foráneas ---------------------------------------------------------------


def test_postings_reference_existing_entities(bundle):
    locs = {x.key for x in bundle.locations}
    skills = {x.key for x in bundle.skills}
    companies = {x.key for x in bundle.companies}
    for p in bundle.postings:
        assert p.location in locs and p.company in companies, p.key
        assert all(r.skill in skills for r in p.requirements), p.key
        assert any(r.required for r in p.requirements), f"{p.key}: sin requisito obligatorio"


def test_courses_reference_existing_entities(bundle):
    centers = {x.key for x in bundle.training_centers}
    skills = {x.key for x in bundle.skills}
    for c in bundle.courses:
        assert c.center in centers, c.key
        assert set(c.skills) <= skills, c.key
        assert 1 <= len(c.sessions) <= 3
        for s in c.sessions:
            assert s.seats_taken <= s.seats_total


def test_youth_reference_existing_entities(bundle):
    locs = {x.key for x in bundle.locations}
    skills = {x.key for x in bundle.skills}
    for y in bundle.youth:
        assert y.location in locs, y.key
        assert {s.skill for s in y.skills} <= skills, y.key
        assert all(s.evidence.strip() for s in y.skills), y.key


def test_bundle_rejects_dangling_foreign_key(bundle):
    data = bundle.model_dump()
    data["postings"][0]["requirements"][0]["skill"] = "habilidad-inexistente"
    with pytest.raises(ValueError, match="habilidad-inexistente"):
        type(bundle).model_validate(data)


def test_built_rows_foreign_keys_resolve(rows):
    ids = {t: {r["id"] for r in rows[t] if "id" in r} for t in TABLE_ORDER}
    for r in rows["commute_matrix"]:
        assert r["origin_id"] in ids["location"] and r["dest_id"] in ids["location"]
    for r in rows["job_posting"]:
        assert r["company_id"] in ids["company"] and r["location_id"] in ids["location"]
    for r in rows["posting_requirement"]:
        assert r["posting_id"] in ids["job_posting"] and r["skill_id"] in ids["skill"]
    for r in rows["course_skill"]:
        assert r["course_id"] in ids["course"] and r["skill_id"] in ids["skill"]
    for r in rows["course_session"]:
        assert r["course_id"] in ids["course"]
    for r in rows["profile_skill"]:
        assert r["youth_id"] in ids["youth"] and r["skill_id"] in ids["skill"]


def test_ids_are_unique_and_deterministic(rows):
    all_ids = [r["id"] for t in TABLE_ORDER for r in rows[t] if "id" in r]
    assert len(all_ids) == len(set(all_ids))
    assert seed_uuid("location", "barrio-balboa") == seed_uuid("location", "barrio-balboa")
    assert seed_uuid("location", "barrio-balboa") != seed_uuid("skill", "barrio-balboa")


# --- Marcado sintético y persona demo ----------------------------------------------


def test_synthetic_data_is_flagged(bundle):
    assert all(y.is_synthetic for y in bundle.youth)
    assert all(p.is_synthetic and p.source for p in bundle.postings)
    assert all(c.is_synthetic for c in bundle.companies)


def test_ana_matches_prd_persona(bundle):
    ana = next(y for y in bundle.youth if y.key == "ana")
    assert ana.birth_year == 2005  # 21 años en 2026
    assert ana.location == "barrio-balboa"  # La Chorrera
    assert ana.studying and ana.transport_budget_daily <= 4
    assert ana.cv_raw_text is None  # sin CV formal
    assert {"manejo-de-caja", "control-de-inventario", "atencion-al-cliente"} <= {s.skill for s in ana.skills}
    # Ana estudia de noche: su disponibilidad termina antes de las 18:00.
    assert all(s.end <= "18:00" for s in ana.availability)


def test_ana_has_reachable_clean_posting(bundle):
    """El demo necesita al menos una oferta limpia que Ana pueda alcanzar en tiempo y presupuesto."""
    ana = next(y for y in bundle.youth if y.key == "ana")
    labels = {lab.posting: lab for lab in bundle.discrimination_labels}
    commute = {(c.origin, c.dest): c for c in bundle.commute}
    ana_skills = {s.skill for s in ana.skills}
    reachable = [
        p
        for p in bundle.postings
        if not labels[p.key].discriminatory
        and commute[(ana.location, p.location)].minutes <= ana.max_commute_min
        and commute[(ana.location, p.location)].cost_daily <= ana.transport_budget_daily
        and {r.skill for r in p.requirements if r.required} <= ana_skills
    ]
    assert reachable


def test_youth_matches_generator():
    committed = json.loads((SEED_DIR / "youth.json").read_text(encoding="utf-8"))
    assert committed == build_youth.build()


def test_youth_diversity_for_counterfactual_audit(bundle):
    genders = Counter(y.gender for y in bundle.youth)
    assert genders["femenino"] >= 10 and genders["masculino"] >= 10
    assert len({y.location for y in bundle.youth}) >= 15


# --- Etiquetas de discriminación (para guardrail y evals) --------------------------


def test_every_posting_has_a_discrimination_label(bundle):
    labelled = [lab.posting for lab in bundle.discrimination_labels]
    assert sorted(labelled) == sorted(p.key for p in bundle.postings)


def test_discriminatory_postings(bundle):
    postings = {p.key: p for p in bundle.postings}
    flagged = [lab for lab in bundle.discrimination_labels if lab.discriminatory]
    assert len(flagged) >= 3
    kinds = {f.kind for lab in flagged for f in lab.findings}
    assert {"edad", "genero", "apariencia", "foto", "estado_civil"} <= kinds
    for lab in flagged:
        assert lab.findings
        posting = postings[lab.posting]
        assert posting.status == "borrador", "las discriminatorias esperan al auditor"
        for f in lab.findings:
            assert f.text in posting.raw_input, (lab.posting, f.text)


def test_clean_postings_have_no_findings(bundle):
    clean = [lab for lab in bundle.discrimination_labels if not lab.discriminatory]
    assert all(not lab.findings for lab in clean)
    # Controles de precisión: requisitos legítimos que parecen sensibles.
    assert sum(1 for lab in clean if lab.notes) >= 2


# --- Inserción en BD ---------------------------------------------------------------


def _doc05_metadata():
    """Metadata mínima con las tablas semilla del doc 05 (para probar el loader sin models.py)."""
    sa = pytest.importorskip("sqlalchemy")
    md = sa.MetaData()
    uid = lambda name, *a, **k: sa.Column(name, sa.Uuid, *a, **k)
    sa.Table(
        "location",
        md,
        uid("id", primary_key=True),
        sa.Column("corregimiento", sa.String, nullable=False),
        sa.Column("distrito", sa.String),
        sa.Column("provincia", sa.String),
        sa.Column("lat", sa.Float),
        sa.Column("lng", sa.Float),
    )
    sa.Table(
        "commute_matrix",
        md,
        uid("origin_id", sa.ForeignKey("location.id"), primary_key=True),
        uid("dest_id", sa.ForeignKey("location.id"), primary_key=True),
        sa.Column("minutes", sa.Integer),
        sa.Column("cost_daily", sa.Numeric(8, 2)),
        sa.Column("mode", sa.String),
    )
    sa.Table(
        "skill",
        md,
        uid("id", primary_key=True),
        sa.Column("esco_uri", sa.String),
        sa.Column("label_es", sa.String),
        sa.Column("group", sa.String),
        sa.Column("aliases", sa.JSON),
    )
    sa.Table(
        "company",
        md,
        uid("id", primary_key=True),
        sa.Column("name", sa.String),
        uid("location_id", sa.ForeignKey("location.id")),
        sa.Column("contact_email", sa.String),
    )
    sa.Table(
        "job_posting",
        md,
        uid("id", primary_key=True),
        uid("company_id", sa.ForeignKey("company.id")),
        sa.Column("title", sa.String),
        sa.Column("raw_input", sa.Text),
        sa.Column("input_type", sa.String),
        uid("location_id", sa.ForeignKey("location.id")),
        sa.Column("schedule", sa.JSON),
        sa.Column("salary_min", sa.Numeric(8, 2)),
        sa.Column("salary_max", sa.Numeric(8, 2)),
        sa.Column("vacancies", sa.Integer),
        sa.Column("status", sa.String),
    )
    sa.Table(
        "posting_requirement",
        md,
        uid("posting_id", sa.ForeignKey("job_posting.id"), primary_key=True),
        uid("skill_id", sa.ForeignKey("skill.id"), primary_key=True),
        sa.Column("weight", sa.Integer),
        sa.Column("required", sa.Boolean),
    )
    sa.Table(
        "training_center",
        md,
        uid("id", primary_key=True),
        sa.Column("name", sa.String),
        uid("location_id", sa.ForeignKey("location.id")),
    )
    sa.Table(
        "course",
        md,
        uid("id", primary_key=True),
        uid("center_id", sa.ForeignKey("training_center.id")),
        sa.Column("title", sa.String),
        sa.Column("hours", sa.Integer),
        sa.Column("cost", sa.Numeric(8, 2)),
    )
    sa.Table(
        "course_skill",
        md,
        uid("course_id", sa.ForeignKey("course.id"), primary_key=True),
        uid("skill_id", sa.ForeignKey("skill.id"), primary_key=True),
    )
    sa.Table(
        "course_session",
        md,
        uid("id", primary_key=True),
        uid("course_id", sa.ForeignKey("course.id")),
        sa.Column("schedule", sa.JSON),
        sa.Column("start_date", sa.Date),
        sa.Column("seats_total", sa.Integer),
        sa.Column("seats_taken", sa.Integer),
    )
    sa.Table(
        "youth",
        md,
        uid("id", primary_key=True),
        sa.Column("display_name", sa.String),
        sa.Column("birth_year", sa.Integer),
        sa.Column("gender", sa.String),
        uid("location_id", sa.ForeignKey("location.id")),
        sa.Column("max_commute_min", sa.Integer),
        sa.Column("transport_budget_daily", sa.Numeric(8, 2)),
        sa.Column("availability", sa.JSON),
        sa.Column("min_salary", sa.Numeric(8, 2)),
        sa.Column("studying", sa.Boolean),
        sa.Column("cv_raw_text", sa.Text),
        sa.Column("is_synthetic", sa.Boolean),
    )
    sa.Table(
        "profile_skill",
        md,
        uid("youth_id", sa.ForeignKey("youth.id"), primary_key=True),
        uid("skill_id", sa.ForeignKey("skill.id"), primary_key=True),
        sa.Column("level", sa.Integer),
        sa.Column("source", sa.String),
        sa.Column("evidence", sa.Text, nullable=False),
    )
    return md


def _seed_and_check(metadata):
    sa = pytest.importorskip("sqlalchemy")
    from sqlalchemy.orm import Session

    from puente_api.db.seed import seed_database

    engine = sa.create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with Session(engine) as session:
        counts = seed_database(session, metadata=metadata)
        session.commit()
        assert counts["location"] == 50 and counts["job_posting"] == 25 and counts["youth"] == 40
        n = session.execute(sa.select(sa.func.count()).select_from(metadata.tables["commute_matrix"])).scalar_one()
        assert n == 2500
        assert seed_database(session, metadata=metadata) == {}, "segunda carga debe ser no-op"
        again = seed_database(session, metadata=metadata, reset=True)
        assert again == counts


def test_seed_database_with_doc05_schema():
    _seed_and_check(_doc05_metadata())


def test_seed_database_with_project_models():
    models = pytest.importorskip("puente_api.db.models")
    _seed_and_check(models.Base.metadata)
