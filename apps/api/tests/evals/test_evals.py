"""Evals deterministas (`pnpm --filter api evals`): un test por caso de `cases/*.json`."""

import pytest

from tests.evals.runner import load_cases, run_all, run_case

CASES = load_cases()
REQUIRED_KEYS = {"id", "category", "type", "description", "metric", "input", "expected"}


def test_suite_has_at_least_20_cases_in_every_area():
    assert len(CASES) >= 20
    assert {c["category"] for c in CASES} >= {"matching", "auditor", "guardrails", "formacion"}
    assert len({c["id"] for c in CASES}) == len(CASES), "ids de caso repetidos"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case):
    assert case.keys() >= REQUIRED_KEYS
    res = run_case(case)
    assert res.passed, f"{case['id']} ({case['metric']}): " + "; ".join(res.problems)


def test_evals_are_deterministic():
    first = [(r.id, r.passed, r.problems) for r in run_all()]
    second = [(r.id, r.passed, r.problems) for r in run_all()]
    assert first == second
