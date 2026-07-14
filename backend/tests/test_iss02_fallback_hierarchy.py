"""ISS-02 覆盖率提升：app/core/fallback_hierarchy.py 聚焦测试.

通过依赖注入注册假层，纯测 4 层回退逻辑（同步/异步、成功/失败/全失败）。
"""

from __future__ import annotations

import pytest

from app.core.fallback_hierarchy import (
    FallbackExhaustedError,
    FallbackHierarchy,
    FallbackLog,
    FallbackResult,
)


def _sync_ok(value):
    return value


def _sync_fail(exc=RuntimeError("boom")):
    raise exc


async def _async_ok(value):
    return value


class TestFallbackResultAndLog:
    def test_log_add_attempt_updates_final(self):
        log = FallbackLog(request_id="r1")
        assert log.final_layer is None
        log.add_attempt(FallbackResult(success=True, layer="L1", layer_desc="主"))
        assert log.final_layer == "L1"
        assert log.final_result is None
        d = log.to_dict()
        assert d["request_id"] == "r1"
        assert d["final_layer"] == "L1"
        assert len(d["layers_attempted"]) == 1

    def test_log_to_dict_with_failed_attempt(self):
        log = FallbackLog(request_id="r2")
        log.add_attempt(
            FallbackResult(success=False, layer="L1", layer_desc="主", error="e")
        )
        d = log.to_dict()
        assert d["final_layer"] is None
        assert d["layers_attempted"][0]["error"] == "e"


class TestPredictWithFallback:
    def test_first_layer_succeeds(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _sync_ok("ok"))
        result, log = h.predict_with_fallback("feat", request_id="r")
        assert result == "ok"
        assert log.final_layer == "L1"

    def test_fallback_to_next_layer_on_failure(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _sync_fail())
        h.register_layer("L2", "融合", lambda f: _sync_ok("from_l2"))
        result, log = h.predict_with_fallback("feat")
        assert result == "from_l2"
        assert log.final_layer == "L2"
        # 两层都被记录
        layers = [r.layer for r in log.layers_attempted]
        assert layers == ["L1", "L2"]

    def test_all_layers_fail_raises(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _sync_fail())
        h.register_layer("L2", "融合", lambda f: _sync_fail(ValueError("x")))
        with pytest.raises(FallbackExhaustedError):
            h.predict_with_fallback("feat")

    def test_async_predict_awaits_coroutine(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _async_ok("aync"))
        # 在事件循环外，predict_with_fallback 会 asyncio.run 消费 coroutine
        result, log = h.predict_with_fallback("feat")
        assert result == "aync"

    def test_async_predict_with_fallback_awaits(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _async_ok("a"))
        result, log = h.predict_with_fallback("feat")
        assert result == "a"

    def test_no_layers_raises(self):
        h = FallbackHierarchy()
        with pytest.raises(FallbackExhaustedError):
            h.predict_with_fallback("feat")


class TestAsyncPredictWithFallback:
    async def test_async_layer_succeeds(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _async_ok("ok"))
        result, log = await h.async_predict_with_fallback("feat")
        assert result == "ok"

    async def test_async_fallback_to_next(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _sync_fail())
        h.register_layer("L2", "融合", lambda f: _async_ok("l2"))
        result, log = await h.async_predict_with_fallback("feat")
        assert result == "l2"

    async def test_async_all_fail_raises(self):
        h = FallbackHierarchy()
        h.register_layer("L1", "主", lambda f: _sync_fail())
        with pytest.raises(FallbackExhaustedError):
            await h.async_predict_with_fallback("feat")


def test_global_instance_exists():
    from app.core.fallback_hierarchy import fallback_hierarchy

    assert isinstance(fallback_hierarchy, FallbackHierarchy)
