"""ISS-02 覆盖率提升：app/core/kill_switch.py 聚焦测试.

模型预测暂停开关（安全/危机熔断）。mock `_get_redis` 覆盖 Redis 路径与内存降级路径。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import kill_switch as ks


@pytest.fixture(autouse=True)
def reset_state():
    ks.reset_memory_state()
    ks.invalidate_local_cache()
    yield
    ks.reset_memory_state()
    ks.invalidate_local_cache()


class TestMemoryDegradation:
    async def test_paused_false_when_redis_none(self, monkeypatch):
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=None))
        assert await ks.is_model_paused() is False

    async def test_set_paused_memory_mode(self, monkeypatch):
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=None))
        state = await ks.set_model_paused(True, admin_id=1, reason="incident")
        assert state["paused"] is True
        assert state["activated_by"] == 1
        assert await ks.is_model_paused() is True

    async def test_deactivate_memory_mode(self, monkeypatch):
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=None))
        await ks.set_model_paused(True, admin_id=1, reason="x")
        state = await ks.set_model_paused(False, admin_id=1)
        assert state["paused"] is False
        assert state["activated_by"] is None
        assert await ks.is_model_paused() is False

    async def test_get_status_memory_mode(self, monkeypatch):
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=None))
        await ks.set_model_paused(True, admin_id=2, reason="security")
        status = await ks.get_kill_switch_status()
        assert status["paused"] is True
        assert status["reason"] == "security"


class TestRedisPath:
    async def test_is_paused_reads_redis(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.get = AsyncMock(return_value=None)
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=fake_redis))
        assert await ks.is_model_paused() is False

    async def test_set_paused_writes_redis(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.set = AsyncMock()
        fake_redis.get = AsyncMock(return_value=None)
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=fake_redis))

        state = await ks.set_model_paused(True, admin_id=9, reason="drill")
        fake_redis.set.assert_awaited_once()
        assert state["paused"] is True

    async def test_is_paused_parses_redis_state(self, monkeypatch):
        import json

        fake_redis = MagicMock()
        fake_redis.get = AsyncMock(
            return_value=json.dumps({"paused": True, "reason": "x"})
        )
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=fake_redis))
        assert await ks.is_model_paused() is True

    async def test_redis_read_failure_falls_back_memory(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.get = AsyncMock(side_effect=RuntimeError("redis down"))
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=fake_redis))
        # 降级到内存（默认未暂停）
        assert await ks.is_model_paused() is False

    async def test_redis_write_failure_falls_back_memory(self, monkeypatch):
        fake_redis = MagicMock()
        fake_redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
        fake_redis.get = AsyncMock(return_value=None)
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=fake_redis))
        state = await ks.set_model_paused(True, admin_id=3)
        assert state["paused"] is True  # 写入内存成功
        assert await ks.is_model_paused() is True


def test_invalidate_and_reset_helpers():
    ks.reset_memory_state()
    ks.invalidate_local_cache()
    # 仅验证不抛错（函数体内已重置全局）
    assert ks._local_cache is None
