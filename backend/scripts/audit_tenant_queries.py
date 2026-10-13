"""P2-31 全仓租户敏感查询路径审计（机制扫描，非人眼）。

口径（刻意收窄，防过报）：
一条语句被认定为「查询路径」当且仅当它是**查询构造语句**——
  A. ``select(<受保护模型>...)`` 首参形态（与常驻闸门测试同口径）；
  B. 含 ``<受保护模型>.__table__``（聚合/select_from 形态）；
  C. SQL 样子的 ``text("... SELECT/INSERT/... <受保护表名> ...")``。
类型注解、docstring、ORM 构造器（``ReviewTask(...)``）、链式续行
（``query = query.where(...)``）、字典键（``counts["crisis_events"]``）
都**不是**查询构造，不计入 —— 它们的约束状态由所归属的构造语句体现。

分类：helper（SSOT）/ tenant_id_attr（直写谓词）/ exempt（已登记豁免）/
unscoped（无约束，必须为 0）/ write（INSERT/UPDATE/DELETE，范围外）。
链式语句内找不到约束特征时，退到**函数级**兜底分类（同函数上游语句提供
helper/谓词），并如实标注粒度。

与 tests/test_p2_31_tenant_guard.py::TestMechanizedAuditGate 的关系：
闸门测试用同口径 A 断言零漏网；本脚本范围更宽（B/C 形态），出具全量清单。
执行层 before_execute 钩子是最终兜底：任何形态的裸 SELECT 跑到引擎都会红。
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))  # 脚本直跑时 app 包可导入

APP_DIR = BACKEND / "app"
OUT_PATH = BACKEND.parent / "docs" / "P2_31_TENANT_QUERY_AUDIT.md"

PROTECTED_MODEL_NAMES = {"ReviewTask", "CrisisEvent"}
PROTECTED_TABLE_NAMES = {"review_tasks", "crisis_events"}
TENANT_HELPER_NAMES = {
    "tenant_scoped_query",
    "tenant_scoped_filter",
    "user_tenant_scoped_query",
    "get_tenant_scoped_or_404",
}
_SQL_VERB_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WITH)\b", re.I)

# 查询构造/写入构造调用名：语句只要引用受保护对象且含这些调用，即为一条
# 「路径」。``where/order_by/limit`` 等 refine 调用不算 —— 它们是已构造语句
# 的续行，约束特征在构造语句上。
_CONSTRUCTION_CALL_NAMES = {
    "select",
    "select_from",
    "text",
    "user_tenant_scoped_query",
    "tenant_scoped_query",
    "tenant_scoped_filter",
    "get_tenant_scoped_or_404",
    "insert",
    "update",
    "delete",
}

# 复合语句不算查询构造：其体内的叶子语句会被 ast.walk 单独遍历到，
# 把 class/def/if/for/while/with/try 整体计入会重复计数并把函数体
# 上游语句的约束特征错记到复合语句头上。
_COMPOUND_STMTS = (
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
)
if hasattr(ast, "TryStar"):  # py3.11+
    _COMPOUND_STMTS = (*_COMPOUND_STMTS, ast.TryStar)
if hasattr(ast, "Match"):  # py3.10+
    _COMPOUND_STMTS = (*_COMPOUND_STMTS, ast.Match)


@dataclass
class Finding:
    file: str
    line: int
    model: str
    shape: str  # A_select / B_table / C_text
    mechanism: str  # helper / tenant_id_attr / exempt / unscoped / write / helper_chain
    detail: str
    segment: str


def _call_name(call: ast.Call) -> str | None:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _is_query_construction(node: ast.stmt) -> tuple[str, set[str]]:
    """返回 (形态标签, 触及的受保护对象)；非查询构造语句返回 ("", set())。

    形态：A_select（select 系，首参或任一实参引用模型）/ B_table
    （``Model.__table__``）/ C_text（SQL 样子且含表名的 text()）/
    E_write（ORM 构造器 ``Model(...)``）。
    """
    models: set[str] = set()
    shape = ""
    has_construction_call = False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            name = _call_name(sub)
            if name in _CONSTRUCTION_CALL_NAMES or name in PROTECTED_MODEL_NAMES:
                has_construction_call = True
            if name in {"user_tenant_scoped_query", "tenant_scoped_query", "tenant_scoped_filter", "get_tenant_scoped_or_404"}:
                shape = shape or "A_helper"
            if name == "select":
                shape = shape or "A_select"
            # 形态 A：select(<受保护模型>) 首参
            if name == "select" and sub.args:
                first = sub.args[0]
                mname = None
                if isinstance(first, ast.Name):
                    mname = first.id
                elif isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name):
                    mname = first.value.id
                if mname in PROTECTED_MODEL_NAMES:
                    models.add(mname)
                    shape = "A_select"
            # ORM 构造器（写路径）
            if name in PROTECTED_MODEL_NAMES:
                has_construction_call = True
                models.add(name)
                shape = shape or "E_write"
        # 形态 B：<受保护模型>.__table__
        if (
            isinstance(sub, ast.Attribute)
            and sub.attr == "__table__"
            and isinstance(sub.value, ast.Name)
            and sub.value.id in PROTECTED_MODEL_NAMES
        ):
            models.add(sub.value.id)
            shape = shape or "B_table"
        # 形态 C：SQL 样子且含受保护表名的 text() 字面量
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "text"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and isinstance(sub.args[0].value, str)
        ):
            sql = sub.args[0].value
            if _SQL_VERB_RE.search(sql):
                for tbl in PROTECTED_TABLE_NAMES:
                    if re.search(rf"(?<![\w]){tbl}(?![\w])", sql):
                        models.add(f"text:{tbl}")
                        shape = shape or "C_text"
        # 语句内任意位置引用模型名（配合构造调用判定，如 select_from(Model)）
        if isinstance(sub, ast.Name) and sub.id in PROTECTED_MODEL_NAMES:
            if has_construction_call:
                models.add(sub.id)
                shape = shape or "A_select"
        if isinstance(sub, ast.Attribute) and sub.attr in PROTECTED_MODEL_NAMES:
            if has_construction_call:
                models.add(sub.attr)
                shape = shape or "A_select"
    if not has_construction_call:
        return "", set()
    return shape, models


def _classify(node: ast.stmt, func_scope: ast.AST | None) -> tuple[str, str]:
    """语句级分类；语句级无特征时退到函数级兜底（链式语句）。"""
    helpers: set[str] = set()
    has_tenant_attr = False
    exemptions: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "tenant_id":
            has_tenant_attr = True
        if isinstance(sub, ast.Call) and _call_name(sub) in TENANT_HELPER_NAMES:
            helpers.add(_call_name(sub) or "")
        if isinstance(sub, ast.keyword) and sub.arg == "tenant_exempt":
            if isinstance(sub.value, ast.Constant) and isinstance(sub.value.value, str):
                exemptions.add(sub.value.value)
    if exemptions:
        return "exempt", f"tenant_exempt={sorted(exemptions)}"
    if helpers:
        return "helper", f"{sorted(helpers)}"
    if has_tenant_attr:
        return "tenant_id_attr", "直写 .tenant_id 谓词"

    # 写语句（ORM 构造器 / insert/update/delete(<Model>)）
    for sub in ast.walk(node):
        cname = _call_name(sub) if isinstance(sub, ast.Call) else None
        if cname in PROTECTED_MODEL_NAMES:
            return "write", f"{cname}(...) ORM 构造器（INSERT 路径）"
        if cname in {"insert", "update", "delete"}:
            for arg in sub.args:
                name = getattr(arg, "id", None) or getattr(getattr(arg, "value", None), "id", None)
                if name in PROTECTED_MODEL_NAMES:
                    return "write", f"{cname}(<Model>)"

    # 函数级兜底：链式语句的约束特征在同函数上游语句
    if func_scope is not None:
        for sub in ast.walk(func_scope):
            if sub is node:
                continue
            if isinstance(sub, ast.Call) and _call_name(sub) in TENANT_HELPER_NAMES:
                return "helper_chain", f"函数级：同函数上游 {_call_name(sub)}()"
            if isinstance(sub, ast.Attribute) and sub.attr == "tenant_id":
                return "helper_chain", "函数级：同函数上游 .tenant_id 谓词"
            if isinstance(sub, ast.keyword) and sub.arg == "tenant_exempt":
                if isinstance(sub.value, ast.Constant) and isinstance(sub.value.value, str):
                    return "helper_chain", f"函数级：同函数上游 tenant_exempt={sub.value.value}"
    return "unscoped", ""


def scan() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        lines = source.splitlines()
        # 预索引：语句 → 所属函数（用于链式兜底）
        func_of: dict[int, ast.AST | None] = {}
        for func in ast.walk(tree):
            if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(func):
                    if isinstance(sub, ast.stmt):
                        func_of.setdefault(id(sub), func)
        for node in ast.walk(tree):
            if not isinstance(node, ast.stmt):
                continue
            if isinstance(node, _COMPOUND_STMTS):
                continue  # 复合语句：约束特征由体内叶子语句体现，不整体计入
            shape, models = _is_query_construction(node)
            if not shape or not models:
                continue
            mechanism, detail = _classify(node, func_of.get(id(node)))
            seg = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            findings.append(
                Finding(
                    file=path.relative_to(BACKEND.parent).as_posix(),
                    line=node.lineno,
                    model="/".join(sorted(models)),
                    shape=shape,
                    mechanism=mechanism,
                    detail=detail,
                    segment=seg[:150],
                )
            )
    return findings


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BACKEND.parent, capture_output=True, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def render(findings: list[Finding]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    by_mech: dict[str, list[Finding]] = {}
    for f in findings:
        by_mech.setdefault(f.mechanism, []).append(f)

    lines: list[str] = []
    lines.append("# P2-31 租户敏感查询路径全仓审计清单")
    lines.append("")
    lines.append(f"- 生成时间：{now}｜仓库 HEAD：`{_git_head()}`")
    lines.append("- 机制：执行层闸门 `app/core/tenant_guard.py`（before_execute，"
                 "不可绕过）+ 静态扫描 `scan_unscoped_protected_queries`"
                 "（CI 期，`tests/test_p2_31_tenant_guard.py::TestMechanizedAuditGate` 常驻）")
    lines.append("- 受保护对象：`review_tasks` / `crisis_events`（无 tenant_id 列，"
                 "租户归属沿 user_id JOIN `users.tenant_id` 推导）")
    lines.append("- 计入口径：仅**查询构造语句**（形态 A_select `select(<Model>...)` / "
                 "A_helper `user_tenant_scoped_query(...)` 等 SSOT 构造 / "
                 "B_table `<Model>.__table__` / C_text SQL 样子且含表名的 `text()` / "
                 "E_write ORM 构造器 `Model(...)`）；类型注解、docstring、链式 refine 续行"
                 "（``query = query.where(...)``）、字典键不计入。")
    lines.append("- 分类：**helper** = SSOT `user_tenant_scoped_query` 或 "
                 "`tenant_scoped_filter`；**tenant_id_attr** = 直写 `.tenant_id` 谓词；"
                 "**exempt** = 语句级 `tenant_exempt=` 已登记豁免；"
                 "**helper_chain** = 语句级无特征，约束在同函数上游语句（链式写法，"
                 "函数级粒度）；**unscoped** = 无约束（必须为 0）；"
                 "**write** = INSERT/UPDATE/DELETE（范围外）。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 机制 | 条数 |")
    lines.append("|---|---|")
    for mech in ("helper", "tenant_id_attr", "exempt", "helper_chain", "unscoped", "write"):
        lines.append(f"| {mech} | {len(by_mech.get(mech, []))} |")
    lines.append(f"| **合计** | **{len(findings)}** |")
    lines.append("")
    unscoped = by_mech.get("unscoped", [])
    lines.append(f"**无约束查询路径：{len(unscoped)} 条**"
                 + ("（新增即被闸门测试与执行层双拦）" if not unscoped else ""))
    lines.append("")
    lines.append("## 逐条清单（按文件:行号）")
    lines.append("")
    lines.append("| # | 位置 | 模型 | 形态 | 机制 | 说明 | 证据（源码首行） |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, f in enumerate(sorted(findings, key=lambda x: (x.file, x.line)), 1):
        seg = f.segment.replace("|", "\\|")
        lines.append(
            f"| {i} | `{f.file}:{f.line}` | {f.model} | {f.shape} | {f.mechanism} "
            f"| {f.detail} | `{seg}` |"
        )
    lines.append("")
    lines.append("## 豁免登记（EXEMPTION_REGISTRY）")
    lines.append("")
    from app.core.tenant_guard import EXEMPTION_REGISTRY  # noqa: E402

    # 测试目录的使用点单独计（本审计只扫 app/，但豁免登记把守覆盖 tests/，
    # 见 tests/test_p2_31_tenant_guard.py::TestExemptionRegistry）
    tests_dir = BACKEND / "tests"
    test_usages: dict[str, int] = {reason: 0 for reason in EXEMPTION_REGISTRY}
    if tests_dir.is_dir():
        for path in sorted(tests_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for reason in EXEMPTION_REGISTRY:
                test_usages[reason] += src.count(f'"{reason}"')

    for reason, justification in EXEMPTION_REGISTRY.items():
        users = [f for f in findings if reason in f.detail]
        total = len(users) + test_usages[reason]
        lines.append(f"- **{reason}**（{total} 个使用点"
                     + (f"，其中 tests/ {test_usages[reason]} 个" if test_usages[reason] else "")
                     + f"）：{justification}")
        for u in users:
            lines.append(f"  - `{u.file}:{u.line}`")
        if test_usages[reason]:
            lines.append(f"  - tests/ 下 {test_usages[reason]} 处（见 TestExemptionRegistry 把守）")
    lines.append("")
    lines.append("## 范围外与已知局限（如实记账）")
    lines.append("")
    lines.append("1. **写路径不拦**：INSERT/UPDATE/DELETE 触及受保护表不过闸 —— 写路径的"
                 "租户约束语义与服务层不同（如 `assign_review` 的 FOR UPDATE 由同事务前置"
                 "校验保障），由服务层 `tenant_id` 必填关键字参数负责（反向闸门："
                 "`TestReverseGates::test_tenant_id_is_required_keyword` 等两条）。")
    lines.append("2. **ORM 刷新放行**：`session.refresh` / 过期属性重载读的是 identity map "
                 "里已加载实例（先前加载已过闸，主键不可变），按 "
                 "`_sa_orm_load_options._refresh_state` 识别后放行；全新 "
                 "`session.get(Model, id)`（identity map 未命中）照拦（A-01 形态，"
                 "`test_by_pk_get_blocked` 把守）。")
    lines.append("3. **链式语句函数级粒度**：`stmt = (...)` 构造后多行 refine 的写法，"
                 "约束特征在构造语句；`helper_chain` 分类即此类，粒度到函数。")
    lines.append("4. **别名锚点从严**：锚点只认 `users.tenant_id` 限定名，不认别名 —— "
                 "漏放行（假红）可修，错放行（漏报）是闸门失效。")
    lines.append("5. **最终兜底在执行层**：静态扫描看不到的形态（动态构造、字符串拼接 SQL）"
                 "只要真的跑到引擎，`before_execute` 一律过闸。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    findings = scan()
    report = render(findings)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")

    unscoped = [f for f in findings if f.mechanism == "unscoped"]
    print(f"审计完成：{len(findings)} 条查询构造语句，unscoped={len(unscoped)}")
    for f in unscoped:
        print(f"  UNSCOPED {f.file}:{f.line} [{f.model}] {f.segment[:80]}")
    print(f"清单已落盘: {OUT_PATH}")
    return 1 if unscoped else 0


if __name__ == "__main__":
    sys.exit(main())
