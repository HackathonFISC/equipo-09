"""Carga los archivos semilla en la base de datos.

Tres capas, de la más pura a la que toca la BD:

1. `read_seed_bundle()` lee los CSV/JSON y los valida (`SeedBundle`, incluye FKs).
2. `build_rows()` convierte el bundle en filas por tabla con los nombres de columna del
   doc 05 y UUIDs deterministas (`seed_uuid`). No depende de SQLAlchemy.
3. `seed_database(session)` inserta esas filas usando la metadata de
   `puente_api.db.models`. Usa inserts de Core sobre `Base.metadata.tables`, así no
   depende de los nombres de las clases ORM; las claves que la tabla no tenga se
   descartan con un aviso en el log (p. ej. `is_synthetic` en `job_posting`).
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from puente_api.db.seed.schemas import SeedBundle

if TYPE_CHECKING:
    from sqlalchemy import MetaData
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent
SEED_NAMESPACE = uuid.UUID("6f0b6c1e-5a8e-4c51-9b39-70a4e2f2d409")

# Orden de inserción (respeta FKs). El borrado con reset=True va en orden inverso.
TABLE_ORDER = [
    "location",
    "commute_matrix",
    "skill",
    "company",
    "job_posting",
    "posting_requirement",
    "training_center",
    "course",
    "course_skill",
    "course_session",
    "youth",
    "profile_skill",
]

# Nombres alternativos de columna por si models.py se aparta del doc 05.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "group": ("group_name", "skill_group"),
    "origin_id": ("origin_location_id",),
    "dest_id": ("dest_location_id", "destination_id"),
    "center_id": ("training_center_id",),
}


def seed_uuid(kind: str, key: str) -> uuid.UUID:
    """UUID estable para una entidad semilla: `uuid5(SEED_NAMESPACE, "kind:key")`.

    `kind` es el nombre de la tabla (`location`, `skill`, `job_posting`, `youth`, ...).
    Para sesiones de curso la clave es `"<curso>:<sesión>"`, p. ej. `"excel-basico-intermedio:s2"`.
    """
    return uuid.uuid5(SEED_NAMESPACE, f"{kind}:{key}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_seed_bundle(seed_dir: Path = SEED_DIR) -> SeedBundle:
    """Lee y valida todos los archivos semilla de `seed_dir`."""
    courses = _read_json(seed_dir / "courses.json")
    return SeedBundle.model_validate(
        {
            "locations": [
                {**r, "metro": r["metro"] == "1"} for r in _read_csv(seed_dir / "locations.csv")
            ],
            "commute": _read_csv(seed_dir / "commute_matrix.csv"),
            "skills": _read_csv(seed_dir / "skills.csv"),
            "companies": _read_json(seed_dir / "companies.json"),
            "postings": _read_json(seed_dir / "postings.json"),
            "discrimination_labels": _read_json(seed_dir / "discrimination_labels.json"),
            "training_centers": courses["training_centers"],
            "courses": courses["courses"],
            "youth": _read_json(seed_dir / "youth.json"),
        }
    )


def build_rows(bundle: SeedBundle) -> dict[str, list[dict[str, Any]]]:
    """Filas por tabla con nombres de columna del doc 05 (sin SQLAlchemy)."""

    def loc(k: str) -> uuid.UUID:
        return seed_uuid("location", k)

    def skill(k: str) -> uuid.UUID:
        return seed_uuid("skill", k)

    rows: dict[str, list[dict[str, Any]]] = {t: [] for t in TABLE_ORDER}
    rows["location"] = [
        {
            "id": loc(x.key),
            "corregimiento": x.corregimiento,
            "distrito": x.distrito,
            "provincia": x.provincia,
            "lat": x.lat,
            "lng": x.lng,
        }
        for x in bundle.locations
    ]
    rows["commute_matrix"] = [
        {
            "origin_id": loc(x.origin),
            "dest_id": loc(x.dest),
            "minutes": x.minutes,
            "cost_daily": x.cost_daily,
            "mode": x.mode,
        }
        for x in bundle.commute
    ]
    rows["skill"] = [
        {
            "id": skill(x.key),
            "esco_uri": x.esco_uri,
            "label_es": x.label_es,
            "group": x.group,
            "aliases": list(x.aliases),
        }
        for x in bundle.skills
    ]
    rows["company"] = [
        {
            "id": seed_uuid("company", x.key),
            "name": x.name,
            "location_id": loc(x.location),
            "contact_email": x.contact_email,
            "is_synthetic": x.is_synthetic,
        }
        for x in bundle.companies
    ]
    for p in bundle.postings:
        pid = seed_uuid("job_posting", p.key)
        rows["job_posting"].append(
            {
                "id": pid,
                "company_id": seed_uuid("company", p.company),
                "title": p.title,
                "raw_input": p.raw_input,
                "input_type": p.input_type,
                "location_id": loc(p.location),
                "schedule": [s.model_dump() for s in p.schedule],
                "salary_min": p.salary_min,
                "salary_max": p.salary_max,
                "vacancies": p.vacancies,
                "status": p.status,
                "is_synthetic": p.is_synthetic,
                "source": p.source,
            }
        )
        rows["posting_requirement"] += [
            {
                "id": seed_uuid("posting_requirement", f"{p.key}:{r.skill}"),
                "posting_id": pid,
                "skill_id": skill(r.skill),
                "weight": r.weight,
                "required": r.required,
            }
            for r in p.requirements
        ]
    rows["training_center"] = [
        {
            "id": seed_uuid("training_center", x.key),
            "name": x.name,
            "location_id": loc(x.location),
            "is_synthetic": x.is_synthetic,
        }
        for x in bundle.training_centers
    ]
    for c in bundle.courses:
        cid = seed_uuid("course", c.key)
        rows["course"].append(
            {
                "id": cid,
                "center_id": seed_uuid("training_center", c.center),
                "title": c.title,
                "hours": c.hours,
                "cost": c.cost,
                "is_synthetic": c.is_synthetic,
            }
        )
        rows["course_skill"] += [{"course_id": cid, "skill_id": skill(s)} for s in c.skills]
        rows["course_session"] += [
            {
                "id": seed_uuid("course_session", f"{c.key}:{s.key}"),
                "course_id": cid,
                "schedule": [t.model_dump() for t in s.schedule],
                "start_date": s.start_date,
                "seats_total": s.seats_total,
                "seats_taken": s.seats_taken,
            }
            for s in c.sessions
        ]
    for y in bundle.youth:
        yid = seed_uuid("youth", y.key)
        rows["youth"].append(
            {
                "id": yid,
                "display_name": y.display_name,
                "birth_year": y.birth_year,
                "gender": y.gender,
                "location_id": loc(y.location),
                "max_commute_min": y.max_commute_min,
                "transport_budget_daily": y.transport_budget_daily,
                "availability": [s.model_dump() for s in y.availability],
                "min_salary": y.min_salary,
                "studying": y.studying,
                "cv_raw_text": y.cv_raw_text,
                "is_synthetic": y.is_synthetic,
            }
        )
        rows["profile_skill"] += [
            {
                "id": seed_uuid("profile_skill", f"{y.key}:{s.skill}"),
                "youth_id": yid,
                "skill_id": skill(s.skill),
                "level": s.level,
                "source": s.source,
                "evidence": s.evidence,
            }
            for s in y.skills
        ]
    return rows


def _metadata() -> MetaData:
    from puente_api.db import models

    base = getattr(models, "Base", None)
    if base is None or not hasattr(base, "metadata"):
        raise RuntimeError(
            "puente_api.db.models debe exponer `Base` (DeclarativeBase) con `metadata`"
        )
    return base.metadata


def _adapt(
    table_name: str, columns: Iterable[Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Ajusta las filas a las columnas reales: aplica alias, descarta lo que sobra y
    convierte UUID a str cuando la columna es de texto."""
    cols = {c.name: c for c in columns}
    rename: dict[str, str] = {}
    dropped: set[str] = set()
    for key in rows[0] if rows else {}:
        if key in cols:
            continue
        alt = next((a for a in COLUMN_ALIASES.get(key, ()) if a in cols), None)
        if alt:
            rename[key] = alt
        else:
            dropped.add(key)
    if dropped:
        log.warning(
            "seed %s: columnas sin equivalente en el modelo, se omiten: %s",
            table_name,
            sorted(dropped),
        )

    str_cols = set()
    for name, col in cols.items():
        try:
            if col.type.python_type is str:
                str_cols.add(name)
        except NotImplementedError:
            pass

    out = []
    for row in rows:
        new = {}
        for k, v in row.items():
            if k in dropped:
                continue
            name = rename.get(k, k)
            if isinstance(v, uuid.UUID) and name in str_cols:
                v = str(v)
            new[name] = v
        out.append(new)
    return out


