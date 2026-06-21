"""WebSocket连接测试 - v1.30 适配新的 message-based 认证流

v1.30 变更:
- 旧实现: token 通过 URL 参数 `?token=xxx` 传递
- 新实现: 升级为更安全的 message-based 认证
  1. 客户端打开 WebSocket 连接 (无 query param)
  2. 服务端拒绝 URL 中的 token (code 4001)
  3. 客户端发送 `{"type": "auth", "token": "<access>"}`
  4. 服务端校验通过后, 客户端可发送 ping/pong

注: Starlette TestClient 中, ws.receive() 收到 close 消息时返回 dict,
    而 ws.receive_json() 在收到 close 消息时抛 WebSocketDisconnect。
    本文件统一用 pytest.raises(WebSocketDisconnect) 验证关闭。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token, create_refresh_token


def _auth_message(token: str) -> str:
    return '{"type":"auth","token":"%s"}' % token


def _ping_message() -> str:
    return '{"type":"ping"}'


class TestWebSocketConnection:
    """WebSocket连接测试 (v1.30 message-based auth)"""

    def test_ws_accepts_access_token(self, client: TestClient, seeded_user_id: int):
        """测试有效 access_token 可建立连接并 ping/pong"""
        token = create_access_token({"sub": str(seeded_user_id), "role": "user"})

        with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
            ws.send_text(_auth_message(token))
            ws.send_text(_ping_message())
            payload = ws.receive_json()
            assert payload["type"] == "pong"

    def test_ws_rejects_refresh_token(self, client: TestClient, seeded_user_id: int):
        """测试 refresh_token 被拒绝 (类型不匹配)"""
        token = create_refresh_token({"sub": str(seeded_user_id), "role": "user"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
                ws.send_text(_auth_message(token))
                ws.receive_json()
        assert exc_info.value.code == 4001
        assert "Token类型" in exc_info.value.reason

    def test_ws_rejects_invalid_token(self, client: TestClient, seeded_user_id: int):
        """测试无效 token 被拒绝"""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
                ws.send_text(_auth_message("garbage_token_xxx"))
                ws.receive_json()
        assert exc_info.value.code == 4001

    def test_ws_rejects_user_id_mismatch(self, client: TestClient, seeded_user_id: int):
        """测试 user_id 不匹配被拒绝"""
        token = create_access_token({"sub": "9999", "role": "user"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
                ws.send_text(_auth_message(token))
                ws.receive_json()
        assert exc_info.value.code == 4001
        assert "用户ID不匹配" in exc_info.value.reason

    def test_ws_rejects_missing_auth(self, client: TestClient, seeded_user_id: int):
        """测试未发送 auth 直接 ping 被拒绝"""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
                ws.send_text(_ping_message())
                ws.receive_json()
        assert exc_info.value.code == 4001
        assert "缺少认证Token" in exc_info.value.reason

    def test_ws_rejects_token_in_url(self, client: TestClient, seeded_user_id: int):
        """测试 URL 参数中的 token 被拒绝 (安全要求)"""
        token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}?token={token}") as ws:
                ws.receive_json()
        assert exc_info.value.code == 4001
        assert "URL参数" in exc_info.value.reason

    def test_ws_rejects_wrong_message_type(self, client: TestClient, seeded_user_id: int):
        """测试错误的消息类型被拒绝"""
        token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
                ws.send_text('{"type":"login","token":"%s"}' % token)
                ws.receive_json()
        assert exc_info.value.code == 4001
        assert "缺少认证Token" in exc_info.value.reason

    def test_ws_rejects_malformed_json(self, client: TestClient, seeded_user_id: int):
        """测试非法 JSON: 服务端解析失败后关闭连接"""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
                ws.send_text("not json")
                ws.receive_json()
        assert exc_info.value.code == 4001
        assert "缺少认证Token" in exc_info.value.reason


class TestWebSocketBearerNormalization:
    """验证 bearer 前缀和空白在 auth 消息中可被容忍"""

    def test_ws_accepts_bearer_prefix(self, client: TestClient, seeded_user_id: int):
        token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
        with client.websocket_connect(f"/ws/{seeded_user_id}") as ws:
            ws.send_text('{"type":"auth","token":"Bearer %s"}' % token)
            ws.send_text(_ping_message())
            payload = ws.receive_json()
            assert payload["type"] == "pong"
