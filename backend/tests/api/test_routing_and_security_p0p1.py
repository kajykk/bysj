from __future__ import annotations

from app.core.security import create_access_token


def test_forbidden_redirect_for_wrong_role(client, seeded_user_id: int) -> None:
    token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
    resp = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307, 308, 403)


def test_health_endpoint_returns_status(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body["checks"]
