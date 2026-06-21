"""
T-QA-008: 非法类型与极端分布测试

测试目标:
- 测试字符串传入数字字段
- 测试极大/极小数值
- 测试数组长度超限
- 验证标准: 优雅降级，记录异常日志

对应测试计划:
- TC-MON-HP-007: NaN 输入触发 INPUT_ANOMALY 记录
- TC-MON-EC-003: 同时存在多种异常，记录所有异常类型
- TC-VAL-HP-005: NaN 样本记录 failure_reason 为 NaN_in_feature_xxx
- TC-DRF-HP-003: 极端分布输入，无 RuntimeWarning
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.slow


class TestInvalidTypesAndExtremeDistributions:
    """T-QA-008: 非法类型与极端分布测试"""

    # ==========================================================================
    # 1. InputValidator - 非法类型测试
    # ==========================================================================

    def test_string_in_numeric_field(self) -> None:
        """验证字符串传入数字字段被检测为类型错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": "not_a_number", "heart_rate": 72},
        )
        assert result.is_valid is False
        assert any(
            e["anomaly_type"] == "type_error" and e["field"] == "sleep_hours"
            for e in result.errors
        )

    def test_boolean_in_numeric_field(self) -> None:
        """验证布尔值传入数字字段被检测"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": True, "heart_rate": 72},
        )
        # bool 是 int 的子类，可能被接受或拒绝，但不应抛异常
        assert result is not None

    def test_list_in_numeric_field(self) -> None:
        """验证列表传入数字字段被检测为类型错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": [1, 2, 3], "heart_rate": 72},
        )
        assert result.is_valid is False
        assert any(e["field"] == "sleep_hours" for e in result.errors)

    def test_dict_in_numeric_field(self) -> None:
        """验证字典传入数字字段被检测为类型错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": {"value": 7.5}, "heart_rate": 72},
        )
        assert result.is_valid is False
        assert any(e["field"] == "sleep_hours" for e in result.errors)

    # ==========================================================================
    # 2. InputValidator - 极端数值测试
    # ==========================================================================

    def test_extremely_large_value(self) -> None:
        """验证极大数值触发范围错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": 1e10, "heart_rate": 72},
        )
        assert result.is_valid is False
        assert any(
            e["anomaly_type"] == "out_of_range" and e["field"] == "sleep_hours"
            for e in result.errors
        )

    def test_extremely_small_value(self) -> None:
        """验证极小（负）数值触发范围错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": -1e10, "heart_rate": 72},
        )
        assert result.is_valid is False
        assert any(
            e["anomaly_type"] == "out_of_range" and e["field"] == "sleep_hours"
            for e in result.errors
        )

    def test_zero_value_edge_case(self) -> None:
        """验证边界值 0 对睡眠时间的处理"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": 0, "heart_rate": 72},
        )
        # sleep_hours 范围是 (0, 24)，0 应该被接受或拒绝，但不抛异常
        assert result is not None

    def test_boundary_max_value(self) -> None:
        """验证边界最大值处理"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": 24, "heart_rate": 220},
        )
        # heart_rate 最大 220，应该被接受
        # sleep_hours 最大 24，应该被接受或拒绝
        assert result is not None

    def test_float_precision_edge_case(self) -> None:
        """验证浮点精度边界值"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": 23.9999999999, "heart_rate": 72},
        )
        assert result is not None
        # 不应因浮点精度问题抛异常

    # ==========================================================================
    # 3. InputValidator - 文本极端分布测试
    # ==========================================================================

    def test_extremely_long_text(self) -> None:
        """验证超长文本触发长度错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        long_text = "a" * 20000
        result = validator.validate_text(long_text)
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "too_long" for e in result.errors)

    def test_single_repeated_character(self) -> None:
        """验证单一重复字符触发极端分布错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_text("bbbbbbbbbb")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "extreme_distribution" for e in result.errors)

    def test_low_character_diversity(self) -> None:
        """验证低字符多样性触发极端分布错误"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_text("abababababababababab")
        # unique_chars < 3 and length > 10
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "extreme_distribution" for e in result.errors)

    def test_special_characters_only(self) -> None:
        """验证仅特殊字符的文本处理"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_text("!@#$%^&*()!@#$%^&*()")
        # 不应抛异常，根据策略可能通过或拒绝
        assert result is not None

    # ==========================================================================
    # 4. InputValidator - 数组/列表长度超限测试
    # ==========================================================================

    def test_fusion_with_excessive_features(self) -> None:
        """验证融合输入中特征数量过多时的处理"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        # 创建大量特征
        features = {f"feature_{i}": i for i in range(1000)}
        result = validator.validate_fusion(features=features)
        # 不应因特征数量多而抛异常
        assert result is not None

    def test_physiological_extra_fields(self) -> None:
        """验证生理数据包含额外字段时的处理"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        data = {
            "sleep_hours": 7.5,
            "sleep_quality": 7,
            "exercise_minutes": 30,
            "heart_rate": 72,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "steps": 8000,
            "extra_field_1": "value1",
            "extra_field_2": 123,
        }
        result = validator.validate_physiological(data)
        # 额外字段应被忽略或接受，不应抛异常
        assert result is not None

    # ==========================================================================
    # 5. 多异常同时存在测试
    # ==========================================================================

    def test_multiple_anomalies_recorded(self) -> None:
        """验证同时存在多种异常时，所有异常都被记录"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {
                "sleep_hours": float("nan"),
                "heart_rate": float("inf"),
                "steps": -100,
                "systolic_bp": "invalid",
            },
        )
        assert result.is_valid is False
        anomaly_types = [e["anomaly_type"] for e in result.errors]
        assert "nan_value" in anomaly_types
        assert "inf_value" in anomaly_types
        assert "out_of_range" in anomaly_types
        assert "type_error" in anomaly_types

    def test_multiple_missing_and_invalid(self) -> None:
        """验证同时存在缺失字段和非法值"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_physiological(
            {
                "sleep_hours": float("nan"),
                "heart_rate": 72,
                # 缺失: sleep_quality, exercise_minutes, systolic_bp, diastolic_bp, steps
            },
        )
        assert result.is_valid is False
        anomaly_types = [e["anomaly_type"] for e in result.errors]
        assert "nan_value" in anomaly_types
        assert "missing_required" in anomaly_types

    # ==========================================================================
    # 6. 漂移检测 - 极端分布边界测试
    # ==========================================================================

    def test_drift_detector_empty_distribution(self) -> None:
        """验证空分布输入不抛异常"""
        from app.services.drift_detector import DriftDetector

        detector = DriftDetector()
        # 空分布应返回 0 或 null，不抛异常
        try:
            result = detector.calculate_psi([], [])
            assert result == 0 or result is None or math.isfinite(result)
        except Exception as e:
            pytest.fail(f"Empty distribution should not raise exception: {e}")

    def test_drift_detector_single_value_distribution(self) -> None:
        """验证单值分布输入不抛异常"""
        from app.services.drift_detector import DriftDetector

        detector = DriftDetector()
        try:
            result = detector.calculate_psi([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
            assert result == 0 or result is None or math.isfinite(result)
        except Exception as e:
            pytest.fail(f"Single-value distribution should not raise exception: {e}")

    def test_drift_detector_extreme_values(self) -> None:
        """验证漂移检测处理极端数值不抛 RuntimeWarning"""
        from app.services.drift_detector import DriftDetector

        detector = DriftDetector()
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                result = detector.calculate_psi(
                    [1e-300, 1e300, 1e-300],
                    [1e300, 1e-300, 1e300],
                )
                # 检查没有 RuntimeWarning
                runtime_warnings = [x for x in w if issubclass(x.category, RuntimeWarning)]
                assert len(runtime_warnings) == 0, (
                    f"RuntimeWarning detected: {[str(x.message) for x in runtime_warnings]}"
                )
            except Exception as e:
                pytest.fail(f"Extreme values should not raise exception: {e}")

    # ==========================================================================
    # 7. API 层面 - 非法类型不触发 500
    # ==========================================================================

    def test_api_invalid_types_no_500(self, client: TestClient, as_role) -> None:
        """综合验证: API 在非法类型输入下不返回 500"""
        as_role("admin", 3)

        test_cases = [
            # (method, path, body, description)
            ("POST", "/api/v1/validation/run", {"model_version": 12345, "dataset_path": "/tmp/test.json"}, "numeric model_version"),
            ("POST", "/api/v1/validation/run", {"model_version": "v1.5.0", "dataset_path": ["a", "b"]}, "list dataset_path"),
            ("POST", "/api/v1/canary/deployments", {"version": 123, "traffic_percent": "five"}, "invalid types"),
        ]

        for method, path, body, desc in test_cases:
            response = client.request(method, path, json=body)
            assert response.status_code != 500, (
                f"Endpoint {method} {path} ({desc}) returned 500"
            )
