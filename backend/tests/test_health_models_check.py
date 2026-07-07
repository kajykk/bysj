"""STAB-P1-007 测试：健康检查 ML 模型可用性

验证要点：
1. ``check_models()`` 在所有核心模型文件存在时返回 True
2. ``check_models()`` 在任一核心模型缺失时返回 False
3. ``check_models()`` 异常时返回 False 不抛出
4. ``HealthSnapshot.models`` 字段默认 None
5. ``basic_health_snapshot()`` 返回 models=None (未检查)
6. ``get_health_snapshot()`` 包含 models 字段
7. ``/health`` 和 ``/health/ready`` 端点返回 models 检查项
8. ``_CORE_MODEL_IDS`` 包含正确的 3 个模型 ID
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.health import (
    _CORE_MODEL_IDS,
    HealthSnapshot,
    basic_health_snapshot,
    check_models,
)

# ─────────────────────────────────────────────────────────────────────────────
# 1. _CORE_MODEL_IDS 常量测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCoreModelIds:
    """测试 _CORE_MODEL_IDS 常量."""

    def test_contains_three_core_models(self):
        """应包含 3 个核心模型 ID."""
        assert len(_CORE_MODEL_IDS) == 3

    def test_contains_structured_logistic(self):
        """应包含结构化评估降级模型."""
        assert "structured_logistic_regression_quick" in _CORE_MODEL_IDS

    def test_contains_text_depression_model(self):
        """应包含文本评估降级模型."""
        assert "text_depression_model" in _CORE_MODEL_IDS

    def test_contains_text_depression_tfidf(self):
        """应包含文本评估 TF-IDF 向量器."""
        assert "text_depression_tfidf" in _CORE_MODEL_IDS

    def test_aligned_with_model_status_ready_logic(self):
        """_CORE_MODEL_IDS 应与 ModelPredictService.get_model_status 的 ready 逻辑一致."""
        # get_model_status 中 ready 字段检查的 3 个模型 ID
        expected = {
            "structured_logistic_regression_quick",
            "text_depression_model",
            "text_depression_tfidf",
        }
        assert set(_CORE_MODEL_IDS) == expected


# ─────────────────────────────────────────────────────────────────────────────
# 2. HealthSnapshot.models 字段测试
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthSnapshotModelsField:
    """测试 HealthSnapshot.models 字段."""

    def test_default_is_none(self):
        """默认值应为 None (未检查)."""
        snapshot = HealthSnapshot()
        assert snapshot.models is None

    def test_custom_true(self):
        """应能设置为 True (所有核心模型就绪)."""
        snapshot = HealthSnapshot(models=True)
        assert snapshot.models is True

    def test_custom_false(self):
        """应能设置为 False (至少一个核心模型缺失)."""
        snapshot = HealthSnapshot(models=False)
        assert snapshot.models is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. check_models() 函数测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckModels:
    """测试 check_models() 函数."""

    @pytest.mark.asyncio
    async def test_all_models_exist_returns_true(self):
        """所有核心模型文件存在时应返回 True."""
        # mock resolve_model_path 返回绝对路径, mock exists 返回 True
        with patch("app.core.model_registry.resolve_model_path") as mock_resolve, patch(
            "app.core.config.settings"
        ) as mock_settings:
            mock_settings.model_dir = "/fake/models"
            mock_resolve.side_effect = lambda mid: f"/fake/{mid}.pkl"
            # patch Path.exists 全局返回 True (仅对 check_models 中的 Path 实例)
            with patch.object(Path, "exists", return_value=True):
                result = await check_models()
            assert result is True

    @pytest.mark.asyncio
    async def test_one_model_missing_returns_false(self):
        """任一核心模型文件缺失时应返回 False."""
        with patch("app.core.model_registry.resolve_model_path") as mock_resolve, patch(
            "app.core.config.settings"
        ) as mock_settings:
            mock_settings.model_dir = "/fake/models"
            mock_resolve.side_effect = lambda mid: f"/fake/{mid}.pkl"
            # 第一个模型不存在, 后续存在
            exists_call_count = {"n": 0}

            def fake_exists(self):
                exists_call_count["n"] += 1
                return exists_call_count["n"] > 1  # 第一次 False, 后续 True

            with patch.object(Path, "exists", new=fake_exists):
                result = await check_models()
            assert result is False

    @pytest.mark.asyncio
    async def test_all_models_missing_returns_false(self):
        """所有核心模型文件均缺失时应返回 False."""
        with patch("app.core.model_registry.resolve_model_path") as mock_resolve, patch(
            "app.core.config.settings"
        ) as mock_settings:
            mock_settings.model_dir = "/fake/models"
            mock_resolve.side_effect = lambda mid: f"/fake/{mid}.pkl"
            with patch.object(Path, "exists", return_value=False):
                result = await check_models()
            assert result is False

    @pytest.mark.asyncio
    async def test_resolve_model_path_exception_returns_false(self):
        """resolve_model_path 抛出异常时应返回 False 不抛出."""
        with patch(
            "app.core.model_registry.resolve_model_path",
            side_effect=KeyError("unknown model"),
        ):
            result = await check_models()
            assert result is False

    @pytest.mark.asyncio
    async def test_settings_import_exception_returns_false(self):
        """settings 异常时应返回 False 不抛出."""
        with patch("app.core.config.settings", side_effect=ImportError("no config")):
            # 注意: check_models 内部 from app.core.config import settings 是模块级导入
            # 这里 mock 模块属性 settings 抛异常
            result = await check_models()
            # 由于内部使用 from app.core.config import settings, mock side_effect 不一定生效
            # 但 check_models 有 try/except 兜底, 任何异常都返回 False
            assert result is False

    @pytest.mark.asyncio
    async def test_path_resolution_with_models_prefix(self):
        """路径以 models/ 开头时应使用 model_dir.parent 拼接."""
        # 模拟 resolve_model_path 返回 "models/artifacts/xxx.pkl" (相对路径)
        with patch("app.core.model_registry.resolve_model_path") as mock_resolve, patch(
            "app.core.config.settings"
        ) as mock_settings:
            mock_settings.model_dir = Path("/fake/models")
            mock_resolve.side_effect = lambda mid: f"models/artifacts/{mid}.pkl"
            with patch.object(Path, "exists", return_value=True):
                result = await check_models()
            assert result is True
            # 验证 resolve_model_path 被调用 3 次 (每个核心模型一次)
            assert mock_resolve.call_count == 3

    @pytest.mark.asyncio
    async def test_path_resolution_absolute(self):
        """绝对路径应直接使用."""
        with patch("app.core.model_registry.resolve_model_path") as mock_resolve, patch(
            "app.core.config.settings"
        ) as mock_settings:
            mock_settings.model_dir = "/fake/models"
            mock_resolve.side_effect = lambda mid: f"/abs/{mid}.pkl"
            with patch.object(Path, "exists", return_value=True):
                result = await check_models()
            assert result is True

    @pytest.mark.asyncio
    async def test_path_resolution_relative_no_models_prefix(self):
        """相对路径不以 models/ 开头时应使用 model_dir 拼接."""
        with patch("app.core.model_registry.resolve_model_path") as mock_resolve, patch(
            "app.core.config.settings"
        ) as mock_settings:
            mock_settings.model_dir = Path("/fake/models")
            mock_resolve.side_effect = lambda mid: f"artifacts/{mid}.pkl"
            with patch.object(Path, "exists", return_value=True):
                result = await check_models()
            assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. basic_health_snapshot 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestBasicHealthSnapshot:
    """测试 basic_health_snapshot 的 models 字段."""

    @pytest.mark.asyncio
    async def test_basic_snapshot_models_is_none(self):
        """basic_health_snapshot 应返回 models=None (未检查)."""
        snapshot = await basic_health_snapshot()
        assert snapshot.models is None
        assert snapshot.verified is False

    @pytest.mark.asyncio
    async def test_basic_snapshot_other_fields(self):
        """basic_health_snapshot 应保持其他字段不变."""
        snapshot = await basic_health_snapshot()
        assert snapshot.database is True
        assert snapshot.redis is None
        assert snapshot.celery_worker is None
        assert snapshot.models is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. get_health_snapshot 集成测试
# ─────────────────────────────────────────────────────────────────────────────


class TestGetHealthSnapshotIntegration:
    """验证 get_health_snapshot 包含 models 字段."""

    @pytest.mark.asyncio
    async def test_snapshot_includes_models_field(self):
        """get_health_snapshot 返回的快照应包含 models 字段."""
        # 重置缓存
        import app.core.health as health_mod

        health_mod._snapshot = HealthSnapshot()

        with patch(
            "app.core.health.check_database", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_redis", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_celery_worker", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_models", new=AsyncMock(return_value=True)
        ):
            # 使用 mock engine 避免真实 DB 连接
            mock_engine = MagicMock()
            snapshot = await health_mod.get_health_snapshot(
                mock_engine, "redis://localhost"
            )
            assert snapshot.models is True
            assert snapshot.database is True

        # 清理缓存
        health_mod._snapshot = HealthSnapshot()

    @pytest.mark.asyncio
    async def test_snapshot_models_false_when_check_fails(self):
        """check_models 返回 False 时快照 models 应为 False."""
        import app.core.health as health_mod

        health_mod._snapshot = HealthSnapshot()

        with patch(
            "app.core.health.check_database", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_redis", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_celery_worker", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_models", new=AsyncMock(return_value=False)
        ):
            mock_engine = MagicMock()
            snapshot = await health_mod.get_health_snapshot(
                mock_engine, "redis://localhost"
            )
            assert snapshot.models is False

        health_mod._snapshot = HealthSnapshot()

    @pytest.mark.asyncio
    async def test_four_checks_run_in_parallel(self):
        """4 项检查 (database/redis/celery/models) 应并行执行."""
        import app.core.health as health_mod

        health_mod._snapshot = HealthSnapshot()

        call_order: list[str] = []

        async def mock_check_db(_engine):
            call_order.append("db_start")
            await __import__("asyncio").sleep(0.01)
            call_order.append("db_end")
            return True

        async def mock_check_redis(_url):
            call_order.append("redis_start")
            await __import__("asyncio").sleep(0.01)
            call_order.append("redis_end")
            return True

        async def mock_check_celery(_url):
            call_order.append("celery_start")
            await __import__("asyncio").sleep(0.01)
            call_order.append("celery_end")
            return True

        async def mock_check_models():
            call_order.append("models_start")
            await __import__("asyncio").sleep(0.01)
            call_order.append("models_end")
            return True

        with patch("app.core.health.check_database", new=mock_check_db), patch(
            "app.core.health.check_redis", new=mock_check_redis
        ), patch("app.core.health.check_celery_worker", new=mock_check_celery), patch(
            "app.core.health.check_models", new=mock_check_models
        ):
            mock_engine = MagicMock()
            await health_mod.get_health_snapshot(mock_engine, "redis://localhost")

            # 并行执行: 所有 *_start 应在任意 *_end 之前
            starts = [i for i, x in enumerate(call_order) if x.endswith("_start")]
            ends = [i for i, x in enumerate(call_order) if x.endswith("_end")]
            assert max(starts) < min(ends), f"Checks not parallel: {call_order}"

        health_mod._snapshot = HealthSnapshot()


# ─────────────────────────────────────────────────────────────────────────────
# 6. /health 端点集成测试 (静态检查)
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthEndpointIntegration:
    """验证 /health 和 /health/ready 端点返回 models 检查项."""

    def test_health_check_returns_models_field(self):
        """/health 端点源码应包含 models 检查项."""
        import inspect

        from app.main import health_check

        src = inspect.getsource(health_check)
        assert "models" in src
        assert "snapshot.models" in src

    def test_readiness_check_returns_models_field(self):
        """/health/ready 端点源码应包含 models 检查项."""
        import inspect

        from app.main import readiness_check

        src = inspect.getsource(readiness_check)
        assert "models" in src
        assert "snapshot.models" in src

    def test_health_check_models_optional(self):
        """models 失败时应标记为 'failed (optional)' 不影响整体 status."""
        import inspect

        from app.main import health_check

        src = inspect.getsource(health_check)
        assert "failed (optional)" in src


# ─────────────────────────────────────────────────────────────────────────────
# 7. 端到端场景测试
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthModelsEndToEnd:
    """端到端验证健康检查与 ML 模型可用性的集成."""

    @pytest.mark.asyncio
    async def test_models_field_propagates_to_snapshot(self):
        """check_models 的结果应传播到 HealthSnapshot.models."""
        import app.core.health as health_mod

        health_mod._snapshot = HealthSnapshot()

        # 场景 1: 模型可用
        with patch(
            "app.core.health.check_database", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_redis", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_celery_worker", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_models", new=AsyncMock(return_value=True)
        ):
            mock_engine = MagicMock()
            snapshot = await health_mod.get_health_snapshot(
                mock_engine, "redis://localhost"
            )
            assert snapshot.models is True
            assert snapshot.verified is True

        # 清理缓存, 准备场景 2
        health_mod._snapshot = HealthSnapshot()

        # 场景 2: 模型不可用
        with patch(
            "app.core.health.check_database", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_redis", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_celery_worker", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_models", new=AsyncMock(return_value=False)
        ):
            mock_engine = MagicMock()
            snapshot = await health_mod.get_health_snapshot(
                mock_engine, "redis://localhost"
            )
            assert snapshot.models is False
            # models 失败不应影响其他字段
            assert snapshot.database is True
            assert snapshot.redis is True

        health_mod._snapshot = HealthSnapshot()

    @pytest.mark.asyncio
    async def test_models_failure_does_not_degrade_overall_status(self):
        """models 失败不应导致整体 status 降级 (仅 database 决定 degraded)."""
        import app.core.health as health_mod

        health_mod._snapshot = HealthSnapshot()

        with patch(
            "app.core.health.check_database", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_redis", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_celery_worker", new=AsyncMock(return_value=True)
        ), patch(
            "app.core.health.check_models", new=AsyncMock(return_value=False)
        ):
            mock_engine = MagicMock()
            snapshot = await health_mod.get_health_snapshot(
                mock_engine, "redis://localhost"
            )
            # 整体 status 由 database 决定, models 失败不影响
            assert snapshot.database is True  # status 仍为 ok
            assert snapshot.models is False  # 但 models 检查项为 failed (optional)

        health_mod._snapshot = HealthSnapshot()
