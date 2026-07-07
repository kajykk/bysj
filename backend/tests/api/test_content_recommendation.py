from fastapi.testclient import TestClient


def test_recommendations_has_explain(
    client: TestClient, as_role, seed_risk_and_content: None
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/user/content/recommendations?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "explain" in data
    assert "strategy" in data["explain"]
    assert "items" in data
    if data["items"]:
        assert "recommend_reason" in data["items"][0]
