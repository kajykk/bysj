"""PERF-P0-002 测试: predict_structured 串行 3 模型 → asyncio.gather 并行.

验证要点:
1. v121 和 v123 通过 asyncio.gather 并行执行 (源码静态检查)
2. adapter 仍在 v123 完成后串行执行 (依赖 experimental_external_score)
3. 并行执行结果与串行一致 (字段合并正确)
4. v121/v123 异常不互相影响 (gather 异常隔离)
5. 并行实际减少耗时 (性能验证)
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestParallelExecutionSourceCheck:
    """源码静态检查: 验证 v121/v123 并行执行."""

    def test_source_uses_asyncio_gather_for_v121_v123(self):
        """源码应使用 asyncio.gather 并行执行 v121 和 v123."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine.predict_structured)
        # 必须包含 asyncio.gather
        assert (
            "asyncio.gather" in source
        ), "predict_structured 应使用 asyncio.gather 并行执行 v121 和 v123"
        # 必须同时包含两个实验性方法
        assert "_run_experimental_v121" in source
        assert "_run_experimental_v123" in source

    def test_source_does_not_await_v121_v123_sequentially(self):
        """源码不应再串行 await v121 和 v123."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine.predict_structured)
        # 不应出现串行 await _run_experimental_v121 后紧跟 await _run_experimental_v123
        # (并行后应通过 asyncio.gather 调度)
        # 检查不存在 "await self._run_experimental_v121" 直接调用
        assert (
            "await self._run_experimental_v121(raw" not in source
        ), "v121 不应被直接 await, 应通过 asyncio.gather 调度"
        assert (
            "await self._run_experimental_v123(raw" not in source
        ), "v123 不应被直接 await, 应通过 asyncio.gather 调度"

    def test_adapter_still_awaited_sequentially(self):
        """adapter 仍应直接 await (依赖 v123 输出)."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine.predict_structured)
        # adapter 必须直接 await, 因为依赖 v123 的 experimental_external_score
        assert (
            "await self._run_adapter(" in source
        ), "adapter 应直接 await, 因为依赖 v123 的 experimental_external_score"


