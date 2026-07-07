from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token, create_refresh_token


def test_websocket_accepts_access_token_and_pongs(
    client: TestClient, seeded_user_id: int
) -> None:
    """v1.30: message-based auth 流程."""
    token = create_access_token({"sub": str(seeded_user_id), "role": "user"})

    with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
        ws.send_text('{"type":"auth","token":"%s"}' % token)
        ws.send_text('{"type":"ping"}')
        payload = ws.receive_json()
        assert payload["type"] == "pong"


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda user_id: create_refresh_token({"sub": str(user_id), "role": "user"}),
        lambda user_id: create_access_token({"sub": str(user_id + 1), "role": "user"}),
    ],
)
def test_websocket_rejects_invalid_auth(
    token_factory, client: TestClient, seeded_user_id: int
) -> None:
    """v1.30: 错误类型 token 或 user_id 不匹配时拒绝."""
    token = token_factory(seeded_user_id)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
            ws.send_text('{"type":"auth","token":"%s"}' % token)
            ws.receive_json()
    assert exc_info.value.code == 4001


def test_websocket_rejects_missing_token(
    client: TestClient, seeded_user_id: int
) -> None:
    """v1.30: 缺少 auth 消息直接 ping 应被拒绝."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
            ws.send_text('{"type":"ping"}')
            ws.receive_json()
    assert exc_info.value.code == 4001
    assert "缺少认证Token" in exc_info.value.reason


def test_websocket_rejects_token_in_url(
    client: TestClient, seeded_user_id: int
) -> None:
    """v1.30: URL 中的 token 仍被拒绝 (安全要求)."""
    token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/{seeded_user_id}?token={token}") as ws:
            ws.receive_json()
    assert exc_info.value.code == 4001
    assert "URL参数" in exc_info.value.reason
