"""STAB-P1-005 测试: 验证限流盲区已覆盖.

通过源码扫描检查 reports/validation/canary/experiment/observability 5 个文件的
所有 @router 装饰的端点都有显式 @limiter.limit 装饰器, 不再存在限流盲区.

限流策略:
- 计算密集接口 (PDF/Excel 生成、ML 实验、校验运行): 5/min
- 敏感操作 (金丝雀部署/回滚): 10/min
- 普通查询 (列表/详情/状态): 30/min
"""

from __future__ import annotations

import importlib
import inspect
import re

import pytest


def _scan_endpoints(module_path: str) -> list[dict]:
    """扫描模块源码, 提取所有端点的装饰器信息.

    Returns:
        list of dict, 每个元素包含:
        - route: 路由装饰器 (如 '@router.post("/user-risk/pdf")')
        - method: HTTP 方法大写 (如 'POST')
        - path: 路由路径 (如 '/user-risk/pdf')
        - limiter: 限流装饰器值 (如 '5/minute') 或 None
        - has_limiter: bool
        - func_name: 函数名
    """
    module = importlib.import_module(module_path)
    src = inspect.getsource(module)
    lines = src.split("\n")
    endpoints: list[dict] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 匹配 @router.xxx 装饰器
        m = re.match(r"@router\.(get|post|put|delete|patch)\(", line)
        if m:
            route = line
            method = m.group(1).upper()
            # 提取路径: 在 @router 行及后续行中搜索引号包裹的路径
            path = ""
            path_match = re.search(r'["\']([^"\']+)["\']', line)
            if not path_match:
                # 多行装饰器: 路径可能在后续 1-3 行
                for k in range(i + 1, min(i + 4, len(lines))):
                    path_match = re.search(r'["\']([^"\']+)["\']', lines[k])
                    if path_match:
                        break
            if path_match:
                path = path_match.group(1)

            limiter_value: str | None = None
            has_limiter = False
            # 向下查找 @limiter.limit 装饰器和函数定义
            j = i + 1
            while j < len(lines) and j < i + 10:
                next_line = lines[j].strip()
                if next_line.startswith("@limiter.limit("):
                    has_limiter = True
                    # 提取限流值
                    match = re.search(r'["\'](\d+/\w+)["\']', next_line)
                    if match:
                        limiter_value = match.group(1)
                    break
                if next_line.startswith("async def ") or next_line.startswith("def "):
                    # 遇到函数定义, 停止查找
                    break
                if next_line.startswith("@router."):
                    # 遇到下一个路由装饰器 (不应该发生), 停止
                    break
                j += 1

            # 查找函数名
            func_name = None
            for k in range(i + 1, min(i + 15, len(lines))):
                def_line = lines[k].strip()
                match = re.match(r"(?:async\s+)?def\s+(\w+)\s*\(", def_line)
                if match:
                    func_name = match.group(1)
                    break

            endpoints.append(
                {
                    "route": route,
                    "method": method,
                    "path": path,
                    "limiter": limiter_value,
                    "has_limiter": has_limiter,
                    "func_name": func_name,
                }
            )
        i += 1

    return endpoints


def _check_request_param(module_path: str) -> list[str]:
    """检查模块中所有端点函数是否有 request 参数.

    Returns:
        list of 缺少 request 参数的端点路由描述
    """
    module = importlib.import_module(module_path)
    missing: list[str] = []
    endpoints = _scan_endpoints(module_path)
    for ep in endpoints:
        func_name = ep["func_name"]
        if func_name is None:
            continue
        func = getattr(module, func_name, None)
        if func is None:
            continue
        try:
            sig = inspect.signature(func)
            params = sig.parameters
            if "request" not in params:
                missing.append(f"{ep['route']} (func={func_name})")
        except (ValueError, TypeError):
            continue
    return missing


# ─────────────────────────────────────────────────────────────────────────────
# 1. 各模块端点都有 @limiter.limit 装饰器
# ─────────────────────────────────────────────────────────────────────────────


