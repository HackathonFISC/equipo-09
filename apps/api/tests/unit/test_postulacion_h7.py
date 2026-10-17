"""H7: verificador de Postulación sin falsos positivos y holguras visibles en la lista corta."""

from types import SimpleNamespace

from puente_api.db import models
from puente_api.graph.nodes.postulacion import foreign_skills, slack_notes
from puente_api.graph.taxonomy import SkillIndex, fold


def _index(*skills: models.Skill) -> SkillIndex:
    by_key = {}
    for s in skills:
        for name in [s.label_es, *s.aliases]:
            by_key.setdefault(fold(name), s)
    return SkillIndex(by_key=by_key, labels=sorted(s.label_es for s in skills))


EQUIPO = models.Skill(
    id="eq", label_es="Trabajo en equipo", group="transversal", aliases=["colaboración", "equipo"]
)
RESP = models.Skill(
    id="re", label_es="Responsabilidad", group="transversal", aliases=["compromiso", "responsable"]
)
CAJA = models.Skill(id="ca", label_es="Manejo de caja", group="comercio", aliases=["caja"])
INDEX = _index(EQUIPO, RESP, CAJA)


def test_common_words_in_a_letter_are_not_claimed_skills():
    letter = "Estimado equipo de La Canasta: soy responsable y tengo compromiso con mi trabajo."
    assert foreign_skills(letter, set(), INDEX) == []


def test_full_soft_skill_labels_and_technical_aliases_are_still_caught():
    text = "Destaco mi Responsabilidad y el trabajo en equipo; manejé la caja."
    assert foreign_skills(text, set(), INDEX) == [
        "Manejo de caja",
        "Responsabilidad",
        "Trabajo en equipo",
    ]
    assert foreign_skills(text, {"eq", "re", "ca"}, INDEX) == []


def test_slack_notes_explain_each_tolerance_used():
    youth = SimpleNamespace(max_commute_min=30, transport_budget_daily=2.0)
    checked = {
        "slacks": [
            {"constraint": "traslado_max", "amount": 12, "penalty": 120},
            {"constraint": "presupuesto_transporte", "amount": 0.4, "penalty": 40},
            {"constraint": "habilidades_obligatorias", "amount": 1, "penalty": 200},
        ]
    }
    assert slack_notes(youth, checked) == [
        "Traslado 12 min sobre su máximo (30 min)",
        "Costo B/. 0.40 sobre su presupuesto diario (B/. 2.00)",
        "Le falta 1 habilidad(es) obligatoria(s)",
    ]
    assert slack_notes(youth, {}) == []
