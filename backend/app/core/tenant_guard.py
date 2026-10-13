"""P2-31 租户隔离**执行层**闸门（``TenantColumnMissingError`` 同类设施的扩展）。

背景（CODE_REVIEW_2026-10-11.md #31 / A-01 / A-02，根因段实锤）：
``review_tasks`` / ``crisis_events`` 两张表**没有 tenant_id 列**，租户归属只能沿
``user_id`` JOIN ``users.tenant_id`` 推导。``app/core/tenant_query.py`` 的
``tenant_scoped_query`` 对无租户列的模型直接抛 ``TenantColumnMissingError`` ——
它阻止了"用错工具"，却**拦不住裸 ``select(ReviewTask)````：那是构造期防御，
裸查询从来没有过任何检查。P0 修复靠"每个服务方法手写 tenant_id 必填"补漏，
而审查实锤：作者在同类方法里整段忘记（``review_service.py`` 全文 tenant 仅
出现 1 次，:375-389 却配有长注释解释为何必须 JOIN）。
⇒ 逐函数手写在认知上不可解决，必须在**执行层**设闸：任何 SELECT 触及受保护表
而没有租户锚点时直接报错，fail-closed。

设计（三条，缺一不可）：
1. **不可绕过** —— 钩子装在引擎 ``before_execute``，ORM / Core / ``text()``
   三条构造路径都经过它，与"是否记得调 helper"无关；
2. **显式豁免** —— 平台管理员看板、GDPR 数据主体导出等**有意**跨租户/按主体
   取数的路径，用语句级 ``.execution_options(tenant_exempt="<登记理由>")``
   显式标记；未登记的理由同样报错（豁免本身受管制，见 EXEMPTION_REGISTRY）；
3. **只拦读路径** —— INSERT/UPDATE/DELETE 不拦：写路径的租户约束语义不同
   （如 ``assign_review`` 的 FOR UPDATE 由同事务前置校验保障），由服务层
   tenant_id 必填关键字参数负责。此范围控制在审计清单中如实记账；
4. **ORM 刷新放行、全新加载拦截** —— ``session.refresh`` / 过期属性重载
   读的是 identity map 里已加载实例（先前加载已过本闸门，主键不可变），
   按 ``_sa_orm_load_options._refresh_state`` 识别后放行；全新的
   ``session.get(Model, id)``（identity map 未命中）无此标记，照拦不误 ——
   那正是 A-01 的未校验加载形态。区分依据为实测探针结论，见
   ``_is_orm_refresh_of_loaded_instance``。

锚点判定（实测依据，勿凭直觉改）：编译 SQL 中 ``users.tenant_id`` 谓词稳定
出现（``SELECT ... FROM review_tasks JOIN users ON users.id = review_tasks.user_id
WHERE users.tenant_id = ?``）。判定偏向严格：**漏判 = 闸门失效，误判 = 响亮
失败可修**，故选严。反向闸门见 ``tests/test_p2_31_tenant_guard.py``。
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# ── 受保护表 ────────────────────────────────────────────────────────────────
# 无 tenant_id 列、租户归属沿 user_id → users.tenant_id 推导的模型。
# 表名（而非模型类）为键：执行层看到的是编译 SQL，与 ORM 映射解耦。
PROTECTED_TABLES: frozenset[str] = frozenset({"review_tasks", "crisis_events"})

# 受保护表在编译 SQL 中的引用形态：review_tasks.id / FROM review_tasks /
# JOIN crisis_events / "review_tasks"."id"（PG 引号形态）。
# 前后词元边界防误配 old_review_tasks / ix_crisis_events_user_status。
_PROTECTED_TABLE_RE = re.compile(
    r'(?<![\w])"?(?:' + "|".join(sorted(PROTECTED_TABLES)) + r')"?(?![\w"])'
)

# 租户锚点：编译 SQL 中 users.tenant_id 谓词（含 PG 引号形态）。
# 刻意从严：只认 users 表限定名，不认任意别名 —— 漏放行（假红）可修，
# 错放行（漏报）是闸门失效。
_ANCHOR_RE = re.compile(r'(?<![\w])"?users"?\s*\.\s*"?tenant_id"?(?![\w])')

# 纳入检查的语句首关键字。INSERT/UPDATE/DELETE/DDL/事务控制不拦（见模块 docstring 第 3 条）。
_CHECKED_LEADING_KEYWORDS = frozenset({"SELECT", "WITH"})


class TenantConstraintMissingError(RuntimeError):
    """SELECT 触及受保护表但缺少租户锚点（users.tenant_id 谓词）时抛出."""


class TenantExemptionUnregisteredError(RuntimeError):
    """语句请求了未在 EXEMPTION_REGISTRY 登记的豁免理由时抛出."""


# ── 豁免登记表 ──────────────────────────────────────────────────────────────
# 键为语句级 ``tenant_exempt=`` 的理由串，值为书面依据。
# 纪律：新增豁免必须在此登记并写明依据；本表由
# ``tests/test_p2_31_tenant_guard.py::TestExemptionRegistry`` 双向把守
# （源码里出现的理由必须已登记；已登记的理由必须有真实使用点）。
EXEMPTION_REGISTRY: dict[str, str] = {
    "platform_admin_ops_dashboard": (
        "运营看板 GET /ops-dashboard/*（app/api/v1/ops_dashboard.py）由 "
        "require_platform_admin() 把关（角色 + 用户须属 DEFAULT_TENANT_ID），"
        "跨租户聚合是有意的平台运营视角，见该模块文件头。"
    ),
    "platform_admin_crisis_export": (
        "平台管理员危机事件 CSV 导出（admin.py export_crisis_events → "
        "CrisisExportService.iter_export_crisis_csv）。tenant_id=None 表示"
        "有意全量导出，实际范围写入审计日志；租户 B 的 admin 被 "
        "require_platform_admin 拦在 403，到不了这条语句。"
    ),
    "data_subject_gdpr": (
        "GDPR 数据主体导出/匿名化（gdpr_service_export / gdpr_service_anonymize）"
        "按 user_id 取数：scope 是数据主体本人（export_my_data / delete_my_account）"
        "或平台管理员对任意主体的 Article 15/17 履行，不按租户切分。"
    ),
    "system_internal_idempotency_check": (
        "ReviewService.create_review_task 的 pending 存在性检查：系统内部写路径"
        "前置查询，按 user_id 幂等去重，不向租户用户返回数据。"
    ),
    "tenant_checked_upstream_same_transaction": (
        "ReviewService.assign_review 的 FOR UPDATE 按主键取行：同事务内 "
        "_ensure_review_in_tenant 已完成租户校验；review_tasks.user_id 不可变、"
        "租户归属不随并发变化，前置校验后按主键加锁是安全的（原注释 :226-229）。"
    ),
    "test_row_verification": (
        "测试夹具回读整行以断言后置状态（如 tests/api/test_review_assign_auth.py "
        "的 _reload），非生产数据面；夹具不构成跨租户暴露路径。"
    ),
}


def _squash(sql: str) -> str:
    """压缩空白，便于首关键字与正则判定."""
    return " ".join(sql.split())


def _is_orm_refresh_of_loaded_instance(execution_options: Mapping[str, Any] | None) -> bool:
    """识别 ORM 对**已加载实例**的刷新加载（``session.refresh`` / 过期属性重载）.

    实测（SQLAlchemy 2.0.49，见 scripts/probe_refresh_paths.py 探针记录）：
    - ``session.refresh(obj)`` 与过期属性懒加载：``execution_options`` 里的
      ``_sa_orm_load_options`` 带 ``_refresh_state``（对象已在 identity map，
      是先前经租户校验的查询加载进来的，重读同一行 —— 主键不可变）；
    - 全新 ``session.get(Model, id)``（identity map 未命中）：load options 是
      ``QueryContext.default_load_options`` 类对象，**无** ``_refresh_state`` ——
      这正是 A-01 形态的未校验加载，必须拦。

    只认这个内部标记是因为它是 ORM 层唯一可区分「重读已校验对象」与「全新
    未校验加载」的信号；误放行的代价由锚点检查的其它路径承担。
    """
    load_options = (execution_options or {}).get("_sa_orm_load_options")
    return load_options is not None and getattr(load_options, "_refresh_state", None) is not None


def check_statement_tenant_scope(
    sql: str,
    execution_options: Mapping[str, Any] | None = None,
) -> None:
    """对一条（已编译的）SQL 执行租户约束检查。不涉及 IO，便于单测。

    Args:
        sql: 编译后的 SQL 文本
        execution_options: 语句级执行选项（含 ``tenant_exempt`` 豁免标记与
            ORM 内部 ``_sa_orm_load_options``）

    Raises:
        TenantConstraintMissingError: 触及受保护表且无锚点、无已登记豁免
        TenantExemptionUnregisteredError: 豁免理由未登记
    """
    squashed = _squash(sql)
    if not squashed:
        return

    leading = squashed.split(None, 1)[0].upper()
    if leading not in _CHECKED_LEADING_KEYWORDS:
        return  # INSERT/UPDATE/DELETE/DDL/事务语句不在本轮范围

    if not _PROTECTED_TABLE_RE.search(squashed):
        return  # 未触及受保护表

    if _ANCHOR_RE.search(squashed):
        return  # 租户锚点在位

    if _is_orm_refresh_of_loaded_instance(execution_options):
        # ORM 对已加载实例的刷新读（refresh / 过期重载）：该实例先前的加载
        # 已经过本闸门（或由本事务创建），主键不可变 → 重读同一行不构成
        # 新的跨租户暴露。全新 session.get 不在此列（无 _refresh_state）。
        return

    options = execution_options or {}
    reason = options.get("tenant_exempt")
    if reason is not None:
        if reason not in EXEMPTION_REGISTRY:
            raise TenantExemptionUnregisteredError(
                f"语句请求了未登记的租户豁免理由 {reason!r}。"
                f"已登记理由：{sorted(EXEMPTION_REGISTRY)}。"
                "新增豁免必须在 app/core/tenant_guard.py 的 EXEMPTION_REGISTRY "
                "登记并写明依据——豁免本身受管制，防止它退化成免责名单。"
            )
        return

    raise TenantConstraintMissingError(
        "租户隔离闸门：该 SELECT 触及受保护表 "
        f"{sorted(PROTECTED_TABLES)} 但缺少租户锚点（users.tenant_id 谓词）。"
        "review_tasks / crisis_events 无 tenant_id 列，必须 JOIN users 推导租户"
        "（用 app.core.tenant_query.user_tenant_scoped_query 构造），"
        "或对有意跨租户的路径显式声明 .execution_options(tenant_exempt=\"<登记理由>\")。"
    )


def _before_execute(conn, clauseelement, multiparams, params, execution_options):
    """引擎 ``before_execute`` 监听器：编译语句并过闸。

    编译失败时放任异常传播 —— 该语句本就即将被引擎编译，结果同样失败，
    不存在"没有闸门反而能跑"的情形。
    """
    sql = str(clauseelement.compile(dialect=conn.dialect))
    check_statement_tenant_scope(sql, execution_options)


def install_tenant_guard(engine: AsyncEngine) -> None:
    """在引擎上安装租户隔离闸门（幂等；重复调用不叠加监听器）。

    生产引擎（``app/core/database.py``）与测试引擎（``tests/conftest.py``）
    都必须安装：测试引擎不装则"绕过即红"的反向闸门失去被测对象。
    """
    sync_engine = engine.sync_engine
    if getattr(sync_engine, "_tenant_guard_installed", False):
        return
    event.listen(sync_engine, "before_execute", _before_execute)
    sync_engine._tenant_guard_installed = True  # type: ignore[attr-defined]
    logger.info("租户隔离执行层闸门已安装: %s", sorted(PROTECTED_TABLES))


# ── 静态扫描（执行层闸门的源码侧对应物）────────────────────────────────────
# 执行层闸门管"每条真的跑了的 SQL"；静态扫描管"每个写出来的查询构造点"，
# 在 CI 期即可发现新增漏网，不必等运行时。两者共用 PROTECTED_TABLES，
# 但静态扫描是**保守**的：只认 ``select(<Model>...)`` 首参为受保护模型的
# 形态，``select_from(Model.__table__...)`` 等变形它看不到 —— 那些形态由
# 执行层闸门在运行时兜底。文档化的局限，勿据此认为静态扫描即全覆盖。

# 认作"已带租户约束"的语句内特征：
# 1. 出现 ``.tenant_id`` 属性引用（直写谓词）；
# 2. 调用租户隔离 helper（``tenant_scoped_query`` / ``tenant_scoped_filter`` /
#    ``user_tenant_scoped_query`` / ``get_tenant_scoped_or_404``）；
# 3. 语句级豁免标记 ``tenant_exempt=``（理由登记由 EXEMPTION_REGISTRY 把守）。
_TENANT_HELPER_NAMES: frozenset[str] = frozenset(
    {
        "tenant_scoped_query",
        "tenant_scoped_filter",
        "user_tenant_scoped_query",
        "get_tenant_scoped_or_404",
    }
)


def _call_name(call: ast.Call) -> str | None:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def statement_has_tenant_constraint(node: ast.stmt) -> bool:
    """判断一条语句是否已带租户约束（或显式豁免标记）。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "tenant_id":
            return True
        if isinstance(sub, ast.Call) and _call_name(sub) in _TENANT_HELPER_NAMES:
            return True
        if isinstance(sub, ast.keyword) and sub.arg == "tenant_exempt":
            return True
    return False


