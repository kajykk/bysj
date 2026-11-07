"""ROUND_35 接线闸门：把 P0/P1/P2 里「注释写了、线没接」的点钉成机器可检。

审查报告第六节 P3-24 要求「为接线类修复各补一条翻转实现必须翻转断言的
闸门测试」。本文件覆盖 8 处高风险接线，断言一律钉**交付形态下不变的
事实**（AST 结构或真实 CLI 退出码），不钉注释/docstring 文本。

配套 ``tests/tools/mutate_round35.py`` 对每处做一次真实变异：
翻转实现 ⇒ 对应断言必须变红；字节快照还原 ⇒ 恢复全绿。
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _tree(rel: str) -> ast.Module:
    return ast.parse((BACKEND_ROOT / rel).read_text(encoding="utf-8"))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _calls(node: ast.AST) -> set[str]:
    return {
        _dotted(call.func)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }


def _function(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"函数 {name} 不存在")


def _dict_keys(node: ast.AST) -> set[str]:
    return {
        key.value
        for sub in ast.walk(node)
        if isinstance(sub, ast.Dict)
        for key in sub.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


# --- G1: M-01 CSP 端点必须真的实例化校验模型 --------------------------------

def test_csp_endpoint_instantiates_validation_model():
    """只声明模型不实例化 = 长度约束是死代码。"""
    fn = _function(_tree("app/api/csp_report.py"), "receive_csp_report")
    assert "CSPReportBody.model_validate" in _calls(fn)


# --- G2: M-05 审计 detail 不得出现明文绑定码 --------------------------------

def test_bind_audit_detail_never_writes_plaintext_code():
    """ROUND_34 只修了 refresh 的 else 分支，其余 4 处 record_audit 仍明文。"""
    tree = _tree("app/services/counselor_service_binding.py")
    detail_keys: list[set[str]] = []
    for call in ast.walk(tree):
        if isinstance(call, ast.Call) and _dotted(call.func) == "record_audit":
            for kw in call.keywords:
                if kw.arg == "detail" and isinstance(kw.value, ast.Dict):
                    detail_keys.append(
                        {
                            key.value
                            for key in kw.value.keys
                            if isinstance(key, ast.Constant) and isinstance(key.value, str)
                        }
                    )
    assert detail_keys, "未找到任何 record_audit(detail=...) 调用，断言失去意义"
    assert all("bind_code" not in keys for keys in detail_keys), (
        "审计日志仍在写明文绑定码（能看日志的人即可拿码绑定）"
    )
    assert any("bind_code_fingerprint" in keys for keys in detail_keys), (
        "指纹留痕被一并删除，审计无法追溯同一绑定码"
    )


# --- G3: M-07 影子 Task 必须持强引用 ----------------------------------------

def test_shadow_tasks_are_strongly_referenced():
    for rel in (
        "app/services/shadow_mode_service.py",
        "app/services/shadow_comparison_service.py",
    ):
        calls = _calls(_tree(rel))
        assert "asyncio.create_task" in calls, f"{rel} 未创建后台任务"
        assert "self._tasks.add" in calls, f"{rel} 的 Task 可能被 GC 回收"


# --- G4: M-10 告警升级不得回到固定 limit(500) -------------------------------

def test_escalation_scan_is_cursor_paged():
    tree = _tree("app/monitoring/escalation.py")
    fixed_500 = [
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and _dotted(call.func).endswith(".limit")
        and any(isinstance(a, ast.Constant) and a.value == 500 for a in call.args)
    ]
    assert fixed_500 == [], "告警扫描退回固定 limit(500)，积压时会漏掉未确认告警"
    assert any(
        isinstance(node, ast.Name) and node.id.startswith("cursor_")
        for node in ast.walk(tree)
    ), "未使用游标分页"


# --- G5: M-02 PromQL 正则必须白名单 + fail-closed ---------------------------

def test_metrics_regex_is_whitelisted_and_fail_closed():
    fn = _function(_tree("app/api/v1/metrics_helpers.py"), "build_prometheus_query_result")
    assert "re.fullmatch" in _calls(fn), "用户可控正则未做字符集白名单"
    none_appended = any(
        isinstance(call, ast.Call)
        and _dotted(call.func).endswith("regex_filters.append")
        and any(
            isinstance(arg, ast.Tuple)
            and any(isinstance(e, ast.Constant) and e.value is None for e in arg.elts)
            for arg in call.args
        )
        for call in ast.walk(fn)
    )
    assert none_appended, "非法 pattern 未 fail-closed（静默退化成不过滤）"


# --- G6: S-01 client_ip 彻底移除 --------------------------------------------

def test_analytics_event_record_has_no_client_ip():
    tree = _tree("app/schemas/analytics.py")
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "AnalyticsEventRecord"
    )
    annotated = {
        node.target.id
        for node in ast.walk(cls)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert "client_ip" not in annotated, "响应契约里又出现 client_ip 字段"

    fn = _function(_tree("app/api/v1/analytics_events.py"), "submit_events")
    assert "client_ip" not in _dict_keys(fn), "写入侧又开始采集 client_ip"


# --- G7: M-03 操作日志导出必须有 90 天跨度上限 ------------------------------

def test_operation_log_export_caps_time_span():
    fn = _function(_tree("app/api/v1/admin.py"), "export_operation_logs")
    has_90_days = any(
        isinstance(call, ast.Call)
        and _dotted(call.func).endswith("timedelta")
        and any(
            kw.arg == "days"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value == 90
            for kw in call.keywords
        )
        for call in ast.walk(fn)
    )
    assert has_90_days, "导出端点缺 90 天跨度上限，可一次性拉全表"


# --- G8: M-12 缺模型门禁真实退出码（产物判据，非源码字面） ------------------

def test_missing_model_gate_fails_closed():
    script = BACKEND_ROOT / "scripts" / "check_compatibility.py"
    missing_dir = BACKEND_ROOT / "__r35_no_such_models__"
    assert not missing_dir.exists(), "判据目录竟存在，无法验证缺模型分支"
    base_env = {k: v for k, v in os.environ.items() if k != "CI_ALLOW_MISSING_MODELS"}
    cmd = [
        sys.executable,
        str(script),
        "--json",
        "--models-dir",
        str(missing_dir),
    ]
    blocked = subprocess.run(cmd, capture_output=True, text=True, env=base_env, cwd=BACKEND_ROOT)
    assert blocked.returncode == 1, (
        f"缺模型且未显式放行时门禁仍返回 0（假绿）: {blocked.stdout[:300]}"
    )
    payload = json.loads(blocked.stdout)
    assert payload["ok"] is False

    allowed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**base_env, "CI_ALLOW_MISSING_MODELS": "1"},
        cwd=BACKEND_ROOT,
    )
    assert allowed.returncode == 0, "显式放行后门禁仍失败"
    assert "model_files" in allowed.stdout
