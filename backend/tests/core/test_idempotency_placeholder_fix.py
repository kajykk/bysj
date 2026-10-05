"""SEC-FIX-2026-10-05: 幂等占位值缺陷回归测试.

缺陷背景:
    core/idempotency.py 原实现用字符串 "1" 作为「正在处理中」的占位值,
    并靠 `except (TypeError, ValueError)` 捕获 json.loads 失败来识别它。
    但 json.loads("1") **合法返回整数 1 且不抛异常** —— docstring 里
    「占位值非 JSON」的假设与实际写入的值自相矛盾。

    后果: 重复提交时 begin_idempotent_call 返回 (False, 1),
    调用方 admin.py:75 `if replay is not None` 判定为「已完成 → 重放首次响应」,
    把整数 1 当成 upsert 结果返回 → 客户端收到 200 {"data": 1},
    data 是整数而非 {"threshold_id": N}, 前端取 id 得 undefined 静默失败。
    admin.py 的模板/阈值/配置三处 upsert 全部中招, 且拿不到应有的 409。

为什么既有测试没抓到:
    test_p3_fixes_20260705.py 只覆盖了「相同 key 完整执行两次后重放」
    与「不同 key 都执行」—— 前者第一个请求已 settle完毕, 读到的是真实响应;
    后者 key 不同。**没有任何测试覆盖「第一个请求仍在处理中」这条路径**,
    而缺陷恰好只存在于这条路径。

本测试覆盖:
    1. 占位值契约本身（非法 JSON + 自解释）
    2. 处理中重复提交 → (False, None) → 上层 409（核心回归）
    3. 已 settle → (False, dict) 正常重放（不回归）
    4. 非 dict 的 JSON 标量（历史残留 / "1" 旧值）不再被重放
    5. 端到端：处理中重复提交返回 409 而非 200 {"data": 1}
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.core import idempotency
from app.core.idempotency import (
    begin_idempotent_call,
    dismiss_idempotent_call,
    make_idempotency_key,
    settle_idempotent_call,
)

# SEC-FIX-2026-10-05: 该常量在修复前的版本中不存在。
# 用 getattr 兜底取旧实现实际写入的占位值（"1"），使本测试文件在旧代码下
# 也能被收集并运行 —— 否则只会看到 ImportError，而看不到真正的断言失败，
# 对照实验就失去意义（收集失败 ≠ 测试对缺陷敏感）。
_PENDING_PLACEHOLDER = getattr(idempotency, "_PENDING_PLACEHOLDER", "1")
_PLACEHOLDER_IS_FIXED = hasattr(idempotency, "_PENDING_PLACEHOLDER")


class _FakeRedis:
    """最小 Redis 替身, 语义与真实 redis-py 的 get/set(nx)/delete 一致."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()

    async def _client():
        return fake

    monkeypatch.setattr("app.core.idempotency.get_redis_client", _client)
    return fake


class TestPlaceholderContract:
    """占位值契约: 必须能区分「处理中」与「已完成」。"""

    def test_placeholder_is_not_valid_json(self) -> None:
        """占位值不能是合法 JSON —— 否则 json.loads 不会失败, 缺陷复现。

        对照实验意义: 旧实现写 "1", json.loads("1") 合法返回 1,
        因此本测试在旧代码下必然 FAIL —— 证明它对缺陷敏感。
        """
        with pytest.raises(ValueError):
            json.loads(_PENDING_PLACEHOLDER)

    def test_placeholder_is_not_numeric_scalar(self) -> None:
        """回归: 旧实现用的是 "1", json.loads("1") == 1 合法。"""
        assert json.loads("1") == 1, "前置确认: 旧占位值确实是合法 JSON"
        assert _PENDING_PLACEHOLDER != "1", (
            "占位值仍是 '1' —— 该缺陷未修复（json.loads 会成功返回整数 1）"
        )

    def test_module_defines_placeholder_constant(self) -> None:
        """占位值必须是模块级常量, 而不是散落的字面量。"""
        assert _PLACEHOLDER_IS_FIXED, (
            "idempotency 模块未定义 _PENDING_PLACEHOLDER —— "
            "占位值仍是内联字面量，无法集中校验与复用"
        )