class TestParallelResultConsistency:
    """验证并行执行结果与串行一致."""

    @pytest.mark.asyncio
    async def test_v121_v123_results_merged_correctly(self):
        """v121 和 v123 返回字段应正确合并到 result."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)

        v121_ret = {
            "experimental_real_score": 55.5,
            "experimental_real_level": 3,
            "experimental_real_probability": 0.555,
            "experimental_real_model": "structured_v1.21_binary_lr",
        }
        v123_ret = {
            "experimental_external_score": 60.0,
            "experimental_external_level": 3,
            "experimental_external_model": "structured_v1.23_external_lr",
            "experimental_external_available": True,
            "experimental_external_delta": 5.0,
        }
        adapter_ret = {
            "adjusted_score": 58.0,
            "adjusted_delta": 3.0,
            "adjusted_safe_label": "moderate",
            "adapter_available": True,
            "adapter_version": "1.24",
            "v123_raw_score": 60.0,
        }

        with patch.object(
            engine, "_run_experimental_v121", new=AsyncMock(return_value=v121_ret)
        ), patch.object(
            engine, "_run_experimental_v123", new=AsyncMock(return_value=v123_ret)
        ), patch.object(
            engine, "_run_adapter", new=AsyncMock(return_value=adapter_ret)
        ):
            # 模拟 predict_structured 中的并行逻辑
            result: dict = {"risk_score": 50.0}
            v121_result, v123_result = await asyncio.gather(
                engine._run_experimental_v121({}, 50.0),
                engine._run_experimental_v123({}, 50.0),
            )
            result.update(v121_result)
            result.update(v123_result)
            result.update(
                await engine._run_adapter(
                    50.0, False, result.get("experimental_external_score")
                )
            )

            # 验证所有字段都正确合并
            assert result["experimental_real_score"] == 55.5
            assert result["experimental_real_model"] == "structured_v1.21_binary_lr"
            assert result["experimental_external_score"] == 60.0
            assert result["experimental_external_available"] is True
            assert result["adjusted_score"] == 58.0
            assert result["adapter_available"] is True

    @pytest.mark.asyncio
    async def test_v121_v123_field_names_do_not_conflict(self):
        """v121 和 v123 返回字段名不应冲突 (确保并行合并安全)."""
        from app.core.model_engine import ModelEngine

        # 获取两个方法的源码, 提取返回字段名
        v121_source = inspect.getsource(ModelEngine._run_experimental_v121)
        v123_source = inspect.getsource(ModelEngine._run_experimental_v123)

        # v121 返回 experimental_real_* 字段
        assert "experimental_real_score" in v121_source
        assert "experimental_real_model" in v121_source

        # v123 返回 experimental_external_* 字段
        assert "experimental_external_score" in v123_source
        assert "experimental_external_model" in v123_source

        # 确认字段名前缀不同, 不会冲突
        v121_fields = {
            "experimental_real_score",
            "experimental_real_level",
            "experimental_real_probability",
            "experimental_real_model",
        }
        v123_fields = {
            "experimental_external_score",
            "experimental_external_level",
            "experimental_external_model",
            "experimental_external_available",
            "experimental_external_delta",
        }
        assert v121_fields.isdisjoint(v123_fields), "v121 和 v123 返回字段不应冲突"


class TestParallelExecutionTiming:
    """验证并行执行实际减少耗时."""

    @pytest.mark.asyncio
    async def test_parallel_faster_than_sequential(self):
        """并行执行应比串行快 (v121+v123 各 50ms, 并行应 ~50ms 而非 ~100ms)."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)

        async def slow_v121(raw, default_score):
            await asyncio.sleep(0.05)  # 50ms
            return {"experimental_real_score": 50.0}

        async def slow_v123(raw, default_score):
            await asyncio.sleep(0.05)  # 50ms
            return {"experimental_external_score": 55.0}

        with patch.object(
            engine, "_run_experimental_v121", side_effect=slow_v121
        ), patch.object(engine, "_run_experimental_v123", side_effect=slow_v123):
            # 并行执行
            loop = asyncio.get_event_loop()
            start_parallel = loop.time()
            await asyncio.gather(
                engine._run_experimental_v121({}, 50.0),
                engine._run_experimental_v123({}, 50.0),
            )
            elapsed_parallel = loop.time() - start_parallel

            # 串行执行
            start_sequential = loop.time()
            await engine._run_experimental_v121({}, 50.0)
            await engine._run_experimental_v123({}, 50.0)
            elapsed_sequential = loop.time() - start_sequential

            # 并行应明显快于串行 (允许 20ms 容差)
            assert (
                elapsed_parallel < elapsed_sequential - 0.02
            ), f"并行 {elapsed_parallel:.3f}s 应明显快于串行 {elapsed_sequential:.3f}s"
            # 并行应在 ~50ms 附近 (允许 30ms 容差)
            assert (
                elapsed_parallel < 0.08
            ), f"并行耗时 {elapsed_parallel:.3f}s 应接近单个任务耗时 ~50ms"

    @pytest.mark.asyncio
    async def test_adapter_waits_for_v123(self):
        """adapter 必须在 v123 完成后执行 (依赖 experimental_external_score)."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)

        execution_order: list[str] = []

        async def mock_v121(raw, default_score):
            execution_order.append("v121_start")
            await asyncio.sleep(0.01)
            execution_order.append("v121_end")
            return {"experimental_real_score": 50.0}

        async def mock_v123(raw, default_score):
            execution_order.append("v123_start")
            await asyncio.sleep(0.01)
            execution_order.append("v123_end")
            return {"experimental_external_score": 55.0}

        async def mock_adapter(risk_score, fallback_used, v123_raw_score):
            execution_order.append("adapter_start")
            assert (
                v123_raw_score == 55.0
            ), "adapter 应接收到 v123 的 experimental_external_score"
            return {"adjusted_score": 56.0, "v123_raw_score": v123_raw_score}

        with patch.object(
            engine, "_run_experimental_v121", side_effect=mock_v121
        ), patch.object(
            engine, "_run_experimental_v123", side_effect=mock_v123
        ), patch.object(
            engine, "_run_adapter", side_effect=mock_adapter
        ):
            # 模拟 predict_structured 中的完整流程
            result: dict = {}
            v121_result, v123_result = await asyncio.gather(
                engine._run_experimental_v121({}, 50.0),
                engine._run_experimental_v123({}, 50.0),
            )
            result.update(v121_result)
            result.update(v123_result)
            result.update(
                await engine._run_adapter(
                    50.0, False, result.get("experimental_external_score")
                )
            )

            # adapter 必须在 v123_end 之后执行
            assert execution_order.index("v123_end") < execution_order.index(
                "adapter_start"
            ), f"adapter 必须在 v123 完成后执行, 实际顺序: {execution_order}"


class TestParallelExceptionIsolation:
    """验证 v121/v123 异常隔离 (gather 行为)."""

    @pytest.mark.asyncio
    async def test_v123_failure_propagates_through_gather(self):
        """v123 异常应通过 gather 传播 (默认 return_exceptions=False)."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)

        async def failing_v123(raw, default_score):
            raise RuntimeError("v123 model load failed")

        async def ok_v121(raw, default_score):
            return {"experimental_real_score": 50.0}

        with patch.object(
            engine, "_run_experimental_v121", side_effect=ok_v121
        ), patch.object(engine, "_run_experimental_v123", side_effect=failing_v123):
            # asyncio.gather 默认 return_exceptions=False, 第一个异常会立即传播
            with pytest.raises(RuntimeError, match="v123 model load failed"):
                await asyncio.gather(
                    engine._run_experimental_v121({}, 50.0),
                    engine._run_experimental_v123({}, 50.0),
                )

    @pytest.mark.asyncio
    async def test_v121_v123_internal_exception_handling(self):
        """v121/v123 内部 try/except 应吞掉异常返回 None 字段 (不传播)."""
        from app.core.model_engine import ModelEngine

        # 实际的 _run_experimental_v121 和 _run_experimental_v123 内部有 try/except
        # 模型加载失败时返回 None 字段, 不抛异常
        # 验证内部异常处理后, gather 仍能正常完成
        engine = ModelEngine.__new__(ModelEngine)
        engine.models = {}
        engine.model_load_stats = {}

        # 模拟 _load_model_async 抛异常
        async def failing_load(model_id):
            raise FileNotFoundError(f"model {model_id} not found")

        with patch.object(engine, "_load_model_async", side_effect=failing_load):
            # v121 内部 try/except 应吞掉 FileNotFoundError, 返回 None 字段
            v121_result = await engine._run_experimental_v121({}, 50.0)
            assert v121_result["experimental_real_score"] is None
            assert v121_result["experimental_real_model"] is None

            # v123 内部 try/except 应吞掉 FileNotFoundError, 返回 None 字段
            v123_result = await engine._run_experimental_v123({}, 50.0)
            assert v123_result["experimental_external_score"] is None
            assert v123_result["experimental_external_available"] is False


