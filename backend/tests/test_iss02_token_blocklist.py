"""ISS-02 覆盖率提升：app/core/token_blocklist.py 聚焦测试.

依赖 cache_get/cache_set（Redis + LRU 回退），通过 monkeypatch 隔离，无需真实 Redis。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core import token_blocklist as tb


@pytest.fixture
def mock_cache(monkeypatch):
    store = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ttl=None):
        store[key] = value
        return True

    monkeypatch.setattr(tb, "cache_get", fake_get)
    monkeypatch.setattr(tb, "cache_set", fake_set)
    return store


class TestRevokeAndCheck:
    async def test_revoke_then_revoked(self, mock_cache):
        assert await tb.is_token_revoked("jti-1") is False
        ok = await tb.revoke_token("jti-1", ttl=3600)
        assert ok is True
        assert await tb.is_token_revoked("jti-1") is True

    async def test_revoke_empty_jti_returns_false(self, mock_cache):
        assert await tb.revoke_token("", ttl=3600) is False

    async def test_revoke_invalid_ttl_returns_false(self, mock_cache):
        assert await tb.revoke_token("jti-2", ttl=0) is False
        assert await tb.revoke_token("jti-2", ttl=-5) is False

    async def test_is_revoked_empty_jti_false(self, mock_cache):
        # 空 jti 不应查缓存，直接返回 False
        assert await tb.is_token_revoked("") is False

    async def test_key_format(self, mock_cache):
        await tb.revoke_token("abc", ttl=10)
        assert "token_blocklist:abc" in mock_cache
