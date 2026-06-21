from __future__ import annotations

import pytest

from app.core import ws as ws_module


class FakeWebSocket:
    def __init__(self, messages: list[str] | None = None, query_params: dict[str, str] | None = None):
        self.messages = list(messages or [])
        self.query_params = query_params or {}
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = (code, reason)

    async def receive_text(self):
        if not self.messages:
            from fastapi import WebSocketDisconnect

            raise WebSocketDisconnect()
        return self.messages.pop(0)

    async def send_text(self, payload: str):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_websocket_rejects_token_in_query_params():
    ws = FakeWebSocket(query_params={"token": "secret"})

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4001, "Token禁止通过URL参数传递")


@pytest.mark.asyncio
async def test_websocket_requires_first_auth_message():
    ws = FakeWebSocket(messages=['{"type":"ping"}'])

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4001, "缺少认证Token")


@pytest.mark.asyncio
async def test_websocket_accepts_token_from_first_auth_message(monkeypatch):
    ws = FakeWebSocket(messages=['{"type":"auth","token":"Bearer access-token"}'])

    monkeypatch.setattr(ws_module, "decode_token", lambda token: {"type": "access", "sub": "1"})

    class _Result:
        def scalar_one_or_none(self):
            return type("User", (), {"status": "active"})()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, _stmt):
            return _Result()

    monkeypatch.setattr(ws_module, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(ws_module.ws_manager, "connect", lambda user_id, websocket: True)
    monkeypatch.setattr(ws_module.ws_manager, "disconnect", lambda user_id, websocket: None)

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed is None
