"""Fixture mínimo (2–3 filas por tabla) solo para tests; los seeds reales son de Sebastian."""

import os

os.environ["DATABASE_URL"] = "sqlite://"  # nunca tocar puente.db desde los tests

from collections.abc import Iterator  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from puente_api.db import models  # noqa: E402
from puente_api.db.session import get_db  # noqa: E402
from puente_api.main import app  # noqa: E402

LOC_A = "00000000-0000-0000-0000-00000000000a"
LOC_B = "00000000-0000-0000-0000-00000000000b"
SK_CAJA = "00000000-0000-0000-0001-000000000001"
SK_ATENCION = "00000000-0000-0000-0001-000000000002"
SK_EXCEL = "00000000-0000-0000-0001-000000000003"
COMPANY = "00000000-0000-0000-0002-000000000001"
POST_OK = "00000000-0000-0000-0003-000000000001"
POST_BLOCKED = "00000000-0000-0000-0003-000000000002"


def load_fixture(session: Session) -> None:
    session.add_all(
        [
            models.Location(
                id=LOC_A,
                corregimiento="Bella Vista",
                distrito="Panamá",
                provincia="Panamá",
                lat=8.98,
                lng=-79.52,
            ),
            models.Location(
                id=LOC_B,
                corregimiento="Belisario Porras",
                distrito="San Miguelito",
                provincia="Panamá",
            ),
            models.Skill(
                id=SK_CAJA,
                label_es="Manejo de caja",
                group="comercio",
                esco_uri="http://data.europa.eu/esco/skill/caja",
                aliases=["cajero"],
            ),
            models.Skill(
                id=SK_ATENCION,
                label_es="Atención al cliente",
                group="servicio",
                aliases=["servicio al cliente"],
            ),
            models.Skill(
                id=SK_EXCEL, label_es="Hojas de cálculo", group="digital", aliases=["Excel"]
            ),
            models.Company(id=COMPANY, name="Super Ejemplo", location_id=LOC_A),
        ]
    )
    session.flush()
    session.add_all(
        [
            models.JobPosting(
                id=POST_OK,
                company_id=COMPANY,
                title="Cajero/a",
                input_type="texto",
                location_id=LOC_A,
                status="publicada",
                vacancies=2,
                salary_min=Decimal("600.00"),
                salary_max=Decimal("700.50"),
                schedule=[{"day": "lun", "start": "08:00", "end": "16:00"}],
                requirements=[
                    models.PostingRequirement(skill_id=SK_CAJA, weight=3, required=True),
                    models.PostingRequirement(skill_id=SK_ATENCION, weight=2, required=False),
                ],
            ),
            models.JobPosting(
                id=POST_BLOCKED,
                company_id=COMPANY,
                title="Recepcionista",
                input_type="foto",
                location_id=LOC_B,
                status="bloqueada",
                # Formato del doc 05; la API lo normaliza a day/start/end.
                schedule=[{"dia": "sab", "inicio": "09:00", "fin": "13:00"}],
            ),
        ]
    )
    session.flush()
    session.add(
        models.AuditCheck(
            posting_id=POST_BLOCKED,
            kind="discriminacion",
            variable="genero",
            passed=False,
            findings=["Pide «solo mujeres»"],
        )
    )
    session.commit()


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        load_fixture(session)
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def _get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