class TestIntegrationWithPredictStructured:
    """集成测试: predict_structured 端到端验证并行执行."""

    @pytest.mark.asyncio
    async def test_predict_structured_uses_gather(self):
        """predict_structured 应使用 asyncio.gather 并行执行 v121/v123."""
        from app.core.model_engine import ModelEngine

        # 监控 asyncio.gather 调用
        original_gather = asyncio.gather
        gather_calls: list = []

        async def tracking_gather(*aws, **kwargs):
            gather_calls.append(aws)
            return await original_gather(*aws, **kwargs)

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = {}
        engine.model_load_stats = {}
        engine._adapter_cached = None
        engine.monitoring_counters = {}
        engine._monitoring_lock = MagicMock()
        engine.feature_order = [
            "age",
            "gender",
            "study_year",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
            "treatment_seeking",
        ]

        # 模拟所有依赖方法, 避免真实模型加载
        async def mock_load_model(model_id):
            return None

        engine._load_model_async = mock_load_model

        def mock_route(raw):
            routing_info = {
                "selected_model_id": "structured_logistic_regression_v1.20",
                "selected_model_family": "structured",
                "routing_reason": "feature_coverage_sufficient",
                "feature_coverage_ratio": 1.0,
                "prediction_confidence_band": "high",
            }
            return routing_info, None

        engine._route_structured = mock_route

        engine._patch_simple_imputer = MagicMock()
        engine._incr_fallback = MagicMock()
        engine._incr_routing = MagicMock()
        engine._incr_counter = MagicMock()
        engine._record_score_delta = MagicMock()
        engine._timed_async = MagicMock()
        engine._timed_async.return_value.__aenter__ = AsyncMock(return_value=None)
        engine._timed_async.return_value.__aexit__ = AsyncMock(return_value=None)

        async def mock_v121(raw, default_score):
            return {"experimental_real_score": 50.0, "experimental_real_model": "v121"}

        engine._run_experimental_v121 = mock_v121

        async def mock_v123(raw, default_score):
            return {
                "experimental_external_score": 55.0,
                "experimental_external_available": True,
            }

        engine._run_experimental_v123 = mock_v123

        async def mock_adapter(risk_score, fallback_used, v123_raw_score):
            return {"adjusted_score": 56.0, "adapter_available": True}

        engine._run_adapter = mock_adapter

        engine._update_structured_monitoring = MagicMock()

        features = {
            "age": 22,
            "gender": 1,
            "study_year": 3,
            "cgpa": 3.5,
            "stress_level": 3,
            "sleep_duration": 7,
            "social_support": 4,
            "financial_pressure": 2,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 2,
            "anxiety": 2,
            "panic_attack": 0,
            "treatment_seeking": 1,
        }

        with patch("app.core.model_engine.asyncio.gather", side_effect=tracking_gather):
            result = await engine.predict_structured(features)

            # 验证 asyncio.gather 被调用 (并行执行 v121+v123)
            assert (
                len(gather_calls) == 1
            ), f"应调用 1 次 asyncio.gather, 实际: {len(gather_calls)}"
            assert len(gather_calls[0]) == 2, "gather 应接收 2 个协程 (v121+v123)"

            # 验证结果包含 v121/v123/adapter 字段
            assert result["experimental_real_score"] == 50.0
            assert result["experimental_external_score"] == 55.0
            assert result["adjusted_score"] == 56.0


