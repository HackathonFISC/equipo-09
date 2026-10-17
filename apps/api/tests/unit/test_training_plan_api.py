"""`/youth/{id}/training-plan`: solver real, explicación del LLM verificada y traza."""

# ruff: noqa: F811  (los fixtures importados se usan como argumentos)

import json
from datetime import date
from types import SimpleNamespace

import pytest

from puente_api.config import Settings
from puente_api.db import models
from puente_api.graph.nodes.formacion import verify_explanation
from puente_api.llm import LLMClient, get_llm
from puente_api.main import app
from tests.unit.conftest import LOC_A, SK_CAJA

API = "/api/v1"
YOUTH = "00000000-0000-0000-0005-000000000001"
CENTER = "00000000-0000-0000-0006-000000000001"
COURSE = "00000000-0000-0000-0007-000000000001"
SESSION = "00000000-0000-0000-0008-000000000001"


class ExplainLLM:
    """Responde al agente de Formación; `text=None` simula una salida inválida."""

    def __init__(self, text: str | None):
        self.text, self.calls = text, 0

    def __call__(self, **_kwargs):
        self.calls += 1
        content = json.dumps({"explanation": self.text}) if self.text else "no es json"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _use(fake: ExplainLLM) -> ExplainLLM:
    settings = Settings(
        _env_file=None,
        llm_model="fake/m",
        llm_model_fast="fake/m",
        llm_fallback_model=None,
        llm_max_retries=0,
    )
    app.dependency_overrides[get_llm] = lambda: LLMClient(settings=settings, completion=fake)
    return fake


@pytest.fixture
def catalog(session_factory):
    """Joven sin la habilidad de caja, una oferta que la exige y un curso que la enseña."""
    with session_factory() as s:
        s.add_all(
            [
                models.CommuteMatrix(
                    origin_id=LOC_A, dest_id=LOC_A, minutes=15, cost_daily=0.5, mode="bus"
                ),
                models.Youth(
                    id=YOUTH,
                    display_name="Ana",
                    birth_year=2004,
                    location_id=LOC_A,
                    max_commute_min=60,
                    transport_budget_daily=5,
                    availability=[{"day": "lun", "start": "07:00", "end": "17:00"}],
                ),
                models.TrainingCenter(id=CENTER, name="INADEH", location_id=LOC_A),
            ]
        )
        s.flush()
        s.add(
            models.Course(
                id=COURSE,
                center_id=CENTER,
                title="Caja y atención",
                hours=20,
                cost=15,
                skills=[models.CourseSkill(skill_id=SK_CAJA)],
                sessions=[
                    models.CourseSession(
                        id=SESSION,
                        schedule=[{"day": "lun", "start": "09:00", "end": "11:00"}],
                        start_date=date(2026, 11, 2),
                        seats_total=20,
                        seats_taken=3,
                    )
                ],
            )
        )
        s.commit()


def _post(client):
    return client.post(f"{API}/youth/{YOUTH}/training-plan")


def test_plan_is_computed_by_the_solver_and_explained_by_the_llm(client, catalog):
    fake = _use(ExplainLLM("Toma «Caja y atención»: cuesta 15 en total y desbloquea 1 oferta."))
    # Antes de calcular no hay ruta.
    assert client.get(f"{API}/youth/{YOUTH}/training-plan").status_code == 404

    res = _post(client)
    assert res.status_code == 202, res.text
    body = res.json()
    assert fake.calls == 1

    plan = client.get(f"{API}/youth/{YOUTH}/training-plan").json()
    assert plan["id"] == body["resourceId"] and plan["youthId"] == YOUTH
    [item] = plan["items"]
    assert item["courseTitle"] == "Caja y atención" and item["commuteMin"] == 15
    assert item["session"] == {
        "id": SESSION,
        "schedule": [{"day": "lun", "start": "09:00", "end": "11:00"}],
        "startDate": "2026-11-02",
        "seatsTotal": 20,
        "seatsTaken": 3,
    }
    assert plan["unlockedPostings"] == 1 and plan["totalCost"] > 15  # matrícula + transporte
    assert plan["explanation"].startswith("Toma «Caja y atención»")

    steps = client.get(f"{API}/traces/{body['threadId']}").json()["steps"]
    assert [s["agent"] for s in steps] == ["supervisor", "formacion"]
    step = steps[-1]
    assert step["tool"].startswith("OR-Tools MIP") and "llm: fake/m" in step["tool"]
    assert "desbloquea 1 oferta" in step["decision"]
    assert "verificada contra el solver" in step["reason"]
    assert step["outputSummary"].startswith(f"plan {plan['id']}")


def test_invalid_llm_output_falls_back_to_the_solver_text(client, catalog):
    _use(ExplainLLM(None))
    assert _post(client).status_code == 202
    plan = client.get(f"{API}/youth/{YOUTH}/training-plan").json()
    assert plan["explanation"].startswith("Ruta de 1 curso(s): Caja y atención")
    thread = client.get(f"{API}/traces").json()[0]["threadId"]
    reason = client.get(f"{API}/traces/{thread}").json()["steps"][-1]["reason"]
    assert "valor por defecto seguro" in reason


def test_llm_that_invents_figures_is_replaced_by_the_solver_text(client, catalog):
    _use(ExplainLLM("Cuesta solo 5 balboas y te consigue 40 vacantes."))
    assert _post(client).status_code == 202
    plan = client.get(f"{API}/youth/{YOUTH}/training-plan").json()
    assert "40" not in plan["explanation"] and plan["explanation"].startswith("Ruta de 1 curso")
    thread = client.get(f"{API}/traces").json()[0]["threadId"]
    reason = client.get(f"{API}/traces/{thread}").json()["steps"][-1]["reason"]
    assert "cifras ajenas" in reason


def test_latest_plan_wins_and_empty_plan_skips_the_llm(client, catalog, session_factory):
    fake = _use(ExplainLLM("Toma el curso por 15."))
    first = _post(client).json()["resourceId"]
    # Si el joven ya tiene la habilidad no hay brecha: plan vacío sin llamar al LLM.
    with session_factory() as s:
        s.add(
            models.ProfileSkill(
                youth_id=YOUTH, skill_id=SK_CAJA, level=2, source="cv", evidence="e"
            )
        )
        s.commit()
    calls_before = fake.calls
    second = _post(client).json()["resourceId"]
    assert second != first and fake.calls == calls_before

    plan = client.get(f"{API}/youth/{YOUTH}/training-plan").json()
    assert plan["id"] == second and plan["items"] == [] and plan["unlockedPostings"] == 0
    assert (
        plan["explanation"]
        == "No hay brechas de habilidades que cerrar con la formación disponible."
    )


def test_unknown_youth_is_404(client):
    missing = "00000000-0000-0000-0005-0000000000ff"
    assert client.get(f"{API}/youth/{missing}/training-plan").status_code == 404
    assert client.post(f"{API}/youth/{missing}/training-plan").status_code == 404


def test_verify_explanation_only_allows_known_figures():
    facts = "Ruta de 1 curso(s). Costo total estimado B/. 15.50. Desbloquea 2 oferta(s)."
    assert verify_explanation("Pagas 15,50 y se abren 2 ofertas.", facts)
    assert verify_explanation("Es un buen curso.", facts)
    assert not verify_explanation("Pagas 20 en total.", facts)
    assert not verify_explanation("   ", facts)
