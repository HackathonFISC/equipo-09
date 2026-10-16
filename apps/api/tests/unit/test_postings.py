from tests.unit.conftest import COMPANY, LOC_A, POST_BLOCKED, POST_OK, SK_CAJA


def _by_id(items):
    return {item["id"]: item for item in items}


def test_list_postings_matches_contract(client):
    res = client.get("/api/v1/postings")
    assert res.status_code == 200
    postings = _by_id(res.json())
    assert set(postings) == {POST_OK, POST_BLOCKED}

    ok = postings[POST_OK]
    for key in ("id", "companyId", "title", "status", "inputType", "requirements"):
        assert key in ok
    assert ok["companyId"] == COMPANY
    assert ok["location"]["id"] == LOC_A
    assert ok["salaryMin"] == 600.0
    assert ok["salaryMax"] == 700.5
    assert ok["schedule"] == [{"day": "lun", "start": "08:00", "end": "16:00"}]
    reqs = {r["skill"]["id"]: r for r in ok["requirements"]}
    assert reqs[SK_CAJA]["weight"] == 3
    assert reqs[SK_CAJA]["required"] is True
    assert reqs[SK_CAJA]["skill"]["labelEs"] == "Manejo de caja"
    assert ok["auditFindings"] == []


def test_blocked_posting_exposes_audit_and_normalizes_schedule(client):
    blocked = _by_id(client.get("/api/v1/postings").json())[POST_BLOCKED]
    assert blocked["schedule"] == [{"day": "sab", "start": "09:00", "end": "13:00"}]
    [finding] = blocked["auditFindings"]
    assert finding["kind"] == "discriminacion"
    assert finding["passed"] is False
    assert finding["findings"] == ["Pide «solo mujeres»"]


def test_filter_by_status_and_company(client):
    published = client.get("/api/v1/postings", params={"status": "publicada"}).json()
    assert [p["id"] for p in published] == [POST_OK]
    by_company = client.get("/api/v1/postings", params={"companyId": COMPANY}).json()
    assert len(by_company) == 2
    assert client.get("/api/v1/postings", params={"companyId": "otra"}).json() == []


def test_invalid_status_is_problem_json(client):
    res = client.get("/api/v1/postings", params={"status": "inventado"})
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["status"] == 422


def test_get_posting_and_404(client):
    assert client.get(f"/api/v1/postings/{POST_OK}").json()["title"] == "Cajero/a"
    res = client.get("/api/v1/postings/no-existe")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/problem+json")