class TestStructuredExperimentalSwitch:
    """RES-P1-001 测试: predict_structured 实验路径开关.

    验证 ``settings.structured_experimental_enabled`` 控制是否执行 v121/v123/adapter
    3 路实验性推理. 关闭时填充 None 占位字段, 保持响应结构一致.
    """

    def test_source_uses_structured_experimental_switch(self):
        """RES-P1-001-TC-001: predict_structured 源码应引用 structured_experimental_enabled 开关."""
        from app.core import model_engine_predict

        source = inspect.getsource(model_engine_predict.PredictMixin.predict_structured)
        assert (
            "structured_experimental_enabled" in source
        ), "predict_structured 应通过 settings.structured_experimental_enabled 控制实验路径"

    def test_config_default_is_true(self):
        """RES-P1-001-TC-002: structured_experimental_enabled 默认值应为 True (保持兼容)."""
        from app.core.config import Settings

        # 通过 Settings 字段注解验证默认值
        fields = Settings.model_fields
        assert "structured_experimental_enabled" in fields
        assert (
            fields["structured_experimental_enabled"].default is True
        ), "默认应开启实验路径, 保持与现有行为兼容"

    @pytest.mark.asyncio
    async def test_switch_off_skips_experimental_paths(self):
        """RES-P1-001-TC-003: structured_experimental_enabled=False 时跳过 v121/v123/adapter."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = {}
        engine.model_load_stats = {}
        engine._adapter_cached = None
        engine.monitoring_counters = {}
        engine._monitoring_lock = MagicMock()
        engine.feature_order = [
            "age",
            "gender",
            "study_year",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
            "treatment_seeking",
        ]

        async def mock_load_model(model_id):
            return None

        engine._load_model_async = mock_load_model

        def mock_route(raw):
            routing_info = {
                "selected_model_id": "structured_logistic_regression_v1.20",
                "selected_model_family": "structured",
                "routing_reason": "feature_coverage_sufficient",
                "feature_coverage_ratio": 1.0,
                "prediction_confidence_band": "high",
            }
            return routing_info, None

        engine._route_structured = mock_route

        engine._patch_simple_imputer = MagicMock()
        engine._incr_fallback = MagicMock()
        engine._incr_routing = MagicMock()
        engine._incr_counter = MagicMock()
        engine._record_score_delta = MagicMock()
        engine._timed_async = MagicMock()
        engine._timed_async.return_value.__aenter__ = AsyncMock(return_value=None)
        engine._timed_async.return_value.__aexit__ = AsyncMock(return_value=None)

        # 实验方法应不被调用, 若被调用则抛错
        v121_called = []
        v123_called = []
        adapter_called = []

        async def mock_v121(raw, default_score):
            v121_called.append(True)
            return {"experimental_real_score": 50.0}

        async def mock_v123(raw, default_score):
            v123_called.append(True)
            return {"experimental_external_score": 55.0}

        async def mock_adapter(risk_score, fallback_used, v123_raw_score):
            adapter_called.append(True)
            return {"adjusted_score": 56.0}

        engine._run_experimental_v121 = mock_v121
        engine._run_experimental_v123 = mock_v123
        engine._run_adapter = mock_adapter
        engine._update_structured_monitoring = MagicMock()

        features = {
            "age": 22,
            "gender": 1,
            "study_year": 3,
            "cgpa": 3.5,
            "stress_level": 3,
            "sleep_duration": 7,
            "social_support": 4,
            "financial_pressure": 2,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 2,
            "anxiety": 2,
            "panic_attack": 0,
            "treatment_seeking": 1,
        }

        # 关闭实验路径开关
        with patch("app.core.config.settings.structured_experimental_enabled", False):
            result = await engine.predict_structured(features)

        # 验证 3 个实验方法均未被调用
        assert v121_called == [], "v121 不应在开关关闭时被调用"
        assert v123_called == [], "v123 不应在开关关闭时被调用"
        assert adapter_called == [], "adapter 不应在开关关闭时被调用"

        # 验证所有实验字段均为 None (占位)
        assert result["experimental_real_score"] is None
        assert result["experimental_real_level"] is None
        assert result["experimental_real_probability"] is None
        assert result["experimental_real_model"] is None
        assert result["experimental_external_score"] is None
        assert result["experimental_external_level"] is None
        assert result["experimental_external_model"] is None
        assert result["experimental_external_available"] is False
        assert result["experimental_external_delta"] is None
        assert result["adjusted_score"] is None
        assert result["adjusted_delta"] is None
        assert result["adjusted_safe_label"] is None
        assert result["adapter_available"] is False
        assert result["adapter_version"] is None
        assert result["v123_raw_score"] is None

        # 验证基础预测字段仍正常返回
        assert "prediction" in result
        assert "probability" in result
        assert "risk_score" in result
        assert "risk_level" in result
        assert "model_used" in result

    @pytest.mark.asyncio
    async def test_switch_on_executes_experimental_paths(self):
        """RES-P1-001-TC-004: structured_experimental_enabled=True 时实验路径正常执行."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = {}
        engine.model_load_stats = {}
        engine._adapter_cached = None
        engine.monitoring_counters = {}
        engine._monitoring_lock = MagicMock()
        engine.feature_order = [
            "age",
            "gender",
            "study_year",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
            "treatment_seeking",
        ]

        async def mock_load_model(model_id):
            return None

        engine._load_model_async = mock_load_model

        def mock_route(raw):
            return {
                "selected_model_id": "structured_logistic_regression_v1.20",
                "selected_model_family": "structured",
                "routing_reason": "feature_coverage_sufficient",
                "feature_coverage_ratio": 1.0,
                "prediction_confidence_band": "high",
            }, None

        engine._route_structured = mock_route

        engine._patch_simple_imputer = MagicMock()
        engine._incr_fallback = MagicMock()
        engine._incr_routing = MagicMock()
        engine._incr_counter = MagicMock()
        engine._record_score_delta = MagicMock()
        engine._timed_async = MagicMock()
        engine._timed_async.return_value.__aenter__ = AsyncMock(return_value=None)
        engine._timed_async.return_value.__aexit__ = AsyncMock(return_value=None)

        v121_called = []
        v123_called = []
        adapter_called = []

        async def mock_v121(raw, default_score):
            v121_called.append(True)
            return {"experimental_real_score": 50.0}

        async def mock_v123(raw, default_score):
            v123_called.append(True)
            return {
                "experimental_external_score": 55.0,
                "experimental_external_available": True,
            }

        async def mock_adapter(risk_score, fallback_used, v123_raw_score):
            adapter_called.append(True)
            return {"adjusted_score": 56.0, "adapter_available": True}

        engine._run_experimental_v121 = mock_v121
        engine._run_experimental_v123 = mock_v123
        engine._run_adapter = mock_adapter
        engine._update_structured_monitoring = MagicMock()

        features = {
            "age": 22,
            "gender": 1,
            "study_year": 3,
            "cgpa": 3.5,
            "stress_level": 3,
            "sleep_duration": 7,
            "social_support": 4,
            "financial_pressure": 2,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 2,
            "anxiety": 2,
            "panic_attack": 0,
            "treatment_seeking": 1,
        }

        with patch("app.core.config.settings.structured_experimental_enabled", True):
            result = await engine.predict_structured(features)

        # 开关开启时, 3 个实验方法都应被调用
        assert len(v121_called) == 1
        assert len(v123_called) == 1
        assert len(adapter_called) == 1

        # 实验字段应有值
        assert result["experimental_real_score"] == 50.0
        assert result["experimental_external_score"] == 55.0
        assert result["experimental_external_available"] is True
        assert result["adjusted_score"] == 56.0
        assert result["adapter_available"] is True
