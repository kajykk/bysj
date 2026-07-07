"""API Contract Tests using schemathesis.

Validates all API endpoints conform to OpenAPI specification.
Run after updating API routes: python scripts/export_openapi.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import schemathesis
from hypothesis import settings

pytestmark = pytest.mark.contract

# Load OpenAPI schema from exported file
OPENAPI_PATH = Path(__file__).parent / "openapi.json"

if not OPENAPI_PATH.exists():
    pytest.skip(
        f"OpenAPI schema not found at {OPENAPI_PATH}. Run: python scripts/export_openapi.py",
        allow_module_level=True,
    )

# PERF: 使用 from_path 加载已导出的 openapi.json (避免 from_asgi 启动 TestClient 获取 schema,
# collection 时间从 ~88s 降至 <1s). 设置 schema.app 使 case.call() 走 ASGI 传输.
# 配置 Schemathesis: 将 400 加入 positive_data_acceptance 的合法状态码列表.
# 默认配置 POSITIVE_DATA_ACCEPTANCE_EXPECTED_STATUSES = ["2xx", "401", "403", "404", "409", "5xx"]
# 不包含 400, 但本项目用 400 表示业务错误 (如"用户名已存在"/"用户不存在"),
# 这些请求在 schema 层面是合法的, 只是业务逻辑拒绝, 应视为合法响应.
from schemathesis.config import SchemathesisConfig
from schemathesis.config._checks import (
    ChecksConfig,
    PositiveDataAcceptanceConfig,
)
from schemathesis.config._projects import ProjectConfig, ProjectsConfig

from app.main import app

_positive_config = PositiveDataAcceptanceConfig(
    # 422 加入合法状态码: FastAPI 的 Pydantic 验证错误 (如密码字节长度校验、
    # extra fields 拒绝) 返回 422, 这些是 schema-compliant 请求的业务验证拒绝,
    # 不是 schema 违规。JSON Schema 无法表达 UTF-8 字节长度约束等业务规则。
    expected_statuses=["2xx", "400", "401", "403", "404", "409", "422", "5xx"]
)
_checks = ChecksConfig(positive_data_acceptance=_positive_config)
_project = ProjectConfig(checks=_checks)
_projects = ProjectsConfig(default=_project)
_contract_config = SchemathesisConfig(projects=_projects)

schema = schemathesis.openapi.from_path(str(OPENAPI_PATH), config=_contract_config)
schema.app = app

# Filtered schemas for specific endpoints
predict_tabular_schema = schema.include(path="/api/v1/model/predict/tabular")
predict_text_schema = schema.include(path="/api/v1/model/predict/text")
health_schema = schema.include(path="/health")


@schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_api_contract(case):
    """Validate all API endpoints conform to OpenAPI spec.

    This test automatically generates requests for all endpoints defined
    in the OpenAPI schema and validates responses.
    """
    response = case.call()
    case.validate_response(response)


@predict_tabular_schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_predict_tabular_contract(case):
    """Specific contract test for tabular prediction endpoint."""
    response = case.call()
    case.validate_response(response)

    # Additional validation for prediction response structure.
    # Note: fallback 模式下 data 是 ApiResponse 包裹的, risk_score 在 data.data 内且可能缺失
    # (当模型不可用时 fallback_used=True, 不返回 risk_score). 这里只验证 ApiResponse 结构.
    if response.status_code == 200:
        data = response.json()
        assert "code" in data and "message" in data


@predict_text_schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_predict_text_contract(case):
    """Specific contract test for text prediction endpoint."""
    response = case.call()
    case.validate_response(response)

    # Note: 同上, fallback 模式下不返回 risk_score, 只验证 ApiResponse 结构.
    if response.status_code == 200:
        data = response.json()
        assert "code" in data and "message" in data


@health_schema.parametrize()
@settings(max_examples=5, deadline=None)
def test_health_endpoint_contract(case):
    """Contract test for health check endpoint."""
    response = case.call()
    case.validate_response(response)

    if response.status_code == 200:
        data = response.json()
        assert "status" in data
