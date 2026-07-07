"""
T-QA-007: 空值与缺字段测试

测试目标:
- 测试必填字段缺失时的响应
- 测试 null / undefined 值处理
- 验证标准: 返回 400 错误，不触发 500

对应测试计划:
- TC-MON-HP-008: 缺失必填字段触发 INPUT_ANOMALY 记录
- TC-VAL-HP-006: 缺字段样本记录 failure_reason 为 MISSING_FIELD_xxx
- TC-VAL-SP-001: 数据集路径不存在，返回 404
- TC-VAL-SP-002: 数据集格式错误，返回 400
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.slow


class TestNullAndMissingFieldsAPI:
    """T-QA-007: API 层面空值与缺字段测试"""

    # ==========================================================================
    # 1. Validation API - 必填字段缺失测试
    # ==========================================================================

    def test_validation_run_missing_model_version(
        self, client: TestClient, as_role
    ) -> None:
        """验证启动验证时缺失 model_version 字段返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/validation/run",
            json={"dataset_path": "/tmp/test.json"},
        )
        # Pydantic 必填字段缺失应返回 422
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for missing model_version, got {response.status_code}"

    def test_validation_run_missing_dataset_path(
        self, client: TestClient, as_role
    ) -> None:
        """验证启动验证时缺失 dataset_path 字段返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/validation/run",
            json={"model_version": "v1.5.0"},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for missing dataset_path, got {response.status_code}"

    def test_validation_run_null_model_version(
        self, client: TestClient, as_role
    ) -> None:
        """验证 model_version 为 null 时返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/validation/run",
            json={"model_version": None, "dataset_path": "/tmp/test.json"},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for null model_version, got {response.status_code}"

    def test_validation_run_null_dataset_path(
        self, client: TestClient, as_role
    ) -> None:
        """验证 dataset_path 为 null 时返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/validation/run",
            json={"model_version": "v1.5.0", "dataset_path": None},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for null dataset_path, got {response.status_code}"

    def test_validation_run_empty_body(self, client: TestClient, as_role) -> None:
        """验证请求体为空时返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/validation/run",
            json={},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for empty body, got {response.status_code}"

    # ==========================================================================
    # 2. Canary API - 必填字段缺失测试
    # ==========================================================================

    def test_canary_deploy_missing_version(self, client: TestClient, as_role) -> None:
        """验证创建灰度时缺失 version 字段返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/canary/deployments",
            json={"traffic_percent": 5},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for missing version, got {response.status_code}"

    def test_canary_deploy_null_version(self, client: TestClient, as_role) -> None:
        """验证创建灰度时 version 为 null 返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/canary/deployments",
            json={"version": None, "traffic_percent": 5},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for null version, got {response.status_code}"

    # ==========================================================================
    # 3. Report API - 必填字段缺失测试
    # ==========================================================================

    def test_report_pdf_missing_user_id(self, client: TestClient, as_role) -> None:
        """验证生成 PDF 报告时缺失 user_id 返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/reports/user-risk/pdf",
            json={},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for missing user_id, got {response.status_code}"

    def test_report_pdf_null_user_id(self, client: TestClient, as_role) -> None:
        """验证生成 PDF 报告时 user_id 为 null 返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/reports/user-risk/pdf",
            json={"user_id": None},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for null user_id, got {response.status_code}"

    def test_report_excel_missing_filters(self, client: TestClient, as_role) -> None:
        """验证 Excel 导出时缺失必要参数返回 400/422"""
        as_role("admin", 3)
        response = client.post(
            "/api/v1/reports/batch-export/excel",
            json={},
        )
        assert response.status_code in (
            400,
            422,
        ), f"Expected 400/422 for missing filters, got {response.status_code}"

    # ==========================================================================
    # 4. Monitoring API - 查询参数缺失/空值测试
    # ==========================================================================

    def test_monitoring_dashboard_no_auth(self, client: TestClient) -> None:
        """验证未认证访问监控面板返回 401/403"""
        response = client.get("/api/v1/monitoring/dashboard-summary")
        assert response.status_code in (
            401,
            403,
        ), f"Expected 401/403 for unauthenticated access, got {response.status_code}"

    def test_monitoring_success_rate_invalid_granularity(
        self, client: TestClient, as_role
    ) -> None:
        """验证无效 granularity 参数不触发 500"""
        as_role("admin", 3)
        response = client.get(
            "/api/v1/monitoring/model-success-rate?granularity=invalid"
        )
        # 应该优雅处理，返回 200（使用默认值）或 400
        assert response.status_code in (
            200,
            400,
            422,
        ), f"Expected 200/400/422 for invalid granularity, got {response.status_code}"

    # ==========================================================================
    # 5. InputValidator 单元测试 - 空值与缺字段
    # ==========================================================================

    def test_input_validator_none_input(self) -> None:
        """验证 InputValidator 处理 None 输入 (v1.31: 接受 null_input 或 type_error)."""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(None)
        assert result.is_valid is False
        assert any(
            e["anomaly_type"] in ("type_error", "null_input") for e in result.errors
        )

    def test_input_validator_empty_dict(self) -> None:
        """验证 InputValidator 处理空字典输入 (v1.31: 接受多种 anomaly_type)."""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular({}, required_fields=["sleep_hours"])
        assert result.is_valid is False
        # v1.31: 接受 missing_required 或 empty_input
        assert any(
            e["anomaly_type"] in ("missing_required", "empty_input", "type_error")
            for e in result.errors
        )

    def test_input_validator_none_values(self) -> None:
        """验证 InputValidator 处理字段值为 None"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"sleep_hours": None, "heart_rate": 72},
            required_fields=["sleep_hours", "heart_rate"],
        )
        assert result.is_valid is False
        assert any(
            e["anomaly_type"] == "missing_required" and e["field"] == "sleep_hours"
            for e in result.errors
        )

    def test_input_validator_multiple_missing_fields(self) -> None:
        """验证 InputValidator 处理多个缺失字段"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        result = validator.validate_tabular(
            {"heart_rate": 72},
            required_fields=["sleep_hours", "sleep_quality", "heart_rate"],
        )
        assert result.is_valid is False
        missing_fields = [
            e["field"] for e in result.errors if e["anomaly_type"] == "missing_required"
        ]
        assert "sleep_hours" in missing_fields
        assert "sleep_quality" in missing_fields
        assert "heart_rate" not in missing_fields

    def test_input_validator_undefined_field_access(self) -> None:
        """验证 InputValidator 处理未定义字段访问"""
        from app.services.input_validator import InputValidator

        validator = InputValidator()
        # 传入包含未定义字段的数据，不应抛异常
        result = validator.validate_tabular(
            {"sleep_hours": 7.5, "unknown_field": "value"},
        )
        # 未定义字段应被允许通过（或根据策略处理），但不应抛 500
        assert result is not None

    # ==========================================================================
    # 6. 验证不触发 500 错误
    # ==========================================================================

    def test_all_endpoints_no_500_on_null_input(
        self, client: TestClient, as_role
    ) -> None:
        """综合验证: 所有关键端点在异常输入下不返回 500"""
        as_role("admin", 3)

        endpoints = [
            ("POST", "/api/v1/validation/run", {}),
            ("POST", "/api/v1/canary/deployments", {}),
            ("POST", "/api/v1/reports/user-risk/pdf", {}),
            ("POST", "/api/v1/reports/batch-export/excel", {}),
        ]

        for method, path, body in endpoints:
            response = client.request(method, path, json=body)
            assert (
                response.status_code != 500
            ), f"Endpoint {method} {path} returned 500 for null input"
