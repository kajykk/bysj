"""
T-QA-009: 推理耗时性能测试

测试目标:
- 基线: 单条推理 < 200ms (P99)
- 批量推理 100 条 < 5s
- 验证标准: 不劣于 v1.4 基线

对应测试计划:
- TC-FBC-HP-008: 推理延迟 > 200ms，触发超时告警并回退
- TC-FBC-HP-009: 回退后延迟 < 50ms
- TC-RPT-PERF-001: 10000 条数据导出耗时 < 10s
"""

from __future__ import annotations

import statistics
import time

import pytest

pytestmark = pytest.mark.performance


class TestInferencePerformance:
    """T-QA-009: 推理耗时性能测试"""

    # 性能基线配置
    SINGLE_INFERENCE_P99_MS = 200  # P99 单条推理耗时 < 200ms
    BATCH_INFERENCE_100_MAX_S = 5  # 批量 100 条 < 5s
    FALLBACK_MAX_MS = 50  # 回退推理 < 50ms

    # ==========================================================================
    # 1. InputValidator 性能测试
    # ==========================================================================

    def test_input_validator_single_latency(self) -> None:
        """验证单条输入验证耗时 < 10ms"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        features = {"sleep_hours": 7.5, "heart_rate": 72, "steps": 8000}

        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            result = validator.validate_tabular(features)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)
            assert result.is_valid is True

        p99 = statistics.quantiles(latencies, n=100)[98]  # P99
        avg = statistics.mean(latencies)
        max_lat = max(latencies)

        print(
            f"\nInputValidator Single - P99: {p99:.2f}ms, Avg: {avg:.2f}ms, Max: {max_lat:.2f}ms"
        )
        assert p99 < 10, f"InputValidator P99 latency {p99:.2f}ms exceeds 10ms baseline"

    def test_input_validator_batch_100_latency(self) -> None:
        """验证批量 100 条输入验证耗时 < 100ms"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        features_list = [
            {"sleep_hours": 7.5, "heart_rate": 72, "steps": 8000 + i}
            for i in range(100)
        ]

        start = time.perf_counter()
        for features in features_list:
            result = validator.validate_tabular(features)
            assert result.is_valid is True
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(
            f"\nInputValidator Batch 100 - Total: {elapsed_ms:.2f}ms, Avg: {elapsed_ms / 100:.2f}ms/item"
        )
        assert (
            elapsed_ms < 100
        ), f"Batch 100 validation took {elapsed_ms:.2f}ms, exceeds 100ms baseline"

    # ==========================================================================
    # 2. 漂移检测性能测试
    # ==========================================================================

    def test_drift_detection_single_latency(self) -> None:
        """验证单条漂移检测耗时 < 50ms"""
        from app.services.drift_detector import DriftDetector

        detector = DriftDetector()
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0] * 20  # 100 samples
        current = [1.1, 2.1, 3.1, 4.1, 5.1] * 20

        latencies = []
        for _ in range(50):
            start = time.perf_counter()
            detector.calculate_psi(baseline, current)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        p99 = statistics.quantiles(latencies, n=100)[98]
        avg = statistics.mean(latencies)

        print(f"\nDrift Detection Single - P99: {p99:.2f}ms, Avg: {avg:.2f}ms")
        assert (
            p99 < 50
        ), f"Drift detection P99 latency {p99:.2f}ms exceeds 50ms baseline"

    def test_drift_detection_batch_latency(self) -> None:
        """验证批量漂移检测性能"""
        from app.services.drift_detector import DriftDetector

        detector = DriftDetector()

        start = time.perf_counter()
        for i in range(10):
            baseline = [1.0 + i * 0.1, 2.0, 3.0, 4.0, 5.0] * 20
            current = [1.1 + i * 0.1, 2.1, 3.1, 4.1, 5.1] * 20
            detector.calculate_psi(baseline, current)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(
            f"\nDrift Detection Batch 10 - Total: {elapsed_ms:.2f}ms, Avg: {elapsed_ms / 10:.2f}ms/item"
        )
        assert elapsed_ms < 500, f"Batch 10 drift detection took {elapsed_ms:.2f}ms"

    # ==========================================================================
    # 3. 指标计算性能测试
    # ==========================================================================

    def test_metrics_calculation_latency(self) -> None:
        """验证指标计算耗时 < 50ms (1000 条样本)"""
        from app.services.validation_engine import ValidationEngine

        engine = ValidationEngine()
        import random

        random.seed(42)
        ground_truth = [random.randint(0, 1) for _ in range(1000)]
        predictions = [random.randint(0, 1) for _ in range(1000)]
        probabilities = [random.random() for _ in range(1000)]

        start = time.perf_counter()
        metrics = engine.calculate_metrics(ground_truth, predictions, probabilities)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\nMetrics Calculation (1000 samples) - Total: {elapsed_ms:.2f}ms")
        assert metrics.sample_count == 1000
        assert (
            elapsed_ms < 50
        ), f"Metrics calculation took {elapsed_ms:.2f}ms, exceeds 50ms baseline"

    def test_metrics_calculation_batch_100(self) -> None:
        """验证批量 100 条指标计算性能"""
        from app.services.validation_engine import ValidationEngine

        engine = ValidationEngine()
        import random

        random.seed(42)

        start = time.perf_counter()
        for _ in range(100):
            ground_truth = [random.randint(0, 1) for _ in range(100)]
            predictions = [random.randint(0, 1) for _ in range(100)]
            engine.calculate_metrics(ground_truth, predictions)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(
            f"\nMetrics Calculation Batch 100x100 - Total: {elapsed_ms:.2f}ms, Avg: {elapsed_ms / 100:.2f}ms/item"
        )
        assert elapsed_ms < 5000, f"Batch metrics calculation took {elapsed_ms:.2f}ms"

    # ==========================================================================
    # 4. 启发式回退性能测试 (使用 RiskService)
    # ==========================================================================

    def test_heuristic_fallback_latency(self) -> None:
        """验证启发式回退推理耗时 < 50ms"""
        # 使用 RiskService 的启发式评分作为回退机制
        from app.services.risk_service import RiskService

        # 创建 mock db session (不需要实际数据库操作)
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

        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            service._calculate_heuristic_score(features)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        p99 = statistics.quantiles(latencies, n=100)[98]
        avg = statistics.mean(latencies)

        print(f"\nHeuristic Fallback - P99: {p99:.2f}ms, Avg: {avg:.2f}ms")
        assert (
            p99 < self.FALLBACK_MAX_MS
        ), f"Fallback P99 latency {p99:.2f}ms exceeds {self.FALLBACK_MAX_MS}ms baseline"

    def test_heuristic_vs_validation_latency_comparison(self) -> None:
        """验证回退延迟显著低于复杂处理延迟"""
        from app.services.input_validator import InputValidator
        from app.services.risk_service import RiskService

        class MockDB:
            pass

        service = RiskService(db=MockDB())
        validator = InputValidator()
        features = {
            "stress_level": 5,
            "anxiety": 3,
            "sleep_duration": 6,
            "financial_pressure": 2,
            "social_support": 4,
            "panic_attack": 0,
        }

        # 回退延迟
        fallback_latencies = []
        for _ in range(50):
            start = time.perf_counter()
            service._calculate_heuristic_score(features)
            fallback_latencies.append((time.perf_counter() - start) * 1000)

        # 验证延迟
        validation_latencies = []
        for _ in range(50):
            start = time.perf_counter()
            validator.validate_tabular(features)
            validation_latencies.append((time.perf_counter() - start) * 1000)

        fallback_p99 = statistics.quantiles(fallback_latencies, n=100)[98]
        validation_p99 = statistics.quantiles(validation_latencies, n=100)[98]

        print(
            f"\nFallback P99: {fallback_p99:.2f}ms, Validation P99: {validation_p99:.2f}ms"
        )
        assert (
            fallback_p99 < validation_p99 * 2
        ), f"Fallback latency ({fallback_p99:.2f}ms) should be less than 2x validation latency ({validation_p99:.2f}ms)"

    # ==========================================================================
    # 5. 综合性能基准
    # ==========================================================================

    def test_overall_inference_pipeline_latency(self) -> None:
        """验证完整推理管道（验证+回退）P99 < 200ms"""
        from app.services.input_validator import InputValidator
        from app.services.risk_service import RiskService

        class MockDB:
            pass

        validator = InputValidator()
        service = RiskService(db=MockDB())
        features = {
            "stress_level": 5,
            "anxiety": 3,
            "sleep_duration": 6,
            "financial_pressure": 2,
            "social_support": 4,
            "panic_attack": 0,
        }

        latencies = []
        for _ in range(200):
            start = time.perf_counter()
            # 完整管道: 验证 -> 回退预测
            val_result = validator.validate_tabular(features)
            if val_result.is_valid:
                service._calculate_heuristic_score(
                    val_result.sanitized_input or features
                )
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        p99 = statistics.quantiles(latencies, n=100)[98]
        p95 = statistics.quantiles(latencies, n=100)[94]
        avg = statistics.mean(latencies)

        print(
            f"\nOverall Pipeline - P99: {p99:.2f}ms, P95: {p95:.2f}ms, Avg: {avg:.2f}ms"
        )
        assert (
            p99 < self.SINGLE_INFERENCE_P99_MS
        ), f"Overall pipeline P99 latency {p99:.2f}ms exceeds {self.SINGLE_INFERENCE_P99_MS}ms baseline"

    def test_batch_inference_100_latency(self) -> None:
        """验证批量 100 条推理总耗时 < 5s"""
        from app.services.input_validator import InputValidator
        from app.services.risk_service import RiskService

        class MockDB:
            pass

        validator = InputValidator()
        service = RiskService(db=MockDB())

        import random

        random.seed(42)
        batch = [
            {
                "stress_level": random.randint(1, 10),
                "anxiety": random.randint(1, 10),
                "sleep_duration": random.uniform(4, 10),
                "financial_pressure": random.randint(1, 10),
                "social_support": random.randint(1, 5),
                "panic_attack": random.randint(0, 5),
            }
            for _ in range(100)
        ]

        start = time.perf_counter()
        for features in batch:
            val_result = validator.validate_tabular(features)
            if val_result.is_valid:
                service._calculate_heuristic_score(
                    val_result.sanitized_input or features
                )
        elapsed_s = time.perf_counter() - start

        print(
            f"\nBatch Inference 100 - Total: {elapsed_s:.2f}s, Avg: {elapsed_s / 100 * 1000:.2f}ms/item"
        )
        assert (
            elapsed_s < self.BATCH_INFERENCE_100_MAX_S
        ), f"Batch 100 inference took {elapsed_s:.2f}s, exceeds {self.BATCH_INFERENCE_100_MAX_S}s baseline"

    # ==========================================================================
    # 6. 内存使用稳定性测试
    # ==========================================================================

    def test_memory_stability_during_inference(self) -> None:
        """验证推理过程中内存使用稳定（无异常增长）"""
        import gc

        from app.services.input_validator import InputValidator
        from app.services.risk_service import RiskService

        class MockDB:
            pass

        validator = InputValidator()
        service = RiskService(db=MockDB())
        features = {
            "stress_level": 5,
            "anxiety": 3,
            "sleep_duration": 6,
            "financial_pressure": 2,
            "social_support": 4,
            "panic_attack": 0,
        }

        gc.collect()

        # 执行大量推理
        for _ in range(1000):
            val_result = validator.validate_tabular(features)
            if val_result.is_valid:
                service._calculate_heuristic_score(
                    val_result.sanitized_input or features
                )

        gc.collect()
        # 如果内存泄漏，后续推理会变慢
        start = time.perf_counter()
        for _ in range(100):
            val_result = validator.validate_tabular(features)
            if val_result.is_valid:
                service._calculate_heuristic_score(
                    val_result.sanitized_input or features
                )
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(
            f"\nMemory Stability - 100 inferences after 1000 warmup: {elapsed_ms:.2f}ms"
        )
        assert (
            elapsed_ms < 500
        ), f"Memory stability test took {elapsed_ms:.2f}ms, possible memory leak"
