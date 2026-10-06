"""防复发闸门：防止重演"实现了、测试了、没接上"的失效模式。

AUDIT-2026-10-06 全量审查发现本项目存在一类贯穿性问题 ——
**安全/校验能力实现了、有测试，却没有任何生产调用点**：

- ``app/core/tenant_query.py``（多租户查询隔离，5 个导出函数零引用）
- ``app/services/input_validator.py``（NaN/Inf 校验，零调用）
- ClamAV 病毒扫描（默认关闭 + 三路异常 fail-open）

这类问题比"没写"更危险：它让 review 的人以为防护到位。
本文件把"有没有真的接上"变成可自动失败的测试。

三道闸门：
1. **孤儿模块检测**：关键模块的导出必须在 app/ 里有真实引用；
2. **配置项接线检测**：``enable_clamav_scan`` / ``clamav_fail_open``
   等安全开关必须在业务代码里真的被读取（而不是只定义）；
3. **租户查询快照锁（ratchet）**：``select(User)`` /
   ``select(OperationLog)`` 这类**租户敏感表**查询若没有 tenant 过滤，
   必须显式登记在白名单里；新增未登记的即失败。
   白名单是"现状快照"——现存 46 处多数是合理的平台/系统作用域
   （seed / Celery / 告警链路 / 监控聚合 / 平台 admin 接口），
   一刀切会误报；但新增必须走登记流程，等于强制每次新增都思考一次。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# ── 闸门 1：关键模块不得成为孤儿 ────────────────────────────────────────────
# 键为模块相对路径，值为该模块必须被外部引用的符号
CRITICAL_MODULES: dict[str, tuple[str, ...]] = {
    # 多租户查询隔离：ADR-001 要求"所有租户敏感查询必须经过此模块构造"
    "core/tenant_query.py": (
        "tenant_scoped_query",
        "tenant_scoped_filter",
    ),
    # 模型输入校验：NaN/Inf 会静默污染风险评分
    "services/input_validator.py": ("InputValidator", "input_validator"),
}


def _iter_source_files() -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        out.extend(Path(dirpath) / f for f in filenames if f.endswith(".py"))
    return out


def _referenced_symbols(exclude: set[Path]) -> dict[str, set[str]]:
    """扫描 app/ 下所有 .py，统计「每个符号在哪些文件里出现过」。

    用文本级匹配而非完整 AST 解析：本文件是**守门测试**，
    宁可多算（漏报），也不能因为解析失败而报错。
    """
    refs: dict[str, set[str]] = {}
    for path in _iter_source_files():
        if path in exclude:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for symbols in CRITICAL_MODULES.values():
            for sym in symbols:
                refs.setdefault(sym, set())
                if sym in text:
                    refs[sym].add(path.relative_to(APP_DIR).as_posix())
    return refs


class TestNoOrphanSecurityModules:
    @pytest.mark.parametrize(
        "rel_path,symbol",
        [(p, s) for p, syms in CRITICAL_MODULES.items() for s in syms],
    )
    def test_symbol_is_used_in_production_code(self, rel_path: str, symbol: str) -> None:
        """关键符号必须在 app/ 的**其他**文件里被引用（测试不算）。"""
        self_path = (APP_DIR / rel_path).resolve()
        refs = _referenced_symbols(exclude={self_path})
        used_in = refs.get(symbol, set())
        assert used_in, (
            f"{rel_path} 里的 {symbol} 在 app/ 中零引用 —— "
            f"这是「实现了但没接上」的复发信号。若确认它已不再需要，"
            f"请连同测试一起删除；若仍需要，请在业务代码中真正调用它。"
        )

    @pytest.mark.parametrize("rel_path", list(CRITICAL_MODULES))
    def test_module_has_at_least_one_live_export(self, rel_path: str) -> None:
        """模块整体不得完全孤儿化。

        逐个符号强制使用会逼出"为了满足测试而硬凑调用"的坏味道，
        因此这里只要求：**至少有一个导出在生产代码里真的被用**。
        """
        self_path = (APP_DIR / rel_path).resolve()
        refs = _referenced_symbols(exclude={self_path})
        symbols = CRITICAL_MODULES[rel_path]
        assert any(refs.get(s) for s in symbols), (
            f"{rel_path} 的全部导出 {symbols} 在 app/ 中零引用 —— 整个模块已沦为孤儿。"
        )


class TestSecuritySwitchesAreRead:
    """安全开关必须被业务代码读取，而不是只躺在 config 里。"""

    def test_clamav_switches_are_consumed(self) -> None:
        text = "\n".join(
            p.read_text(encoding="utf-8", errors="replace") for p in _iter_source_files()
        )
        assert "enable_clamav_scan" in text, "enable_clamav_scan 未被任何代码读取"
        assert "clamav_fail_open" in text, "clamav_fail_open 未被任何代码读取"

    def test_clamav_fail_open_defaults_false(self) -> None:
        """默认必须 fail-closed，否则「病毒扫描失效」的老问题复发。"""
        from app.core.config import Settings

        assert Settings.model_construct().clamav_fail_open is False


# ── 闸门 3：租户敏感表查询快照锁（ratchet）────────────────────────────────
# 只有这两张模型有 tenant_id 列（实测确认），其余租户敏感表要隔离
# 必须先加列 + Alembic 迁移 —— 属 schema 决策，另行处理。
TENANT_SENSITIVE_MODELS = {"User", "OperationLog"}

# 现状快照（由 _unfiltered_tenant_queries 实测得出，20 个文件）。
# 绝大多数是**合理的**平台/系统作用域。分类如下：
#
#   [平台数据面] 操作日志/告警记录本身是平台级资源，访问入口由
#                require_platform_admin / platform 权限依赖把关：
#     api/v1/alerts/__init__.py, api/v1/content_governance.py,
#     api/v1/ops_dashboard.py, services/admin_service_log.py,
#     services/admin_service_archive.py, services/mttr_service.py,
#     services/anomaly_detection_service.py, services/observability/aggregate.py,
#     services/observability/query.py
#   [告警链路] OperationLog 由系统生成，按 fingerprint / id 处理，不按租户切分：
#     monitoring/dedup.py, monitoring/escalation.py, tasks/alerts.py
#   [系统任务] seed 数据与定时清理任务，无请求租户上下文：
#     core/seed.py, tasks/scheduler.py
#   [已鉴权取值] 按已校验的 user_id 取单条，不构成列表越权：
#     core/ws.py, services/gdpr_service_export.py
#   [产品决策] 用户名/邮箱全局唯一（注册）；复核候选用户为平台范围：
#     services/auth_service.py, api/v1/review.py
#   [绑定关系] 绑定表不带 tenant_id，租户隔离依赖 API 层 require_role
#     services/counselor_service_binding.py
#     （咨询师用户列表已用 tenant_scoped_filter 接上，故不在白名单里）
#
# 新增未登记的会失败 → 强制每次新增都回答一次"这个查询要不要租户过滤"。
UNFILTERED_QUERY_ALLOWLIST: set[str] = {
    "api/v1/alerts/__init__.py",
    "api/v1/content_governance.py",
    "api/v1/ops_dashboard.py",
    "api/v1/review.py",
    "core/seed.py",
    "core/ws.py",
    "monitoring/dedup.py",
    "monitoring/escalation.py",
    "services/admin_service_archive.py",
    "services/admin_service_log.py",
    "services/anomaly_detection_service.py",
    "services/auth_service.py",
    "services/counselor_service_binding.py",
    "services/mttr_service.py",
    "services/gdpr_service_export.py",
    "services/observability/aggregate.py",
    "services/observability/query.py",
    "tasks/alerts.py",
    "tasks/scheduler.py",
}


def _unfiltered_tenant_queries() -> set[str]:
    """返回「未带 tenant 过滤的租户敏感表查询」所在文件集合。

    关键：判定范围是**整条语句**而不是 ``select()`` 调用本身。
    链式写法 ``stmt = select(OperationLog)`` 后再 ``stmt = stmt.where(
    OperationLog.tenant_id == x)`` 里，``tenant_id`` 不在 select 调用节点内 ——
    只看调用会把正确实现了隔离的代码误报成漏网。
    """
    found: set[str] = set()
    for path in _iter_source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = path.relative_to(APP_DIR).as_posix()  # 统一用正斜杠，跨平台可比
        for node in ast.walk(tree):
            if not isinstance(node, ast.stmt):
                continue
            has_select = False
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "select"
                    and sub.args
                ):
                    first = sub.args[0]
                    name = None
                    if isinstance(first, ast.Name):
                        name = first.id
                    elif isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name):
                        name = first.value.id
                    if name in TENANT_SENSITIVE_MODELS:
                        has_select = True
                        break
            if not has_select:
                continue
            has_tenant = any(
                isinstance(s, ast.Attribute) and s.attr == "tenant_id" for s in ast.walk(node)
            )
            if not has_tenant:
                found.add(rel)
    return found


class TestTenantQueryRatchet:
    def test_no_new_unfiltered_tenant_queries(self) -> None:
        """新增对 User/OperationLog 的查询必须带 tenant 过滤或登记白名单。"""
        unfiltered = _unfiltered_tenant_queries()
        new_offenders = unfiltered - UNFILTERED_QUERY_ALLOWLIST
        assert not new_offenders, (
            "以下文件对租户敏感表(User/OperationLog)做了无 tenant 过滤的查询，"
            "且未登记在 UNFILTERED_QUERY_ALLOWLIST：\n  "
            + "\n  ".join(sorted(new_offenders))
            + "\n请加上 tenant 过滤，或确认是平台/系统作用域后登记进白名单（并写明理由）。"
        )

    def test_allowlist_has_no_stale_entries(self) -> None:
        """白名单里不该有已经修好的条目（避免allowlist 越滚越大失去意义）。"""
        unfiltered = _unfiltered_tenant_queries()
        stale = UNFILTERED_QUERY_ALLOWLIST - unfiltered
        assert not stale, (
            "白名单中这些文件已不再有无过滤查询，请移除条目：\n  "
            + "\n  ".join(sorted(stale))
        )

    def test_tenant_audit_is_actually_wired(self) -> None:
        """反向验证：真正做了隔离的查询不能被误报成漏网。"""
        text = (APP_DIR / "api/v1/tenant_audit.py").read_text(encoding="utf-8")
        assert "OperationLog.tenant_id ==" in text