class TestBeginIdempotentCall:
    """begin_idempotent_call 的三条返回路径。"""

    @pytest.mark.asyncio
    async def test_first_call_proceeds_and_writes_placeholder(
        self, fake_redis: _FakeRedis
    ) -> None:
        key = make_idempotency_key(1, "k-first")
        proceed, replay = await begin_idempotent_call(key)

        assert proceed is True
        assert replay is None
        # 首次调用写入的必须是占位值, 而不是 "1"
        assert fake_redis._store[key] == _PENDING_PLACEHOLDER

    @pytest.mark.asyncio
    async def test_in_progress_duplicate_returns_no_replay(
        self, fake_redis: _FakeRedis
    ) -> None:
        """核心回归: 前一次仍在处理中 → (False, None), 不得返回任何重放数据.

        旧实现此处返回 (False, 1) —— 上层会把它当首次响应重放。
        """
        key = make_idempotency_key(1, "k-pending")
        await begin_idempotent_call(key)  # 第一个请求: 占位

        proceed, replay = await begin_idempotent_call(key)  # 第二个请求: 处理中

        assert proceed is False
        # 关键断言: 必须是 None, 不能是整数 1 或任何非 None 值
        assert replay is None, (
            f"处理中重复提交返回了重放数据 {replay!r} —— "
            "上层会把它当首次响应返回给客户端（缺陷回归）"
        )

    @pytest.mark.asyncio
    async def test_settled_call_replays_dict(self, fake_redis: _FakeRedis) -> None:
        """已完成 → (False, dict), 正常重放, 不回归。"""
        key = make_idempotency_key(1, "k-settled")
        await begin_idempotent_call(key)
        payload = {"threshold_id": 42}
        await settle_idempotent_call(key, payload)

        proceed, replay = await begin_idempotent_call(key)

        assert proceed is False
        assert replay == payload

    @pytest.mark.asyncio
    async def test_legacy_numeric_placeholder_not_replayed(
        self, fake_redis: _FakeRedis
    ) -> None:
        """历史残留的旧占位值 "1" 不得被当作响应重放。

        这是真实场景: 修复上线前写入的键仍是 "1", TTL 内重复提交必须走
        「处理中 → 409」, 而不是把整数 1 返回给客户端。
        """
        key = make_idempotency_key(1, "k-legacy")
        fake_redis._store[key] = "1"  # 模拟修复前的残留值

        proceed, replay = await begin_idempotent_call(key)

        assert proceed is False
        assert replay is None, "旧占位值 '1' 被当成了合法响应重放"

    @pytest.mark.asyncio
    async def test_non_dict_json_not_replayed(self, fake_redis: _FakeRedis) -> None:
        """任何非 dict 的 JSON 标量/数组都不重放（契约是 dict）。"""
        for raw in ("1", "true", '"str"', "[1,2]", "3.14"):
            key = make_idempotency_key(1, f"k-scalar-{raw}")
            fake_redis._store[key] = raw

            proceed, replay = await begin_idempotent_call(key)

            assert proceed is False, raw
            assert replay is None, f"{raw} 不应被重放, 实际 {replay!r}"

    @pytest.mark.asyncio
    async def test_invalid_json_residue_treated_as_in_progress(
        self, fake_redis: _FakeRedis
    ) -> None:
        """非法 JSON 残留值按「处理中」处理, 不把垃圾数据返给调用方。"""
        key = make_idempotency_key(1, "k-garbage")
        fake_redis._store[key] = "{not-json"

        proceed, replay = await begin_idempotent_call(key)

        assert proceed is False
        assert replay is None

    @pytest.mark.asyncio
    async def test_dismiss_allows_retry(self, fake_redis: _FakeRedis) -> None:
        """dismiss 后允许重试 —— 失败请求不应永久卡住幂等键。"""
        key = make_idempotency_key(1, "k-dismiss")
        await begin_idempotent_call(key)
        await dismiss_idempotent_call(key)

        proceed, replay = await begin_idempotent_call(key)

        assert proceed is True
        assert replay is None

    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades_to_proceed(self, monkeypatch) -> None:
        """Redis 不可用时降级放行（既有设计, 不得回归）。

        注: 降级本身是静默的, 属审查报告中的「一般」级问题,
        本次仅保证行为不变 —— 保护失效应有可观测性, 另行处理。
        """
        monkeypatch.setattr(
            "app.core.idempotency.get_redis_client",
            AsyncMock(return_value=None),
        )
        proceed, replay = await begin_idempotent_call(make_idempotency_key(1, "k-nr"))
        assert proceed is True
        assert replay is None

    @pytest.mark.asyncio
    async def test_different_actor_keys_are_isolated(self, fake_redis: _FakeRedis) -> None:
        """不同操作者的同名幂等键互相隔离。"""
        k1 = make_idempotency_key(1, "shared-key")
        k2 = make_idempotency_key(2, "shared-key")
        assert k1 != k2

        assert (await begin_idempotent_call(k1))[0] is True
        assert (await begin_idempotent_call(k2))[0] is True


