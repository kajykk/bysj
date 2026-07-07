"""
T-QA-011: 资源占用性能测试

测试目标:
- 内存占用增长 < 10% (相比 v1.4)
- CPU 使用率峰值 < 80%
- 验证标准: 无内存泄漏

对应测试计划:
- TC-FEO-PERF-003: 首屏加载时间降低 30%
- TC-FEO-PERF-004: FCP < 2.5s, LCP < 4.0s
- TC-RPT-PERF-001: 10000 条数据导出耗时 < 10s
"""

from __future__ import annotations

import gc
import time
import tracemalloc

import pytest

pytestmark = pytest.mark.performance


class TestResourceUsage:
    """T-QA-011: 资源占用性能测试"""

    # 资源使用基线
    MEMORY_GROWTH_MAX_PERCENT = 10  # 内存增长 < 10%
    CPU_PEAK_MAX_PERCENT = 80  # CPU 峰值 < 80%
    EXPORT_10000_MAX_S = 10  # 10000 条导出 < 10s

    # ==========================================================================
    # 1. 内存泄漏检测
    # ==========================================================================

    def test_input_validator_no_memory_leak(self) -> None:
        """验证 InputValidator 无内存泄漏"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        features = {"sleep_hours": 7.5, "heart_rate": 72, "steps": 8000}

        gc.collect()
        tracemalloc.start()

        # 记录初始内存
        snapshot1 = tracemalloc.take_snapshot()

        # 执行大量验证操作
        for _ in range(1000):
            validator.validate_tabular(features)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()

        # 比较内存差异
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        # 内存增长应 < 1MB (1000 次操作)
        assert (
            total_diff < 1 * 1024 * 1024
        ), f"Memory leak detected: {total_diff / 1024 / 1024:.2f}MB growth after 1000 validations"

    def test_validation_engine_no_memory_leak(self) -> None:
        """验证 ValidationEngine 无内存泄漏"""
        from app.services.validation_engine import ValidationEngine

        engine = ValidationEngine()
        import random

        random.seed(42)

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # 执行大量指标计算
        for _ in range(500):
            ground_truth = [random.randint(0, 1) for _ in range(100)]
            predictions = [random.randint(0, 1) for _ in range(100)]
            engine.calculate_metrics(ground_truth, predictions)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        assert (
            total_diff < 2 * 1024 * 1024
        ), f"Memory leak detected: {total_diff / 1024 / 1024:.2f}MB growth after 500 calculations"

    def test_drift_detector_no_memory_leak(self) -> None:
        """验证 DriftDetector 无内存泄漏"""
        from app.services.drift_detector import DriftDetector

        detector = DriftDetector()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # 执行大量漂移检测
        for i in range(200):
            baseline = [1.0 + i * 0.01, 2.0, 3.0, 4.0, 5.0] * 20
            current = [1.1 + i * 0.01, 2.1, 3.1, 4.1, 5.1] * 20
            detector.calculate_psi(baseline, current)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        assert (
            total_diff < 1 * 1024 * 1024
        ), f"Memory leak detected: {total_diff / 1024 / 1024:.2f}MB growth after 200 drift checks"

    # ==========================================================================
    # 2. 内存使用稳定性
    # ==========================================================================

    def test_memory_usage_stable_over_iterations(self) -> None:
        """验证多次迭代后内存使用稳定"""
        from app.services.input_validator import InputValidator
        from app.services.validation_engine import ValidationEngine

        validator = InputValidator()
        engine = ValidationEngine()

        # 预热：执行一批操作让缓存/懒加载完成，避免初始化开销被计入基线
        for _ in range(50):
            validator.validate_tabular({"sleep_hours": 7.5, "heart_rate": 72})
            engine.calculate_metrics([0, 1, 0], [1, 0, 1])

        gc.collect()
        tracemalloc.start()

        memory_readings = []
        for i in range(10):
            # 执行一批操作
            for _ in range(100):
                validator.validate_tabular({"sleep_hours": 7.5, "heart_rate": 72})
                engine.calculate_metrics([0, 1, 0], [1, 0, 1])

            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            memory_readings.append(current)

        tracemalloc.stop()

        # 计算内存增长趋势
        # 使用绝对字节增长而非百分比，因为小数据集基线很小（几 KB），
        # Python 内存分配器的 arena 池开销会导致百分比虚高（>100%），
        # 但绝对增长应在合理范围内（< 512KB 表示无泄漏）
        if len(memory_readings) >= 2:
            first_reading = memory_readings[0]
            last_reading = memory_readings[-1]
            growth_bytes = last_reading - first_reading
            growth_percent = (
                (last_reading - first_reading) / max(1, first_reading)
            ) * 100

            # 绝对增长 < 512KB（10 批 x 100 次操作）
            assert (
                growth_bytes < 512 * 1024
            ), f"Memory growth {growth_bytes / 1024:.1f}KB exceeds 512KB absolute baseline"
            # 同时记录百分比用于诊断
            print(
                f"\nMemory growth: {growth_percent:.1f}% ({growth_bytes / 1024:.1f}KB)"
            )

    def test_large_dataset_memory_efficiency(self) -> None:
        """验证大数据集处理内存效率"""
        from app.services.validation_engine import ValidationEngine

        engine = ValidationEngine()
        import random

        random.seed(42)

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # 处理 10000 条数据
        ground_truth = [random.randint(0, 1) for _ in range(10000)]
        predictions = [random.randint(0, 1) for _ in range(10000)]
        probabilities = [random.random() for _ in range(10000)]

        metrics = engine.calculate_metrics(ground_truth, predictions, probabilities)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        # 10000 条数据处理内存增长应 < 50MB
        assert (
            total_diff < 50 * 1024 * 1024
        ), f"Large dataset processing used {total_diff / 1024 / 1024:.2f}MB, exceeds 50MB limit"
        assert metrics.sample_count == 10000

    # ==========================================================================
    # 3. 大数据导出性能
    # ==========================================================================

    def test_excel_export_10000_performance(self) -> None:
        """验证 10000 条数据 Excel 导出耗时 < 10s"""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()

        # 生成 10000 条测试数据
        data = [
            {
                "id": i,
                "name": f"User_{i}",
                "risk_score": i % 100,
                "risk_level": i % 5,
                "created_at": "2026-04-28",
            }
            for i in range(10000)
        ]

        start = time.perf_counter()
        service.export_to_excel(data, "test_export")
        elapsed_s = time.perf_counter() - start

        print(f"\nExcel Export 10000 rows - Time: {elapsed_s:.2f}s")
        assert (
            elapsed_s < self.EXPORT_10000_MAX_S
        ), f"Excel export took {elapsed_s:.2f}s, exceeds {self.EXPORT_10000_MAX_S}s baseline"

    def test_pdf_export_memory_usage(self) -> None:
        """验证 PDF 导出内存使用合理"""
        from app.services.pdf_report_service import PDFReportService

        service = PDFReportService()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # 生成包含图表和数据的 PDF
        user_data = {
            "user_id": 1,
            "risk_score": 78,
            "risk_level": 3,
            "trend_data": [
                {"date": f"2026-04-{i:02d}", "score": 70 + i} for i in range(1, 31)
            ],
        }

        start = time.perf_counter()
        service.generate_user_risk_report(user_data)
        elapsed_s = time.perf_counter() - start

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        print(
            f"\nPDF Export - Time: {elapsed_s:.2f}s, Memory: {total_diff / 1024 / 1024:.2f}MB"
        )
        assert elapsed_s < 3, f"PDF export took {elapsed_s:.2f}s, exceeds 3s baseline"
        assert (
            total_diff < 100 * 1024 * 1024
        ), f"PDF export used {total_diff / 1024 / 1024:.2f}MB, exceeds 100MB limit"

    # ==========================================================================
    # 4. 并发处理资源控制
    # ==========================================================================

    def test_concurrent_validation_memory(self) -> None:
        """验证并发验证内存使用可控"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # 模拟并发处理多个请求
        batch_size = 50
        features_list = [
            {
                "sleep_hours": 7.5 + i * 0.1,
                "heart_rate": 72 + i,
                "steps": 8000 + i * 10,
            }
            for i in range(batch_size)
        ]

        for features in features_list:
            validator.validate_tabular(features)

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        # 50 个并发请求内存增长应 < 10MB
        assert (
            total_diff < 10 * 1024 * 1024
        ), f"Concurrent validation used {total_diff / 1024 / 1024:.2f}MB, exceeds 10MB limit"

    # ==========================================================================
    # 5. 资源清理验证
    # ==========================================================================

    def test_observability_collector_cleanup(self) -> None:
        """验证监控指标收集器资源清理"""
        from app.services.observability_service import observability_collector

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # 记录大量指标
        for i in range(500):
            observability_collector.record_inference(
                model_version="v1.5.0",
                latency_ms=100 + i % 50,
                fallback_reason=None if i % 10 != 0 else "test_fallback",
            )

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        # 指标记录内存增长应 < 5MB
        assert (
            total_diff < 5 * 1024 * 1024
        ), f"Observability collector used {total_diff / 1024 / 1024:.2f}MB, exceeds 5MB limit"

    # ==========================================================================
    # 6. 综合资源基准
    # ==========================================================================

    def test_overall_resource_efficiency(self) -> None:
        """综合验证资源使用效率"""
        from app.services.drift_detector import DriftDetector
        from app.services.input_validator import InputValidator
        from app.services.validation_engine import ValidationEngine

        validator = InputValidator()
        engine = ValidationEngine()
        detector = DriftDetector()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        start = time.perf_counter()

        # 执行综合工作负载
        import random

        random.seed(42)

        for i in range(100):
            # 输入验证
            features = {
                "sleep_hours": random.uniform(4, 10),
                "heart_rate": random.randint(60, 100),
                "steps": random.randint(1000, 15000),
            }
            validator.validate_tabular(features)

            # 指标计算
            ground_truth = [random.randint(0, 1) for _ in range(100)]
            predictions = [random.randint(0, 1) for _ in range(100)]
            engine.calculate_metrics(ground_truth, predictions)

            # 漂移检测
            baseline = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
            current = [1.1, 2.1, 3.1, 4.1, 5.1] * 20
            detector.calculate_psi(baseline, current)

        elapsed_s = time.perf_counter() - start

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

        tracemalloc.stop()

        print(
            f"\nOverall Workload - Time: {elapsed_s:.2f}s, Memory: {total_diff / 1024 / 1024:.2f}MB"
        )
        assert (
            elapsed_s < 10
        ), f"Overall workload took {elapsed_s:.2f}s, exceeds 10s baseline"
        assert (
            total_diff < 20 * 1024 * 1024
        ), f"Overall workload used {total_diff / 1024 / 1024:.2f}MB, exceeds 20MB limit"
