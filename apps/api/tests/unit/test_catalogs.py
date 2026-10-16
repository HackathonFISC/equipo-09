from tests.unit.conftest import LOC_A, SK_ATENCION, SK_CAJA, SK_EXCEL


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_list_locations_camel_and_ordered(client):
    res = client.get("/api/v1/locations")
    assert res.status_code == 200
    body = res.json()
    assert [loc["corregimiento"] for loc in body] == ["Bella Vista", "Belisario Porras"]
    assert body[0] == {
        "id": LOC_A,
        "corregimiento": "Bella Vista",
        "distrito": "Panamá",
        "provincia": "Panamá",
        "lat": 8.98,
        "lng": -79.52,
    }
    # Opcionales sin valor se omiten: el contrato (OpenAPI 3.1) no admite null.
    assert "lat" not in body[1]


def test_list_skills(client):
    body = client.get("/api/v1/skills").json()
    assert {s["id"] for s in body} == {SK_CAJA, SK_ATENCION, SK_EXCEL}
    caja = next(s for s in body if s["id"] == SK_CAJA)
    assert caja["labelEs"] == "Manejo de caja"
    assert caja["escoUri"].startswith("http://data.europa.eu/esco/")


def test_search_skills_ignores_accents_and_uses_aliases(client):
    def ids(q):
        return [s["id"] for s in client.get("/api/v1/skills", params={"q": q}).json()]

    assert ids("ATENCION") == [SK_ATENCION]
    assert ids("excel") == [SK_EXCEL]
    assert ids("soldadura") == []
