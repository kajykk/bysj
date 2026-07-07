from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token, create_refresh_token


def test_admin_dashboard_rejects_user_role(
    client: TestClient, seeded_user_id: int
) -> None:
    token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
    resp = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307, 308, 403)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/templates",
        "/api/v1/admin/thresholds",
        "/api/v1/admin/configs",
        "/api/v1/admin/operation-logs",
    ],
)
def test_admin_routes_reject_counselor_role(
    client: TestClient, as_role, path: str
) -> None:
    as_role("counselor", 2)
    resp = client.get(path)
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/counselor/warnings",
        "/api/v1/counselor/users",
        "/api/v1/counselor/groups",
        "/api/v1/counselor/bind-code",
    ],
)
def test_counselor_routes_reject_user_role(
    client: TestClient, as_role, path: str
) -> None:
    as_role("user", 1)
    resp = client.get(path)
    assert resp.status_code == 403


def test_upload_requires_upload_permission(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    resp = client.post(
        "/api/v1/user/upload",
        files={"file": ("test.jpg", b"\xff\xd8\xff\xe0" + b"x" * 32, "image/jpeg")},
    )
    assert resp.status_code in (403, 422)


def test_risk_export_requires_export_permission(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    resp = client.get("/api/v1/user/risk/export?format=pdf&days=30")
    assert resp.status_code == 403


def test_model_predict_requires_prediction_permission(
    client: TestClient, as_role
) -> None:
    as_role("counselor", 2)
    resp = client.post("/api/v1/model/predict/text", json={"text": "最近有点难过"})
    assert resp.status_code == 403


def test_ws_rejects_refresh_token(client: TestClient, seeded_user_id: int) -> None:
    token = create_refresh_token({"sub": str(seeded_user_id), "role": "user"})
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
            ws.send_text('{"type":"auth","token":"%s"}' % token)
            ws.receive_json()
    assert exc_info.value.code == 4001


def test_ws_rejects_missing_token(client: TestClient, seeded_user_id: int) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
            ws.send_text('{"type":"ping"}')
            ws.receive_json()
    assert exc_info.value.code == 4001


def test_user_role_rejects_admin_settings(client: TestClient, as_role) -> None:
    as_role("user", 1)
    resp = client.get("/api/v1/admin/settings")
    assert resp.status_code == 403


def test_unknown_resource_returns_404(client: TestClient) -> None:
    resp = client.get("/api/v1/user/intervention/tasks/999999")
    assert resp.status_code in (404, 422)


class TestAdminAccessAllResources:
    def test_admin_access_user_routes(self, client: TestClient, as_role) -> None:
        as_role("admin", 3)
        resp = client.get("/api/v1/user/warnings")
        assert resp.status_code == 200

    def test_admin_access_counselor_routes(self, client: TestClient, as_role) -> None:
        as_role("admin", 3)
        resp = client.get("/api/v1/counselor/warnings")
        assert resp.status_code == 200

    def test_admin_access_admin_routes(self, client: TestClient, as_role) -> None:
        as_role("admin", 3)
        resp = client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 200