def seed_database(
    session: Session,
    *,
    bundle: SeedBundle | None = None,
    metadata: MetaData | None = None,
    reset: bool = False,
) -> dict[str, int]:
    """Inserta los datos semilla y devuelve `{tabla: filas insertadas}`.

    Idempotente: si `location` ya tiene filas y `reset` es False, no inserta nada y
    devuelve `{}`. Con `reset=True` borra primero las tablas semilla (orden inverso).
    No hace commit: el llamador decide (`session.commit()`).
    """
    from sqlalchemy import delete, func, insert, select

    metadata = metadata if metadata is not None else _metadata()
    missing = [t for t in TABLE_ORDER if t not in metadata.tables]
    if missing:
        raise RuntimeError(f"Faltan tablas en models.py para cargar seeds: {missing}")
    tables = {t: metadata.tables[t] for t in TABLE_ORDER}

    if reset:
        for name in reversed(TABLE_ORDER):
            session.execute(delete(tables[name]))
    elif session.execute(select(func.count()).select_from(tables["location"])).scalar_one() > 0:
        log.info("seed: la tabla location ya tiene datos; no se inserta nada")
        return {}

    rows = build_rows(bundle or read_seed_bundle())
    counts: dict[str, int] = {}
    for name in TABLE_ORDER:
        table = tables[name]
        data = _adapt(name, table.columns, rows[name])
        if data:
            session.execute(insert(table), data)
        counts[name] = len(data)
    session.flush()
    log.info("seed: %s", counts)
    return counts
