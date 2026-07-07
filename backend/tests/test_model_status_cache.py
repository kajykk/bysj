"""PERF-P1-002 (T-P2-011): model_status 端点 30s Redis 缓存测试.

验证缓存命中/未命中/降级路径.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.api.v1.model_predict.status as status_module


@pytest.fixture(autouse=True)
def _reset_cache():
    """每个测试前重置内存缓存, 避免跨测试污染."""
    from app.core.cache import clear_memory_cache

    clear_memory_cache()
    yield
    clear_memory_cache()


class TestGetCachedModelStatus:
    """测试 _get_cached_model_status 缓存逻辑."""

    @pytest.mark.asyncio
    async def test_cache_miss_computes_and_backfills(self):
        """TC-PERF-P1-002-001: cache miss 时调用 get_model_status 并回填缓存."""
        fake_status = {
            "items": [],
            "ready": True,
            "performance": {},
            "performance_summary": {},
        }
        mock_service = MagicMock()
        mock_service.get_model_status.return_value = fake_status

        with patch.object(
            status_module, "cache_get", new=AsyncMock(return_value=None)
        ) as mock_get, patch.object(
            status_module, "cache_set", new=AsyncMock(return_value=True)
        ) as mock_set, patch.object(
            status_module, "ModelPredictService", return_value=mock_service
        ):
            result = await status_module._get_cached_model_status()

        assert result == fake_status
        mock_get.assert_awaited_once_with(status_module._MODEL_STATUS_CACHE_KEY)
        mock_set.assert_awaited_once_with(
            status_module._MODEL_STATUS_CACHE_KEY,
            fake_status,
            status_module._MODEL_STATUS_CACHE_TTL,
        )
        mock_service.get_model_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_computation(self):
        """TC-PERF-P1-002-002: cache hit 时不调用 get_model_status."""
        cached_status = {
            "items": ["cached"],
            "ready": True,
            "performance": {"cache_size": 5},
        }

        with patch.object(
            status_module, "cache_get", new=AsyncMock(return_value=cached_status)
        ) as mock_get, patch.object(
            status_module, "cache_set", new=AsyncMock()
        ) as mock_set, patch.object(
            status_module, "ModelPredictService"
        ) as mock_svc_cls:
            result = await status_module._get_cached_model_status()

        assert result == cached_status
        mock_get.assert_awaited_once_with(status_module._MODEL_STATUS_CACHE_KEY)
        # cache hit 时不应回填缓存
        mock_set.assert_not_awaited()
        # cache hit 时不应实例化 service
        mock_svc_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_set_failure_degrades_gracefully(self, caplog):
        """TC-PERF-P1-002-003: cache_set 失败时降级为直接返回结果, 不影响请求."""
        fake_status = {"items": [], "ready": True}
        mock_service = MagicMock()
        mock_service.get_model_status.return_value = fake_status

        with patch.object(
            status_module, "cache_get", new=AsyncMock(return_value=None)
        ), patch.object(
            status_module,
            "cache_set",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ) as mock_set, patch.object(
            status_module, "ModelPredictService", return_value=mock_service
        ):
            import logging

            with caplog.at_level(
                logging.WARNING, logger="app.api.v1.model_predict.status"
            ):
                result = await status_module._get_cached_model_status()

        # 即使 cache_set 失败, 仍返回计算结果
        assert result == fake_status
        mock_set.assert_awaited_once()
        assert "cache_set failed" in caplog.text

    @pytest.mark.asyncio
    async def test_cache_ttl_is_30_seconds(self):
        """TC-PERF-P1-002-004: 缓存 TTL 为 30 秒."""
        assert status_module._MODEL_STATUS_CACHE_TTL == 30

    @pytest.mark.asyncio
    async def test_cache_key_is_stable(self):
        """TC-PERF-P1-002-005: 缓存 key 为固定的 model_status:v1."""
        assert status_module._MODEL_STATUS_CACHE_KEY == "model_status:v1"


class TestModelStatusEndpointIntegration:
    """测试 model_status 与 model_performance_debug 共享缓存."""

    @pytest.mark.asyncio
    async def test_model_performance_debug_uses_cached_performance(self):
        """TC-PERF-P1-002-006: model_performance_debug 从缓存中提取 performance 部分."""
        cached_status = {
            "items": [],
            "ready": True,
            "performance": {"cache_size": 10, "uptime_seconds": 100.0},
            "performance_summary": {"cached_models": 10},
        }

        with patch.object(
            status_module, "cache_get", new=AsyncMock(return_value=cached_status)
        ), patch.object(
            status_module, "cache_set", new=AsyncMock()
        ) as mock_set, patch.object(
            status_module, "ModelPredictService"
        ) as mock_svc_cls:
            result = await status_module._get_cached_model_status()

        # model_performance_debug 只取 performance 部分
        performance = result.get("performance", {})
        assert performance["cache_size"] == 10
        assert performance["uptime_seconds"] == 100.0
        # 不应实例化 service (cache hit)
        mock_svc_cls.assert_not_called()
        mock_set.assert_not_awaited()
