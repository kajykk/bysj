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

# P2-31：无 tenant_id 列的受保护表（租户归属沿 user_id JOIN users 推导）。
# 来源 = 静态扫描器实际使用的同一集合（app/core/tenant_guard.py 里的
# ``_PROTECTED_MODEL_NAMES``）。重复定义会与扫描器漂移，让闸门 4 失真；
# 但它是**私有**名，故用 getattr 兜底取用，取不到即视为集合为空并让断言失败，
# 不静默跳过。
try:
    from app.core.tenant_guard import _PROTECTED_MODEL_NAMES as PROTECTED_TENANTLESS_MODELS
except ImportError:  # pragma: no cover - app 包不可导入时闸门 4 会红
    PROTECTED_TENANTLESS_MODELS = set()


def _model_has_tenant_column(model_name: str) -> bool:
    """反射 ORM 模型是否真有 tenant_id 列。

    - 用 ``__table__.columns`` 而非源码 grep：grep 会被注释与 docstring 里的
      "tenant_id" 字样误报（本仓已吃过这个亏，见记忆「源码 grep 被注释旧值误报」）。
    - 模型定位**遍历 app.models 全部子模块**而非硬编码模块路径：实测
      OperationLog 实际在 ``app/models/admin.py`` 而非 ``operation_log.py``，
      猜路径会得到「无 tenant_id 列」的假否定，进而把正确代码判成违规。
    - 找不到模型时返回 False（宁可误报也不漏报）。
    """
    import importlib
    import pkgutil

    try:
        models_pkg = importlib.import_module("app.models")
    except Exception:
        return False

    for mod_info in pkgutil.iter_modules(models_pkg.__path__):
        try:
            module = importlib.import_module(f"app.models.{mod_info.name}")
        except Exception:
            continue
        model = getattr(module, model_name, None)
        table = getattr(model, "__table__", None)
        if table is not None:
            return "tenant_id" in table.columns
    return False

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
#   [产品决策] 用户名/邮箱全局唯一（注册）：
#     services/auth_service.py
#   ~~[产品决策] 复核候选用户为平台范围：api/v1/review.py~~
#     AUDIT-2026-10-08 (P1-3) 已移除该条目：``list_assignable_counselors``
#     原以「复核候选是平台范围」为由放行裸 ``select(User)``，导致跨租户咨询师
#     名单（含手机号等 PII）泄露。现已接入 ``tenant_scoped_query``，
#     super_admin 亦不豁免（它同样是租户内管理员）。棘轮测试要求修复后必须
#     移除条目，防止白名单退化成「什么都往里塞」的免责名单。
#   [绑定关系] 绑定表不带 tenant_id，租户隔离依赖 API 层 require_role
#     services/counselor_service_binding.py
#     （咨询师用户列表已用 tenant_scoped_filter 接上，故不在白名单里）
#
# 新增未登记的会失败 → 强制每次新增都回答一次"这个查询要不要租户过滤"。
UNFILTERED_QUERY_ALLOWLIST: set[str] = {
    "api/v1/alerts/__init__.py",
    "api/v1/content_governance.py",
    "api/v1/ops_dashboard.py",
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


# REV-2026-10-20：识别「惯用租户过滤形式」。
# 本仓的惯用写法是调用 ``tenant_scoped_filter(Model, tenant_id)`` /
# ``tenant_scoped_query(Model, tenant_id)``（见 app/core/tenant_query.py）。
# 旧判据只认「语句里出现 X.tenant_id 属性」这一**字面量**形式 ⇒ 惯用 helper
# 调用被误判成"无 tenant 过滤"（假阳性：S3 把 counselor_service_user.py 的
# db.get(User, ...) 改成 select(User).where(..., tenant_scoped_filter(...)) 后
# 立刻被误报）。这正是「断言钉结构不钉字面量」的反面教材：闸门认的是写法，
# 不是语义。
# 收紧点：helper 的第一个实参必须确实是**本语句所查的**租户敏感模型 ——
# 防止拿别的模型的过滤条件顶包，把真漏网的查询蒙混过关。
_TENANT_FILTER_HELPERS = {"tenant_scoped_filter", "tenant_scoped_query"}


def _statement_has_tenant_filter(node: ast.stmt, model_names: set[str]) -> bool:
    """判断语句是否带租户过滤：字面量形式（X.tenant_id）或惯用 helper 形式。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "tenant_id":
            return True
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)):
            continue
        if sub.func.id not in _TENANT_FILTER_HELPERS:
            continue
        for arg in sub.args:
            name = None
            if isinstance(arg, ast.Name):
                name = arg.id
            elif isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                name = arg.value.id
            if name in model_names:
                return True
    return False


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
            selected_models: set[str] = set()
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
                        selected_models.add(name)
            if not selected_models:
                continue
            if not _statement_has_tenant_filter(node, selected_models):
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


# ── 闸门 4：受保护表必须走机制化闸门，不得塞进白名单棘轮 ───────────────────
# P2-31 的实测结论（scripts/probe_ratchet_extension.py）：
# 若把 ReviewTask/CrisisEvent 直接加进 TENANT_SENSITIVE_MODELS 棘轮集合，
# 会**立刻误报 3 个正确实现了隔离的服务文件**
# （services/review_service.py / crisis_export_service.py /
#   gdpr_service_anonymize.py）——因为这两张表无 tenant_id 列，正确写法是
# ``tenant_scoped_filter(User, tenant_id)``，tenant_id 是**位置参数**，
# 语句内不存在 ``X.tenant_id`` 属性节点，棘轮判定条件永远为假。
#
# 那 3 个文件一旦"修棘轮"就只能进白名单 —— 白名单会当场涨成 3 条新免责
# 条款，正是 CODE_REVIEW 根因段点名的退化解法（豁免退化成免责名单）。
# 故：白名单棘轮只管**有 tenant_id 列**的表；无列的受保护表由
# app/core/tenant_guard.py 的执行层 fail-closed 闸门 +
# tests/test_p2_31_tenant_guard.py::TestMechanizedAuditGate 接管。
# 本闸门把这条分流写成断言，防止后人图省事走白名单捷径。
class TestProtectedTablesRoutedToMechanismNotAllowlist:
    def test_protected_models_absent_from_ratchet_set(self) -> None:
        assert not (TENANT_SENSITIVE_MODELS & PROTECTED_TENANTLESS_MODELS), (
            f"受保护表（无 tenant_id 列）被加进了白名单棘轮集合："
            f"{sorted(TENANT_SENSITIVE_MODELS & PROTECTED_TENANTLESS_MODELS)}。"
            "它们必须由 app/core/tenant_guard.py 的执行层闸门接管 —— "
            "加进棘轮会让正确实现隔离的服务文件全部误报，"
            "逼人把它们塞进 UNFILTERED_QUERY_ALLOWLIST（白名单退化成免责名单）。"
        )

    def test_ratchet_anchor_assumption_still_holds(self) -> None:
        """棘轮的前提是「集合内模型都有 tenant_id 列」；有列的表一旦失配，
        同样会让正确实现隔离的代码全量误报。此断言守住该前提。"""
        mismatched = [
            name
            for name in sorted(TENANT_SENSITIVE_MODELS)
            if not _model_has_tenant_column(name)
        ]
        assert not mismatched, (
            f"棘轮集合中这些模型没有 tenant_id 列：{mismatched}。"
            "棘轮判定依赖语句内出现 `X.tenant_id` 属性节点，"
            "无列模型在正确实现隔离时也不会出现该节点 → 全量误报。"
            "请把它移出棘轮集合，改由 tenant_guard 执行层闸门接管。"
        )

    def test_mechanism_is_actually_installed_and_scanning(self) -> None:
        """分流的前提是机制真的在位：静态扫描函数可调用 + 测试引擎装了执行层闸门。
        否则闸门 4 只是把缺口从一边挪到另一边。"""
        from app.core.tenant_guard import PROTECTED_TABLES, scan_unscoped_protected_queries

        assert PROTECTED_TABLES, "受保护表集合为空 —— 闸门 4 失去了分流对象"
        assert scan_unscoped_protected_queries(APP_DIR) == [], (
            "静态扫描有漏网项，说明受保护表并未真正被机制接管，"
            "此时禁止把它们挪出棘轮集合（会同时失去两道闸门）。"
        )