def _selects_protected_model(node: ast.stmt) -> set[str]:
    """返回该语句内 ``select(<受保护模型>...)`` 触及的模型名集合."""
    hit: set[str] = set()
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "select"):
            continue
        if not sub.args:
            continue
        first = sub.args[0]
        name = None
        if isinstance(first, ast.Name):
            name = first.id
        elif isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name):
            name = first.value.id
        if name is not None and name in _PROTECTED_MODEL_NAMES:
            hit.add(name)
    return hit


# 模型类名（AST 看到的是标识符，不是表名）。
_PROTECTED_MODEL_NAMES: frozenset[str] = frozenset({"ReviewTask", "CrisisEvent"})

# 复合语句不算查询构造：其体内叶子语句会被单独遍历到；把 class/def/if/for/
# while/with/try 整体计入会重复计数，并把函数体上游语句的约束特征错记到
# 复合语句头上（实测：audit 首版把 ``class CrisisExportService:`` 报成
# helper —— 那是体内条件 JOIN 的特征）。
_COMPOUND_STMTS: tuple[type[ast.stmt], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.ExceptHandler,
    *( (ast.TryStar,) if hasattr(ast, "TryStar") else () ),  # py3.11+
    *( (ast.Match,) if hasattr(ast, "Match") else () ),  # py3.10+
)


def scan_unscoped_protected_queries(app_dir: Path) -> list[dict[str, str]]:
    """扫描 app_dir 下所有 .py，返回**缺租户约束**的受保护表查询清单.

    Returns:
        [{file, line, model, segment}]，segment 为源码首行摘录（证据用）。
    """
    offenders: list[dict[str, str]] = []
    for path in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.stmt) or isinstance(node, _COMPOUND_STMTS):
                continue
            models = _selects_protected_model(node)
            if not models or statement_has_tenant_constraint(node):
                continue
            seg = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            offenders.append(
                {
                    "file": path.relative_to(app_dir).as_posix(),
                    "line": str(node.lineno),
                    "model": "/".join(sorted(models)),
                    "segment": seg[:160],
                }
            )
    return offenders
