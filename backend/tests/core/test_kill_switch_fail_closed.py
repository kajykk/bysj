"""AUDIT-2026-10-01 (P1-7)：Kill Switch 故障降级模式（fail-closed / fail-open）回归测试。

背景（原缺陷）：
    Redis 不可用时，``is_model_paused()`` 回退到进程内 ``_memory_state``（默认
    ``paused=False``）→ **放行**；``set_model_paused()`` 写 Redis 失败时静默写内存并
    **返回成功**。多实例部署下这两条合起来意味着：运维在 A 实例按下暂停，B/C 实例照常
    预测，而操作界面显示「已暂停」。

本文件钉住修复后的契约：
    - fail-closed：无法确认权威状态 → 视为已暂停；无法写入 → 抛错（不返回假成功）
    - fail-open：沿用内存状态，但**必须**如实标记 degraded（区分「确认未暂停」与「不知道」）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.core import kill_switch as ks
from app.core.config import Settings
from app.core.kill_switch import KillSwitchUnavailableError


@pytest.fixture(autouse=True)
def reset_state():
    ks.reset_memory_state()
    ks.invalidate_local_cache()
    yield
    ks.reset_memory_state()
    ks.invalidate_local_cache()


def _force(monkeypatch, fail_closed: bool) -> None:
    """强制 kill_switch 模块的降级判定（绕过 config 层）。"""
    monkeypatch.setattr(ks, "_fail_closed", lambda: fail_closed)


def _broken_redis(monkeypatch, *, read: bool | None = None, write: bool = False) -> None:
    """装配一个「不可用」的 Redis。

    read=False → get 抛异常；read=True → 返回 None（无记录）；read=None → 客户端为 None
    write=True → set 抛异常
    """
    if read is None:
        monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=None))
        return

    fake = MagicMock()
    if read:
        fake.get = AsyncMock(return_value=None)
    else:
        fake.get = AsyncMock(side_effect=RuntimeError("redis read down"))
    if write:
        fake.set = AsyncMock(side_effect=RuntimeError("redis write down"))
    else:
        fake.set = AsyncMock()
    monkeypatch.setattr(ks, "_get_redis", AsyncMock(return_value=fake))


# --------------------------------------------------------------------------- #
# A. 配置层：kill_switch_fail_closed 的判定
# --------------------------------------------------------------------------- #
class TestFailModeResolution:
    """配置 → 判定的映射（唯一入口，避免各处重复判断而漂移）。"""

    def test_explicit_closed(self):
        s = Settings.model_construct(kill_switch_fail_mode="closed", app_env="test")
        assert s.kill_switch_fail_closed is True

    def test_explicit_open(self):
        s = Settings.model_construct(kill_switch_fail_mode="open", app_env="production")
        assert s.kill_switch_fail_closed is False

    def test_auto_production_is_closed(self):
        """留空 + production → closed（生产无需额外配置即获得最严行为）。"""
        s = Settings.model_construct(kill_switch_fail_mode="", app_env="production")
        assert s.kill_switch_fail_closed is True

    def test_auto_non_production_is_open(self):
        """留空 + development/test → open（不被无 Redis 的常态打成 503）。"""
        s = Settings.model_construct(kill_switch_fail_mode="", app_env="development")
        assert s.kill_switch_fail_closed is False

    def test_invalid_mode_rejected(self):
        """笔误必须启动即报错，而不是静默走另一条分支。"""
        with pytest.raises(ValidationError, match="KILL_SWITCH_FAIL_MODE"):
            Settings(kill_switch_fail_mode="closure")


# --------------------------------------------------------------------------- #
# B. fail-closed：读不到权威状态 → 视为已暂停
# --------------------------------------------------------------------------- #
class TestFailClosedRead:
    @pytest.mark.parametrize(
        "read",
        [None, False],
        ids=["redis_client_none", "redis_get_raises"],
    )
    async def test_is_model_paused_true_when_unavailable(self, monkeypatch, read):
        """Redis 不可用 → True（阻止预测），无论内存状态是什么。"""
        _force(monkeypatch, True)
        _broken_redis(monkeypatch, read=read)
        assert await ks.is_model_paused() is True

    async def test_status_marks_unavailable(self, monkeypatch):
        """状态接口必须暴露「不知道」，而不是伪装成「未暂停」。"""
        _force(monkeypatch, True)
        _broken_redis(monkeypatch, read=None)
        status = await ks.get_kill_switch_status()
        assert status["paused"] is True
        assert status["degraded"] is True
        assert status["source"] == "unavailable"

    async def test_healthy_status_is_not_degraded(self, monkeypatch):
        """对照：Redis 正常时 degraded 必须为 False（不能一律标降级）。"""
        _force(monkeypatch, True)
        _broken_redis(monkeypatch, read=True)  # get 正常返回 None（无记录）
        status = await ks.get_kill_switch_status()
        assert status["paused"] is False
        assert status["degraded"] is False
        assert status["source"] == "redis"


# --------------------------------------------------------------------------- #
# C. fail-closed：写不进权威状态 → 抛错，且不产生半生效
# --------------------------------------------------------------------------- #
class TestFailClosedWrite:
    @pytest.mark.parametrize(
        "read",
        [None, False],
        ids=["redis_client_none", "redis_set_raises"],
    )
    async def test_set_raises_instead_of_fake_success(self, monkeypatch, read):
        """绝不返回「设置成功」——多实例下其他实例不会生效。"""
        _force(monkeypatch, True)
        _broken_redis(monkeypatch, read=read, write=True)
        with pytest.raises(KillSwitchUnavailableError):
            await ks.set_model_paused(True, admin_id=1, reason="crisis")

    async def test_no_partial_memory_effect(self, monkeypatch):
        """抛错后内存状态不得被改动（不能有「本实例暂停了」的半生效）。"""
        _force(monkeypatch, True)
        _broken_redis(monkeypatch, read=None, write=True)
        before = dict(ks._memory_state)
        with pytest.raises(KillSwitchUnavailableError):
            await ks.set_model_paused(True, admin_id=1, reason="crisis")
        assert ks._memory_state == before

    async def test_deactivate_also_refuses(self, monkeypatch):
        """恢复操作同样不能声称成功——否则界面显示已恢复、其他实例仍在 503。"""
        _force(monkeypatch, True)
        _broken_redis(monkeypatch, read=None, write=True)
        with pytest.raises(KillSwitchUnavailableError):
            await ks.set_model_paused(False, admin_id=1, reason="resolved")


# --------------------------------------------------------------------------- #
# D. fail-open：保持可用，但必须如实标记 degraded
# --------------------------------------------------------------------------- #
class TestFailOpenPreservesAvailability:
    async def test_is_model_paused_follows_memory(self, monkeypatch):
        _force(monkeypatch, False)
        _broken_redis(monkeypatch, read=None)
        assert await ks.is_model_paused() is False
        await ks.set_model_paused(True, admin_id=1, reason="x")
        ks.invalidate_local_cache()
        assert await ks.is_model_paused() is True

    async def test_status_marks_memory_degradation(self, monkeypatch):
        """即使放行，也必须让调用方知道这不是权威状态。"""
        _force(monkeypatch, False)
        _broken_redis(monkeypatch, read=None)
        await ks.set_model_paused(True, admin_id=2, reason="security")
        status = await ks.get_kill_switch_status()
        assert status["paused"] is True
        assert status["degraded"] is True
        assert status["source"] == "memory"

    async def test_set_returns_degraded_flag(self, monkeypatch):
        _force(monkeypatch, False)
        _broken_redis(monkeypatch, read=None, write=True)
        state = await ks.set_model_paused(True, admin_id=3, reason="drill")
        assert state["paused"] is True
        assert state["degraded"] is True
        assert state["source"] == "memory"


# --------------------------------------------------------------------------- #
# E. 元测试：证明新行为确实来自 fail-closed 判定，而非别的原因
# --------------------------------------------------------------------------- #
class TestGuardIsTheCause:
    async def test_same_setup_differs_only_by_fail_mode(self, monkeypatch):
        """同一环境、同一故障，仅切换降级模式 → 结果必须相反。

        这条不是「测试通过」，而是证明 B/C 两组的断言确实由该判定产生：
        若把判定关掉（= 改前行为），同样的 Redis 故障会放行并返回假成功。
        """
        _broken_redis(monkeypatch, read=None, write=True)

        _force(monkeypatch, True)
        assert await ks.is_model_paused() is True
        with pytest.raises(KillSwitchUnavailableError):
            await ks.set_model_paused(True, admin_id=1, reason="r")

        ks.reset_memory_state()

        _force(monkeypatch, False)
        assert await ks.is_model_paused() is False
        state = await ks.set_model_paused(True, admin_id=1, reason="r")
        assert state["paused"] is True  # 改前行为：静默落内存并「成功」
