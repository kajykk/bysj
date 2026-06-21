"""WebSocket helper 函数单元测试 (v1.30)"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.core.ws import _normalize_websocket_token, _receive_auth_token


class TestNormalizeWebsocketToken:
    """_normalize_websocket_token 行为测试"""

    def test_none_returns_empty(self):
        assert _normalize_websocket_token(None) == ""

    def test_empty_string_returns_empty(self):
        assert _normalize_websocket_token("") == ""

    def test_plain_token(self):
        assert _normalize_websocket_token("abc.def.ghi") == "abc.def.ghi"

    def test_bearer_prefix_lowercase(self):
        assert _normalize_websocket_token("bearer abc") == "abc"

    def test_bearer_prefix_uppercase(self):
        assert _normalize_websocket_token("Bearer abc") == "abc"

    def test_bearer_prefix_mixed(self):
        assert _normalize_websocket_token("BeArEr abc") == "abc"

    def test_extra_whitespace_stripped(self):
        assert _normalize_websocket_token("   abc   ") == "abc"

    def test_bearer_with_whitespace(self):
        # "  bearer   abc  " -> 因为有前导空格, .lower().startswith("bearer ") 为 False
        # 仅 strip 外部空白, 保留内部: "bearer   abc"
        assert _normalize_websocket_token("  bearer   abc  ") == "bearer   abc"


class TestReceiveAuthToken:
    """_receive_auth_token 行为测试"""

    @pytest.mark.asyncio
    async def test_valid_auth_message(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth", "token": "abc.def.ghi"}))
        result = await _receive_auth_token(ws)
        assert result == "abc.def.ghi"

    @pytest.mark.asyncio
    async def test_wrong_type_returns_empty(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "login", "token": "abc"}))
        result = await _receive_auth_token(ws)
        assert result == ""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(return_value="not json {{")
        result = await _receive_auth_token(ws)
        assert result == ""

    @pytest.mark.asyncio
    async def test_missing_token_returns_empty(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth"}))
        result = await _receive_auth_token(ws)
        assert result == ""

    @pytest.mark.asyncio
    async def test_token_with_bearer_prefix(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock(return_value=json.dumps({"type": "auth", "token": "Bearer xyz"}))
        result = await _receive_auth_token(ws)
        assert result == "xyz"