class TestAllEndpointsHaveLimiter:
    """验证 5 个模块的所有端点都有 @limiter.limit 装饰器."""

    @pytest.mark.parametrize(
        "module_path,expected_min_count",
        [
            ("app.api.v1.reports", 7),
            ("app.api.v1.validation", 4),
            ("app.api.v1.canary", 9),
            ("app.api.v1.model_predict.experiment", 4),
            ("app.api.v1.observability", 8),
        ],
    )
    def test_all_endpoints_have_limiter(
        self, module_path: str, expected_min_count: int
    ):
        """所有端点都应有 @limiter.limit 装饰器."""
        endpoints = _scan_endpoints(module_path)
        assert (
            len(endpoints) >= expected_min_count
        ), f"{module_path} 应至少有 {expected_min_count} 个端点, 实际 {len(endpoints)}"

        missing_limiter = [ep["route"] for ep in endpoints if not ep["has_limiter"]]
        assert (
            not missing_limiter
        ), f"{module_path} 以下端点缺少 @limiter.limit 装饰器: {missing_limiter}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. 限流值符合策略
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimitValues:
    """验证限流值符合策略 (计算密集 5/min, 敏感操作 10/min, 查询 30/min)."""

    def test_reports_pdf_generation_is_5_per_minute(self):
        """reports.py PDF 生成端点 (POST /user-risk/pdf) 应为 5/min."""
        endpoints = _scan_endpoints("app.api.v1.reports")
        pdf_endpoints = [
            ep
            for ep in endpoints
            if ep["method"] == "POST" and ep["path"] == "/user-risk/pdf"
        ]
        assert pdf_endpoints, "未找到 POST /user-risk/pdf 端点"
        assert (
            pdf_endpoints[0]["limiter"] == "5/minute"
        ), f"PDF 生成应为 5/minute, 实际 {pdf_endpoints[0]['limiter']}"

    def test_reports_excel_export_is_5_per_minute(self):
        """reports.py Excel 导出端点 (POST /batch-export/excel) 应为 5/min."""
        endpoints = _scan_endpoints("app.api.v1.reports")
        excel_endpoints = [
            ep
            for ep in endpoints
            if ep["method"] == "POST" and "batch-export" in ep["path"]
        ]
        assert excel_endpoints, "未找到 POST /batch-export/excel 端点"
        assert (
            excel_endpoints[0]["limiter"] == "5/minute"
        ), f"Excel 导出应为 5/minute, 实际 {excel_endpoints[0]['limiter']}"

    def test_validation_run_is_5_per_minute(self):
        """validation.py 校验运行端点 (POST /run) 应为 5/min."""
        endpoints = _scan_endpoints("app.api.v1.validation")
        run_endpoints = [
            ep for ep in endpoints if ep["method"] == "POST" and ep["path"] == "/run"
        ]
        assert run_endpoints, "未找到 POST /run 端点"
        assert (
            run_endpoints[0]["limiter"] == "5/minute"
        ), f"校验运行应为 5/minute, 实际 {run_endpoints[0]['limiter']}"

    def test_experiment_all_are_5_per_minute(self):
        """experiment.py 所有 ML 实验端点应为 5/min."""
        endpoints = _scan_endpoints("app.api.v1.model_predict.experiment")
        experiment_endpoints = [
            ep
            for ep in endpoints
            if "experiment" in ep["path"] or "experiment" in ep["route"]
        ]
        assert (
            len(experiment_endpoints) >= 4
        ), f"应至少有 4 个 experiment 端点, 实际 {len(experiment_endpoints)}"
        for ep in experiment_endpoints:
            assert (
                ep["limiter"] == "5/minute"
            ), f"{ep['route']} 应为 5/minute, 实际 {ep['limiter']}"

    def test_canary_sensitive_operations_are_10_per_minute(self):
        """canary.py 敏感操作 (POST /pause /resume /rollback /complete + PATCH /traffic) 应为 10/min."""
        endpoints = _scan_endpoints("app.api.v1.canary")
        sensitive_keywords = ["pause", "resume", "rollback", "complete", "traffic"]
        sensitive_endpoints = [
            ep
            for ep in endpoints
            if any(kw in ep["path"] for kw in sensitive_keywords)
            and ep["method"] in {"POST", "PATCH"}
        ]
        assert (
            len(sensitive_endpoints) >= 5
        ), f"应至少有 5 个敏感操作端点, 实际 {len(sensitive_endpoints)}"
        for ep in sensitive_endpoints:
            assert (
                ep["limiter"] == "10/minute"
            ), f"{ep['route']} 应为 10/minute, 实际 {ep['limiter']}"

    def test_observability_all_are_30_per_minute(self):
        """observability 所有查询端点应为 30/min."""
        endpoints = _scan_endpoints("app.api.v1.observability")
        assert (
            len(endpoints) >= 8
        ), f"observability 应至少有 8 个端点, 实际 {len(endpoints)}"
        for ep in endpoints:
            assert (
                ep["limiter"] == "30/minute"
            ), f"{ep['route']} 应为 30/minute, 实际 {ep['limiter']}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. 所有端点都有 request: Request 参数 (slowapi 强制要求)
# ─────────────────────────────────────────────────────────────────────────────


class TestRequestParameter:
    """验证所有限流端点都有 request 参数 (slowapi 强制要求)."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "app.api.v1.reports",
            "app.api.v1.validation",
            "app.api.v1.canary",
            "app.api.v1.model_predict.experiment",
            "app.api.v1.observability",
        ],
    )
    def test_all_endpoints_have_request_param(self, module_path: str):
        """所有限流端点都应有 request 参数."""
        missing = _check_request_param(module_path)
        assert not missing, f"{module_path} 以下端点缺少 request 参数: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. 限流值合法性 (只能是 5/10/30 per minute)
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimitValueValidity:
    """验证所有限流值都是合法的策略值."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "app.api.v1.reports",
            "app.api.v1.validation",
            "app.api.v1.canary",
            "app.api.v1.model_predict.experiment",
            "app.api.v1.observability",
        ],
    )
    def test_all_limiter_values_are_valid(self, module_path: str):
        """所有限流值只能是 5/minute, 10/minute, 30/minute 之一."""
        valid_values = {"5/minute", "10/minute", "30/minute"}
        endpoints = _scan_endpoints(module_path)
        invalid: list[str] = []
        for ep in endpoints:
            if ep["has_limiter"] and ep["limiter"] not in valid_values:
                invalid.append(f"{ep['route']} = {ep['limiter']}")
        assert (
            not invalid
        ), f"{module_path} 存在非法限流值: {invalid}, 合法值: {valid_values}"
