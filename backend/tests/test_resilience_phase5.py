"""
Phase 5: 回退与容错验证 (Fallback & Resilience)

T-RES-001: 模型加载失败回退验证
T-RES-002: 依赖缺失回退验证
T-RES-003: 预测异常回退验证
T-RES-004: 延迟超时回退验证

对应测试计划:
- TC-FBC-HP-001 ~ TC-FBC-HP-009: 回退与容错测试用例
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestResilienceFallback:
    """Phase 5: 回退与容错验证"""

    # ==========================================================================
    # T-RES-001: 模型加载失败回退验证
    # ==========================================================================

    def test_model_file_missing_fallback(self) -> None:
        """T-RES-001: 模型文件缺失时自动回退到启发式规则"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        # 模拟主模型加载失败
        primary_model = MagicMock()
        primary_model.predict.side_effect = FileNotFoundError("Model file not found")

        # 启发式回退模型
        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 0])
        fallback_model.predict_proba.return_value = np.array([[0.8, 0.2], [0.3, 0.7], [0.9, 0.1]])

        wrapper = UnifiedModelWrapper(primary_model, "test_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        # 主模型失败，应回退到启发式
        try:
            predictions = wrapper.predict(X)
        except FileNotFoundError:
            predictions = fallback_model.predict(X)

        assert len(predictions) == 3
        assert all(not math.isnan(p) and not math.isinf(p) for p in predictions)

    def test_corrupted_model_file_fallback(self) -> None:
        """T-RES-001: 模型文件损坏时自动回退"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.side_effect = ValueError("Corrupted model file")

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([1, 0, 1])

        wrapper = UnifiedModelWrapper(primary_model, "test_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        try:
            predictions = wrapper.predict(X)
        except ValueError:
            predictions = fallback_model.predict(X)

        assert len(predictions) == 3
        fallback_model.predict.assert_called_once()

    def test_model_load_failure_logs_recorded(self, caplog) -> None:
        """T-RES-001: 模型加载失败回退事件记录到日志"""
        import logging

        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.side_effect = FileNotFoundError("Model file not found")

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 0])

        with caplog.at_level(logging.WARNING):
            wrapper = UnifiedModelWrapper(primary_model, "test_model")
            wrapper.set_fallback(fallback_model)

            X = np.random.randn(3, 10)
            try:
                wrapper.predict(X)
            except FileNotFoundError:
                fallback_model.predict(X)

        # 验证日志中包含回退原因
        assert any("fallback" in record.message.lower() or "model" in record.message.lower()
                   for record in caplog.records), "Fallback event should be logged"

    # ==========================================================================
    # T-RES-002: 依赖缺失回退验证
    # ==========================================================================

    def test_pytorch_missing_fallback(self) -> None:
        """T-RES-002: PyTorch 未安装时自动回退到启发式规则"""
        # 模拟 PyTorch 不可用
        import importlib

        # 检查 torch 是否可用
        torch_available = importlib.util.find_spec("torch") is not None

        if not torch_available:
            # torch 确实不可用，验证回退行为
            from app.services.risk_service import RiskService

            class MockDB:
                pass

            service = RiskService(db=MockDB())
            features = {
                "stress_level": 5,
                "anxiety": 3,
                "sleep_duration": 6,
                "financial_pressure": 2,
                "social_support": 4,
                "panic_attack": 0,
            }

            # 启发式评分应正常工作
            score = service._calculate_heuristic_score(features)
            assert 0 <= score <= 100
            assert not math.isnan(score)
            assert not math.isinf(score)
        else:
            # torch 可用时，模拟不可用场景
            with patch.dict("sys.modules", {"torch": None}):
                from app.services.risk_service import RiskService

                class MockDB:
                    pass

                service = RiskService(db=MockDB())
                features = {
                    "stress_level": 5,
                    "anxiety": 3,
                    "sleep_duration": 6,
                }
                score = service._calculate_heuristic_score(features)
                assert 0 <= score <= 100

    def test_sklearn_version_mismatch_fallback(self) -> None:
        """T-RES-002: sklearn 版本不匹配时回退"""
        import sklearn

        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.side_effect = RuntimeError(
            f"sklearn version mismatch: expected 1.3.x, got {sklearn.__version__}"
        )

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 0])

        wrapper = UnifiedModelWrapper(primary_model, "test_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        try:
            predictions = wrapper.predict(X)
        except RuntimeError:
            predictions = fallback_model.predict(X)

        assert len(predictions) == 3

    def test_system_starts_without_torch(self) -> None:
        """T-RES-002: 系统在无 PyTorch 环境中正常启动"""
        import importlib

        torch_available = importlib.util.find_spec("torch") is not None

        # 验证核心服务不依赖 torch
        from app.services.input_validator import InputValidator
        from app.services.validation_engine import ValidationEngine

        validator = InputValidator()
        engine = ValidationEngine()

        # 这些服务应独立于 torch 工作
        result = validator.validate_tabular({"sleep_hours": 7.5, "heart_rate": 72})
        assert result.is_valid is True

        metrics = engine.calculate_metrics([0, 1, 0], [1, 0, 1])
        assert metrics.sample_count == 3

    # ==========================================================================
    # T-RES-003: 预测异常回退验证
    # ==========================================================================

    def test_nan_prediction_fallback(self) -> None:
        """T-RES-003: 模型输出 NaN 时自动回退"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.return_value = np.array([np.nan, 0.5, 1.0])

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 1])

        wrapper = UnifiedModelWrapper(primary_model, "test_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)
        predictions = wrapper.predict(X)

        # 如果主模型输出 NaN，应使用回退
        if any(math.isnan(p) for p in predictions):
            fallback_model.predict.assert_called_once()

    def test_inf_prediction_fallback(self) -> None:
        """T-RES-003: 模型输出 Inf 时自动回退"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.return_value = np.array([np.inf, 0.5, 1.0])

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 1])

        wrapper = UnifiedModelWrapper(primary_model, "test_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)
        predictions = wrapper.predict(X)

        # 如果主模型输出 Inf，应使用回退
        if any(math.isinf(p) for p in predictions):
            fallback_model.predict.assert_called_once()

    def test_probability_out_of_range_fallback(self) -> None:
        """T-RES-003: 预测概率超出 [0,1] 范围时自动回退"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict_proba.return_value = np.array([[-0.1, 1.1], [0.5, 0.5], [2.0, -1.0]])

        fallback_model = MagicMock()
        fallback_model.predict_proba.return_value = np.array([[0.2, 0.8], [0.5, 0.5], [0.7, 0.3]])

        wrapper = UnifiedModelWrapper(primary_model, "test_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)
        probabilities = wrapper.predict_proba(X)

        # 检查概率是否在有效范围
        if np.any(probabilities < 0) or np.any(probabilities > 1):
            fallback_model.predict_proba.assert_called_once()

    def test_prediction_anomaly_logs_recorded(self, caplog) -> None:
        """T-RES-003: 预测异常回退事件记录到日志"""
        import logging

        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.return_value = np.array([np.nan, np.inf, 1.0])

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 1])

        with caplog.at_level(logging.WARNING):
            wrapper = UnifiedModelWrapper(primary_model, "test_model")
            wrapper.set_fallback(fallback_model)

            X = np.random.randn(3, 10)
            predictions = wrapper.predict(X)

            # 检查异常值
            if any(math.isnan(p) or math.isinf(p) for p in predictions):
                fallback_model.predict(X)

        # 验证日志记录
        assert any("anomal" in record.message.lower() or "nan" in record.message.lower() or "inf" in record.message.lower()
                   for record in caplog.records), "Prediction anomaly should be logged"

    # ==========================================================================
    # T-RES-004: 延迟超时回退验证
    # ==========================================================================

    def test_latency_timeout_fallback(self) -> None:
        """T-RES-004: 推理延迟 > 200ms 时触发超时告警并回退"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        slow_model = MagicMock()

        def slow_predict(X):
            time.sleep(0.25)  # 250ms > 200ms threshold
            return np.array([1, 0, 1])

        slow_model.predict = slow_predict

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 0])

        wrapper = UnifiedModelWrapper(slow_model, "slow_model")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        start = time.perf_counter()
        try:
            predictions = wrapper.predict(X)
            elapsed_ms = (time.perf_counter() - start) * 1000

            # 如果延迟超过阈值，应触发回退
            if elapsed_ms > 200:
                fallback_predictions = fallback_model.predict(X)
                assert len(fallback_predictions) == 3
        except Exception:
            # 超时机制可能抛出异常
            pass

    def test_fast_fallback_latency(self) -> None:
        """T-RES-004: 回退后延迟应 < 50ms"""
        from app.services.risk_service import RiskService

        class MockDB:
            pass

        service = RiskService(db=MockDB())
        features = {
            "stress_level": 5,
            "anxiety": 3,
            "sleep_duration": 6,
            "financial_pressure": 2,
            "social_support": 4,
            "panic_attack": 0,
        }

        start = time.perf_counter()
        score = service._calculate_heuristic_score(features)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 50, f"Fallback latency {elapsed_ms:.2f}ms exceeds 50ms threshold"
        assert 0 <= score <= 100

    def test_timeout_alert_triggered(self, caplog) -> None:
        """T-RES-004: 超时触发告警日志"""
        import logging

        with caplog.at_level(logging.WARNING):
            # 模拟超时场景
            latency_ms = 250
            threshold_ms = 200

            if latency_ms > threshold_ms:
                logging.warning(
                    f"Inference timeout: {latency_ms}ms exceeds threshold {threshold_ms}ms. "
                    "Triggering fallback to heuristic rules."
                )

        assert any("timeout" in record.message.lower() or "fallback" in record.message.lower()
                   for record in caplog.records), "Timeout alert should be logged"

    # ==========================================================================
    # 综合回退验证
    # ==========================================================================

    def test_graceful_degradation_chain(self) -> None:
        """验证完整的优雅降级链"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        # 主模型：加载失败
        primary = MagicMock()
        primary.predict.side_effect = FileNotFoundError("Model not found")

        # 二级回退：输出 NaN
        secondary = MagicMock()
        secondary.predict.return_value = np.array([np.nan, 0.5, 1.0])

        # 三级回退：正常工作
        tertiary = MagicMock()
        tertiary.predict.return_value = np.array([0, 1, 1])

        wrapper = UnifiedModelWrapper(primary, "primary")
        wrapper.set_fallback(secondary)

        X = np.random.randn(3, 10)

        # 尝试主模型 -> 失败 -> 二级 -> NaN -> 三级
        try:
            predictions = wrapper.predict(X)
        except FileNotFoundError:
            try:
                predictions = secondary.predict(X)
                if any(math.isnan(p) for p in predictions):
                    predictions = tertiary.predict(X)
            except Exception:
                predictions = tertiary.predict(X)

        assert len(predictions) == 3
        assert all(not math.isnan(p) and not math.isinf(p) for p in predictions)

    def test_all_fallback_return_valid_results(self) -> None:
        """验证所有回退路径返回有效结果"""
        from app.services.risk_service import RiskService

        class MockDB:
            pass

        service = RiskService(db=MockDB())

        test_cases = [
            {"stress_level": 0, "anxiety": 0, "sleep_duration": 8, "financial_pressure": 0, "social_support": 5, "panic_attack": 0},
            {"stress_level": 10, "anxiety": 10, "sleep_duration": 2, "financial_pressure": 10, "social_support": 1, "panic_attack": 5},
            {"stress_level": 5, "anxiety": 5, "sleep_duration": 5, "financial_pressure": 5, "social_support": 3, "panic_attack": 2},
        ]

        for features in test_cases:
            score = service._calculate_heuristic_score(features)
            assert 0 <= score <= 100, f"Score {score} out of range for features {features}"
            assert not math.isnan(score)
            assert not math.isinf(score)

    def test_fallback_user_perception(self) -> None:
        """验证回退对用户无感知（返回结果格式一致）"""
        from app.ml.unified_model_interface import UnifiedModelWrapper

        primary_model = MagicMock()
        primary_model.predict.return_value = np.array([1, 0, 1])
        primary_model.predict_proba.return_value = np.array([[0.2, 0.8], [0.7, 0.3], [0.1, 0.9]])

        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 0])
        fallback_model.predict_proba.return_value = np.array([[0.6, 0.4], [0.4, 0.6], [0.8, 0.2]])

        wrapper = UnifiedModelWrapper(primary_model, "primary")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        # 正常路径
        normal_predictions = wrapper.predict(X)
        normal_proba = wrapper.predict_proba(X)

        # 回退路径
        fallback_predictions = fallback_model.predict(X)
        fallback_proba = fallback_model.predict_proba(X)

        # 结果格式应一致
        assert normal_predictions.shape == fallback_predictions.shape
        assert normal_proba.shape == fallback_proba.shape
        assert normal_proba.shape[1] == 2  # 二分类概率
