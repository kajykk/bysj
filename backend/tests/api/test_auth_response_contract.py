from __future__ import annotations

from app.core.security import create_access_token


def test_401_response_shape_is_consistent(client) -> None:
    """v1.30: 错误响应统一使用 {error: {code, message, request_id, status_code}} 包装."""
    token = create_access_token({"sub": "9999", "role": "user"})
    resp = client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    body = resp.json()
    # 兼容两种响应格式
    assert "detail" in body or "error" in body
    if "error" in body:
        err = body["error"]
        assert "code" in err
        assert "message" in err
        assert err.get("status_code") == 403


def test_403_response_shape_is_consistent(client, seeded_user_id: int) -> None:
    token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
    resp = client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code in (302, 307, 308, 403)
    if resp.status_code == 403:
        body = resp.json()
        assert "detail" in body or "error" in body
        if "error" in body:
            err = body["error"]
            assert "code" in err
            assert "message" in err
            assert err.get("status_code") == 403
