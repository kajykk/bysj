from fastapi.testclient import TestClient


def test_risk_export_csv(
    client: TestClient, as_role, seed_risk_and_content: None
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/user/risk/export?format=csv&days=90")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")
    body = res.text
    assert "risk_score" in body
    assert "risk_level" in body


def test_risk_report_structure(
    client: TestClient, as_role, seed_risk_and_content: None
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/user/risk/report")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "risk_level" in data
    assert "risk_score" in data
    assert "main_factors" in data
