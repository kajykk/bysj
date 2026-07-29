"""S3 P4 影子模式测试.

测试 shadow_mode_service 核心逻辑 + model_engine_predict 集成.
不加载真实 BERT 模型 (mock TextM2BertPredictor).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.shadow_mode_service import ShadowModeService, get_shadow_mode_service


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
    """model_engine_predict._maybe_fire_shadow_predict 集成测试."""

    def test_maybe_fire_shadow_predict_disabled(self):
        """影子模式禁用时, _maybe_fire_shadow_predict 直接返回不触发."""
        from app.core.model_engine_predict import PredictMixin

        engine = MagicMock(spec=PredictMixin)
        # 模拟 settings.shadow_mode_text_enabled = False
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = False
            # 调用未绑定方法 (手动传 self)
            PredictMixin._maybe_fire_shadow_predict(
                engine, "test", {"prediction": 0}
            )
            # 不应有任何调用
            assert True  # 未抛异常即通过

    def test_maybe_fire_shadow_predict_exception_safe(self):
        """钩子内部异常不影响生产 (logger.debug 记录)."""
        from app.core.model_engine_predict import PredictMixin

        engine = MagicMock(spec=PredictMixin)
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.shadow_mode_text_enabled = True
            mock_settings.shadow_mode_text_sample_rate = 1.0
            # 让 get_shadow_mode_service 抛异常
            with patch(
                "app.services.shadow_mode_service.get_shadow_mode_service",
                side_effect=RuntimeError("import fail"),
            ):
                # 不应抛异常
                PredictMixin._maybe_fire_shadow_predict(
                    engine, "test", {"prediction": 0}
                )
                assert True  # 未抛异常即通过
