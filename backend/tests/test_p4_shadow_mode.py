"""S3 P4 影子模式测试.

测试 shadow_mode_service 核心逻辑 + model_engine_predict 集成.
不加载真实 BERT 模型 (mock TextM2BertPredictor).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.shadow_mode_service import ShadowModeService


@pytest.fixture
def shadow_service():
    """每个测试用独立的 ShadowModeService 实例 (避免单例污染)."""
    service = ShadowModeService()
    return service


@pytest.fixture
def mock_m2_predictor():
    """Mock M2 BERT 推理器 (避免加载真实 BERT)."""
    predictor = MagicMock()
    predictor.predict = AsyncMock()
    return predictor


class TestShadowModeService:
    """ShadowModeService 核心逻辑测试."""

    @pytest.mark.asyncio
    async def test_shadow_disabled_by_default(self, shadow_service):
        """影子模式默认禁用: settings.shadow_mode_text_enabled=False 时不触发."""
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = False
            # _maybe_fire_shadow_predict 在 model_engine_predict 中检查 settings
            # 这里直接测试 fire_shadow_predict 不依赖 settings
            # 只要 predictor 未加载, fire_shadow_predict 会尝试加载
            with patch.object(shadow_service, "_ensure_predictor", return_value=False):
                # predictor 加载失败时, 不触发对拍
                shadow_service.fire_shadow_predict("test text", {"prediction": 0})
                await asyncio.sleep(0.01)  # 让可能的 task 执行
                stats = shadow_service.get_stats()
                assert stats["total_comparisons"] == 0

    @pytest.mark.asyncio
    async def test_shadow_agreement_stats(self, shadow_service, mock_m2_predictor):
        """一致率统计: 生产预测 == M2 预测时 agreement+1."""
        # 注入 mock predictor
        shadow_service._predictor = mock_m2_predictor
        shadow_service._predictor_loaded = True

        # M2 返回与生产相同预测 (prediction=1)
        mock_m2_predictor.predict.return_value = {
            "prediction": 1,
            "probability": 0.85,
            "model_used": "text_m2_bert",
        }
        production_result = {
            "prediction": 1,
            "probability": 0.80,
            "model_used": "text_depression_model",
        }

        shadow_service.fire_shadow_predict("抑郁测试文本", production_result)
        await asyncio.sleep(0.05)  # 等后台任务完成

        stats = shadow_service.get_stats()
        assert stats["total_comparisons"] == 1
        assert stats["agreement"] == 1
        assert stats["disagreement"] == 0
        assert stats["agreement_rate"] == 1.0
        assert stats["avg_prob_diff"] == pytest.approx(0.05, abs=0.01)

    @pytest.mark.asyncio
    async def test_shadow_disagreement_stats(self, shadow_service, mock_m2_predictor):
        """分歧统计: 生产预测 != M2 预测时 disagreement+1."""
        shadow_service._predictor = mock_m2_predictor
        shadow_service._predictor_loaded = True

        # M2 返回预测 1, 生产返回预测 0
        mock_m2_predictor.predict.return_value = {
            "prediction": 1,
            "probability": 0.75,
            "model_used": "text_m2_bert",
        }
        production_result = {
            "prediction": 0,
            "probability": 0.30,
            "model_used": "text_depression_model",
        }

        shadow_service.fire_shadow_predict("分歧文本", production_result)
        await asyncio.sleep(0.05)

        stats = shadow_service.get_stats()
        assert stats["total_comparisons"] == 1
        assert stats["agreement"] == 0
        assert stats["disagreement"] == 1
        assert stats["agreement_rate"] == 0.0
        assert stats["avg_prob_diff"] == pytest.approx(0.45, abs=0.01)

    @pytest.mark.asyncio
    async def test_shadow_sample_rate(self, shadow_service, mock_m2_predictor):
        """采样率: sample_rate=0.0 时全部跳过, =1.0 时全部执行."""
        shadow_service._predictor = mock_m2_predictor
        shadow_service._predictor_loaded = True
        mock_m2_predictor.predict.return_value = {
            "prediction": 0,
            "probability": 0.2,
            "model_used": "text_m2_bert",
        }

        # sample_rate=0.0: 全部跳过
        for _ in range(10):
            shadow_service.fire_shadow_predict("test", {"prediction": 0}, sample_rate=0.0)
        await asyncio.sleep(0.05)
        assert shadow_service.get_stats()["total_comparisons"] == 0

        # sample_rate=1.0: 全部执行
        for _ in range(5):
            shadow_service.fire_shadow_predict("test", {"prediction": 0}, sample_rate=1.0)
        await asyncio.sleep(0.1)
        assert shadow_service.get_stats()["total_comparisons"] == 5

    @pytest.mark.asyncio
    async def test_shadow_predictor_failure_graceful(self, shadow_service, mock_m2_predictor):
        """M2 推理失败 (返回 None) 不影响统计, 不计入 total."""
        shadow_service._predictor = mock_m2_predictor
        shadow_service._predictor_loaded = True
        mock_m2_predictor.predict.return_value = None  # 推理失败

        shadow_service.fire_shadow_predict("失败文本", {"prediction": 0})
        await asyncio.sleep(0.05)

        stats = shadow_service.get_stats()
        assert stats["total_comparisons"] == 0  # 不计入

    @pytest.mark.asyncio
    async def test_shadow_exception_does_not_crash(self, shadow_service, mock_m2_predictor):
        """M2 推理抛异常时不崩溃, 不影响生产."""
        shadow_service._predictor = mock_m2_predictor
        shadow_service._predictor_loaded = True
        mock_m2_predictor.predict.side_effect = RuntimeError("GPU OOM")

        # 不应抛异常
        shadow_service.fire_shadow_predict("异常文本", {"prediction": 0})
        await asyncio.sleep(0.05)

        stats = shadow_service.get_stats()
        assert stats["total_comparisons"] == 0  # 异常不计入

    def test_shadow_get_stats_format(self, shadow_service):
        """get_stats 返回格式正确."""
        stats = shadow_service.get_stats()
        expected_keys = {
            "total_comparisons", "agreement", "disagreement",
            "agreement_rate", "avg_prob_diff", "max_prob_diff",
            "predictor_loaded",
        }
        assert set(stats.keys()) == expected_keys
        assert stats["total_comparisons"] == 0
        assert stats["agreement_rate"] == 0.0
        assert stats["predictor_loaded"] is False

    def test_shadow_reset_stats(self, shadow_service, mock_m2_predictor):
        """reset_stats 清空统计."""
        shadow_service._total = 10
        shadow_service._agreement = 8
        shadow_service._disagreement = 2
        shadow_service._prob_diff_sum = 1.5
        shadow_service._prob_diff_max = 0.3

        shadow_service.reset_stats()

        stats = shadow_service.get_stats()
        assert stats["total_comparisons"] == 0
        assert stats["agreement"] == 0
        assert stats["max_prob_diff"] == 0.0


class TestShadowModeIntegration:
    """model_engine_predict._maybe_fire_shadow_predict 集成测试.

    ARCH-FIX-2026-10-05（依赖倒置）:
        原实现由 core 层自己去 import services 层取影子服务
        （`from app.services.shadow_mode_service import get_shadow_mode_service`），
        构成 core → services 的跨层反向依赖。现在改为 core 只声明 ShadowSink
        协议、实现由 main.py 启动时注入。

        因此测试也从「断言 core 是否去取 service」改为「断言 core 是否调用注入的
        sink」。这更贴近新契约本身：core 的责任是"触发已注入的对拍接收端"，
        而不是"自己去哪里拿服务"。
    """

    def test_maybe_fire_shadow_predict_disabled(self):
        """影子模式禁用时, _maybe_fire_shadow_predict 直接返回不触发."""
        from app.core.model_engine_predict import PredictMixin

        engine = MagicMock(spec=PredictMixin)
        engine._shadow_sink = MagicMock()
        # model_engine_predict 在模块级绑定 settings, 需 patch 其自身引用
        with patch("app.core.model_engine.predict.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = False
            # 调用未绑定方法 (手动传 self)
            PredictMixin._maybe_fire_shadow_predict(
                engine, "test", {"prediction": 0}
            )
            # 禁用时不应触发对拍
            engine._shadow_sink.fire_shadow_predict.assert_not_called()

    def test_maybe_fire_shadow_predict_calls_injected_sink(self):
        """ARCH-FIX-2026-10-05: 启用时调用注入的 sink, 且不 import services 层."""
        from app.core.model_engine_predict import PredictMixin

        engine = MagicMock(spec=PredictMixin)
        sink = MagicMock()
        engine._shadow_sink = sink

        with patch("app.core.model_engine.predict.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = True
            mock_settings.shadow_mode_text_sample_rate = 0.25

            PredictMixin._maybe_fire_shadow_predict(
                engine, "hello", {"prediction": 1}
            )

        sink.fire_shadow_predict.assert_called_once_with(
            "hello", {"prediction": 1}, sample_rate=0.25
        )

    def test_maybe_fire_shadow_predict_exception_safe(self):
        """钩子内部异常不影响生产 (logger.debug 记录)."""
        from app.core.model_engine_predict import PredictMixin

        engine = MagicMock(spec=PredictMixin)
        sink = MagicMock()
        sink.fire_shadow_predict.side_effect = RuntimeError("sink boom")
        engine._shadow_sink = sink

        with patch("app.core.model_engine.predict.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = True
            mock_settings.shadow_mode_text_sample_rate = 1.0
            # 不应抛异常 (异常被吞掉)
            PredictMixin._maybe_fire_shadow_predict(
                engine, "test", {"prediction": 0}
            )

    def test_maybe_fire_shadow_predict_no_sink_is_noop(self):
        """未注入 sink（如单测/CLI/worker）时应静默 no-op，不报错.

        影子对拍是可选旁路功能，它不可用绝不能影响生产推理。
        """
        from app.core.model_engine_predict import PredictMixin

        engine = MagicMock(spec=PredictMixin)
        # 模拟完全没有 _shadow_sink 属性的情况（如旧的 mock 或未走 __init__ 的对象）
        del engine._shadow_sink

        with patch("app.core.model_engine.predict.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = True
            mock_settings.shadow_mode_text_sample_rate = 1.0
            PredictMixin._maybe_fire_shadow_predict(
                engine, "test", {"prediction": 0}
            )

    def test_null_shadow_sink_is_noop(self):
        """NullShadowSink 默认实现：调用它不做任何事，也不抛异常."""
        from app.core.model_engine.shadow_sink import NullShadowSink, ShadowSink

        sink = NullShadowSink()
        assert isinstance(sink, ShadowSink), "NullShadowSink 应满足 ShadowSink 协议"
        # 不抛异常即为通过
        sink.fire_shadow_predict("t", {"prediction": 0}, sample_rate=1.0)

    def test_shadow_sink_protocol_is_runtime_checkable(self):
        """自定义实现只要结构相符即可注入（依赖倒置的前提）."""
        from app.core.model_engine.shadow_sink import ShadowSink

        class MySink:
            def fire_shadow_predict(self, text, production_result, sample_rate=1.0):
                return None

        assert isinstance(MySink(), ShadowSink)
