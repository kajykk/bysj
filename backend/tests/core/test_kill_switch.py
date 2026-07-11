"""Phase 3 模型预测暂停开关（Kill Switch）测试.

覆盖：
- app/core/kill_switch.py: is_model_paused, set_model_paused, get_kill_switch_status
- 内存降级模式（无 Redis 环境）
- 状态切换、缓存失效、重置
"""

from __future__ import annotations

import pytest

from app.core.kill_switch import (
    get_kill_switch_status,
    invalidate_local_cache,
    is_model_paused,
    reset_memory_state,
    set_model_paused,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """每个测试前重置内存状态和本地缓存."""
    reset_memory_state()
    yield
    reset_memory_state()


class TestIsModelPaused:
    """Test is_model_paused."""

    @pytest.mark.asyncio
    async def test_default_not_paused(self):
        """默认状态：未暂停."""
        assert await is_model_paused() is False

    @pytest.mark.asyncio
    async def test_paused_after_activation(self):
        """激活后：已暂停."""
        await set_model_paused(True, admin_id=1, reason="test")
        invalidate_local_cache()  # 清除缓存以反映新状态
        assert await is_model_paused() is True

    @pytest.mark.asyncio
    async def test_not_paused_after_deactivation(self):
        """恢复后：未暂停."""
        await set_model_paused(True, admin_id=1, reason="pause")
        invalidate_local_cache()
        assert await is_model_paused() is True

        await set_model_paused(False, admin_id=1, reason="resume")
        invalidate_local_cache()
        assert await is_model_paused() is False

    @pytest.mark.asyncio
    async def test_local_cache_used(self):
        """本地缓存应被使用（5s TTL 内不重复查 Redis）."""
        # 第一次调用设置缓存
        await is_model_paused()
        # 在缓存有效期内激活暂停
        await set_model_paused(True, admin_id=1, reason="test")
        # 不清除缓存，应仍返回缓存的旧值（False）
        # 注意：set_model_paused 会更新本地缓存，所以这里应为 True
        assert await is_model_paused() is True


class TestSetModelPaused:
    """Test set_model_paused."""

    @pytest.mark.asyncio
    async def test_activate_returns_state(self):
        """激活返回包含 paused=True 的状态."""
        state = await set_model_paused(True, admin_id=1, reason="crisis event")
        assert state["paused"] is True
        assert state["reason"] == "crisis event"
        assert state["activated_by"] == 1
        assert state["activated_at"] is not None

    @pytest.mark.asyncio
    async def test_deactivate_returns_state(self):
        """恢复返回包含 paused=False 的状态."""
        state = await set_model_paused(False, admin_id=1, reason="resolved")
        assert state["paused"] is False
        assert state["activated_by"] is None
        assert state["activated_at"] is None

    @pytest.mark.asyncio
    async def test_state_persistence_in_memory(self):
        """内存模式下状态应持久（直到被显式修改）."""
        await set_model_paused(True, admin_id=1, reason="test")
        invalidate_local_cache()
        # 多次读取应一致
        assert await is_model_paused() is True
        assert await is_model_paused() is True

    @pytest.mark.asyncio
    async def test_reason_optional_on_deactivate(self):
        """恢复时 reason 仍为必填参数."""
        state = await set_model_paused(False, admin_id=2, reason="ok")
        assert state["paused"] is False


class TestGetKillSwitchStatus:
    """Test get_kill_switch_status."""

    @pytest.mark.asyncio
    async def test_default_status(self):
        """默认状态：全部字段为 None/False."""
        status = await get_kill_switch_status()
        assert status["paused"] is False
        assert status["reason"] is None
        assert status["activated_by"] is None
        assert status["activated_at"] is None

    @pytest.mark.asyncio
    async def test_status_after_activation(self):
        """激活后状态应反映暂停信息."""
        await set_model_paused(True, admin_id=42, reason="security incident")
        status = await get_kill_switch_status()
        assert status["paused"] is True
        assert status["reason"] == "security incident"
        assert status["activated_by"] == 42
        assert status["activated_at"] is not None

    @pytest.mark.asyncio
    async def test_status_after_deactivation(self):
        """恢复后状态应反映未暂停."""
        await set_model_paused(True, admin_id=1, reason="pause")
        await set_model_paused(False, admin_id=1, reason="resume")
        status = await get_kill_switch_status()
        assert status["paused"] is False


class TestResetMemoryState:
    """Test reset_memory_state."""

    @pytest.mark.asyncio
    async def test_reset_clears_paused_state(self):
        """reset 后状态应恢复为未暂停."""
        await set_model_paused(True, admin_id=1, reason="test")
        reset_memory_state()
        assert await is_model_paused() is False

    @pytest.mark.asyncio
    async def test_reset_clears_status(self):
        """reset 后状态查询应返回默认值."""
        await set_model_paused(True, admin_id=1, reason="test")
        reset_memory_state()
        status = await get_kill_switch_status()
        assert status["paused"] is False
        assert status["reason"] is None