class TestEndToEndDuplicateDuringProcessing:
    """端到端: 处理中重复提交必须返回 409, 而非 200 + 假数据."""

    @pytest.mark.asyncio
    async def test_api_returns_409_instead_of_fake_payload(
        self, fake_redis: _FakeRedis
    ) -> None:
        """模拟 admin.py:72-79 的调用链: 处理中 → HTTPException 409。

        直接驱动 admin.py 的 _begin_idempotent, 保证修复在真实调用点上生效,
        而不是只在孤立函数里成立。
        """
        from app.api.v1.admin import _begin_idempotent
        from fastapi import HTTPException
        from starlette.requests import Request

        headers = {"Idempotency-Key": "e2e-pending-1"}
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        request = Request({"type": "http", "method": "POST",
                           "path": "/api/v1/admin/thresholds", "headers": raw_headers})

        # 第一个请求占位（不 settle —— 模拟仍在处理中）
        key, _ = await _begin_idempotent(request, actor_id=3)

        # 第二个请求: 必须 409
        with pytest.raises(HTTPException) as exc:
            await _begin_idempotent(request, actor_id=3)

        assert exc.value.status_code == 409, (
            f"处理中重复提交应返回 409, 实际 {exc.value.status_code}"
        )
        assert key is not None

        # 确认 Redis 里存的是占位值而不是 "1"
        assert fake_redis._store[key] == _PENDING_PLACEHOLDER

    @pytest.mark.asyncio
    async def test_replay_returns_real_dict_payload(
        self, fake_redis: _FakeRedis
    ) -> None:
        """已完成时仍重放真实响应（端到端确认不回归）。"""
        from app.api.v1.admin import _begin_idempotent
        from starlette.requests import Request

        headers = {"Idempotency-Key": "e2e-settled-1"}
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        request = Request({"type": "http", "method": "POST",
                           "path": "/api/v1/admin/thresholds", "headers": raw_headers})

        key, _ = await _begin_idempotent(request, actor_id=3)
        await settle_idempotent_call(key, {"threshold_id": 7})

        _, replay = await _begin_idempotent(request, actor_id=3)

        assert replay == {"threshold_id": 7}, f"重放数据异常: {replay!r}"
        assert isinstance(replay, dict)


class TestNoIdempotencyHeader:
    """未带 Idempotency-Key 头时保持原行为（不算入幂等控制）。"""

    @pytest.mark.asyncio
    async def test_missing_header_passes_through(self, fake_redis: _FakeRedis) -> None:
        from app.api.v1.admin import _begin_idempotent
        from starlette.requests import Request

        request = Request({"type": "http", "method": "POST",
                           "path": "/api/v1/admin/thresholds", "headers": []})
        key, replay = await _begin_idempotent(request, actor_id=3)

        assert key is None
        assert replay is None
        assert fake_redis._store == {}
