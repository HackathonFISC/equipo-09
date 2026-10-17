"""Un test por regla de discriminación + controles de precisión + contra los 25 seeds."""

import json
from pathlib import Path

import pytest

from puente_api.guardrails import detect_discrimination

SEED = Path(__file__).parents[2] / "src" / "puente_api" / "db" / "seed"


def kinds(text: str) -> set[str]:
    return set(detect_discrimination(text).kinds)


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("Personal de 18 a 25 años", "edad_rango"),
        ("Se requiere entre 20 y 28 años", "edad_rango"),
        ("Menores de 35 años", "edad_tope"),
        ("Edad máxima 30", "edad_expresion"),
        ("Máximo 30 años", "edad_tope"),
        ("Solo mujeres", "genero_explicito"),
        ("Solo varones para bodega", "genero_explicito"),
        ("Se busca mesera con experiencia", "genero_titulo_femenino"),
        ("Recepcionista soltera", "genero_titulo_femenino"),
        ("Se requiere buena presencia", "apariencia"),
        ("Excelente presentación personal", "apariencia"),
        ("Enviar foto reciente", "foto"),
        ("Adjuntar fotografía", "foto"),
        ("Sin hijos y con disponibilidad", "estado_civil"),
        ("Estado civil: soltero", "estado_civil"),
        ("Prueba de embarazo negativa", "embarazo"),
        ("No residentes de Curundú", "residencia"),
        ("Residentes de Costa del Este", "residencia"),
        ("Solo panameños", "nacionalidad"),
        ("No se aceptan extranjeros", "nacionalidad"),
    ],
)
def test_cada_regla_dispara(text: str, rule_id: str):
    ids = {f.rule_id for f in detect_discrimination(text).findings}
    assert rule_id in ids


@pytest.mark.parametrize(
    "text",
    [
        "Mayores de 18 años",  # mínimo legal
        "Cajero/a con experiencia",  # forma inclusiva
        "Cajero(a) de minisúper",
        "Licencia de conducir vigente",
        "Carné de manipulador de alimentos vigente",
        "Mínimo 10 años de experiencia en bodega",  # edad ≠ experiencia
        "Hasta 12 horas de turno",
        "Residente de Panamá con cédula",
        "Barista con experiencia en caja",
        "",
    ],
)
def test_requisitos_legitimos_no_se_marcan(text: str):
    assert not detect_discrimination(text).discriminatory


def test_normaliza_tildes_y_mayusculas():
    assert "apariencia" in kinds("BUENA PRESENCIA")
    assert "apariencia" in kinds("buena presencia")
    assert "edad" in kinds("MÁXIMO 30 AÑOS")


def test_hallazgo_apunta_al_texto_original():
    text = "Buscamos Cajeras. Máximo 30 años."
    report = detect_discrimination(text)
    for f in report.findings:
        assert text[f.start : f.end] == f.text
    assert {f.text for f in report.findings} == {"Cajeras", "Máximo 30 años"}


def test_mensajes_para_audit_check():
    msgs = detect_discrimination("Mujeres de 18 a 25 años").messages()
    assert any(m.startswith("Restricción de género") for m in msgs)
    assert any(m.startswith("Restricción de edad") for m in msgs)


def test_no_fusiona_tipos_distintos_ni_duplica_el_mismo_tramo():
    r = detect_discrimination("buena presencia")
    assert len(r.findings) == 1


def test_seeds_etiquetados_recall_y_precision_100():
    postings = {
        p["key"]: p["raw_input"]
        for p in json.loads((SEED / "postings.json").read_text(encoding="utf-8"))
    }
    labels = json.loads((SEED / "discrimination_labels.json").read_text(encoding="utf-8"))
    assert len(labels) >= 20
    for label in labels:
        report = detect_discrimination(postings[label["posting"]])
        expected = {f["kind"] for f in label["findings"]}
        assert report.discriminatory == label["discriminatory"], label["posting"]
        assert report.kinds == expected, label["posting"]
