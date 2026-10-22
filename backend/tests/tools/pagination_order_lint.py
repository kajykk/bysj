"""
分页排序确定性 · AST 判定核心（ROUND_24 / T1）。

为什么必须是 AST 而不是字符串匹配：
判据的本质是「`order_by(...)` 的 **args 结构**」——有几个排序键、分别是什么列、
有没有唯一列做 tie-break，以及这个 statement 是否真的接了分页（`.offset`/`.limit`）。
这些都长在语法树上：字符串匹配既认不出 `stmt = stmt.offset(...)` 这种**链式拆分**
形态，也分不清注释/文档里的示例代码。

判据（继承 ROUND_23 补漏 `2d2eb38` 的结论；ROUND_25 扩展列名与形态）：
    违规 = `order_by(...)` 的 args 里有「非唯一排序列」（默认 created_at）
          **且** args 里没有次级排序键（id / pk）
          **且** 该 statement 确实接了分页/截断（有 .offset 或 .limit）
无 offset/limit 的排序**不判违规**（纯"取最新一条"没有跨页语义）。
只接 limit 的站点（单页 top-N）不自动放行——由调用方逐条裁定后进白名单，
理由必须写明"单页、无跨页语义"，且一旦该站点接上 offset 白名单即失效。

ROUND_25（B 摊）两处扩展：
1. 列名判据 `NON_UNIQUE_TIME_COLUMNS` → `NON_UNIQUE_SORT_COLUMNS` +
   时间戳族结构判据（`_at` 结尾）+ 低基数业务列；见常量注释的纳入/排除判据；
2. 排序键**形态**覆盖：除方法形态 `Model.col.desc()` 外，新增函数形态
   `desc(Model.col)`（sqlalchemy 函数式导入）与裸列形态 `Model.col`。
   ROUND_24 判据只认方法形态 ⇒ 全仓 13 处函数形态站点完全不可见
   （其中 3 处 offset 真分页）——这是本轮实测发现的覆盖缺口。

用法：
    python -m tests.tools.pagination_order_lint            # 扫 backend/app 全仓
    from tests.tools.pagination_order_lint import scan_tree
"""
from __future__ import annotations

import ast
import pathlib
import sys
from dataclasses import dataclass, field

# ---- 判据常量（白名单/扩展都从这里取，避免判据散落在测试里）----

#: 非唯一排序列 · 低基数业务列（ROUND_25 由 NON_UNIQUE_TIME_COLUMNS 重命名扩展）。
#: 一个排序列需要 tie-break，当且仅当它落入以下两类之一：
#:   ① **时间戳族**（结构判据，见 TIMESTAMP_COLUMN_SUFFIX）：列名以 `_at` 结尾。
#:      同秒/同毫秒写入的多行在这些列上取值相同 ⇒ 单键排序下顺序由 DB 决定
#:      （SQLite / PostgreSQL 都不保证）。模型实测 24 个 `_at` 列
#:      （acknowledged_at / archived_at / bound_at / … / viewed_at）——用名字
#:      结构判定而非逐个枚举：枚举会漏（P1-30 的教训是"列举必漏"），未来新增
#:      `reviewed_at` 之类排序列 + 分页会被自动覆盖。
#:   ② **低基数业务列**（本常量，显式枚举、逐个可审）：枚举/状态类，同一取值
#:      大量行共享 ⇒ 并列组巨大。新增成员必须确实是低基数枚举列。
#: 排除判据（写下来防止后人凭感觉加列、也防止白名单腐烂）：
#:   - 主键/近似唯一列：id / pk / config_key / uuid / code / name / username /
#:     email——天然唯一或业务唯一，单键排序本身确定；
#:   - 高基数度量列：view_count / score / count——取值分散、并列组通常为 1，
#:     且不属上述两类（现有站点均另有 created_at/id 兜底）；
#:   - 分组键：group_by 后的 date_key 等——结果集内已唯一。
NON_UNIQUE_SORT_COLUMNS: frozenset[str] = frozenset({"status", "role", "level", "category"})

#: 时间戳族的结构判据：列名以该后缀结尾即视为非唯一时间列（判据①）。
TIMESTAMP_COLUMN_SUFFIX: str = "_at"


def is_non_unique_sort_column(col: str) -> bool:
    """判据合并：低基数业务列（显式）∪ 时间戳族（`_at` 结构）。"""
    return col in NON_UNIQUE_SORT_COLUMNS or col.endswith(TIMESTAMP_COLUMN_SUFFIX)

#: 可接受作次级排序（tie-break）的列。主键天然唯一。
SECONDARY_KEYS: frozenset[str] = frozenset({"id", "pk"})

#: 真正的翻页信号：有 offset 才有"第二页"，才存在跨页重复/漏行。
OFFSET_CALLS: frozenset[str] = frozenset({"offset"})

#: 单页截断：`limit(N)` 没有第二页，**但**"取到的是哪 N 条"在 created_at 并列时
#: 由 DB 决定（N 边界可能落在并列组中间）⇒ 仍须逐条裁定，不能自动放行。
#: 裁定的合法出口只有两个：补次级键，或进白名单并写明"单页 top-N、无跨页语义"。
LIMIT_CALLS: frozenset[str] = frozenset({"limit"})

#: 排序方向（asc/desc 对"是否重复/漏行"没有区别，方向不影响判据）
DIRECTIONS: frozenset[str] = frozenset({"asc", "desc"})


@dataclass(frozen=True)
class OrderBySite:
    """一个 `order_by(...)` 站点及其裁定所需的事实。"""

    file: str
    lineno: int
    col: int
    func: str  # 所在函数名（模块级为 <module>）
    sort_columns: tuple[str, ...]  # args 里出现的列名（按出现顺序）
    has_secondary_key: bool
    has_offset: bool  # 真分页信号
    offset_via: str  # "chain" / "variable" / ""
    has_limit: bool  # 单页截断信号
    is_violation: bool  # (offset or limit) and not secondary
    snippet: str = field(default="", compare=False)

    @property
    def has_paging_clause(self) -> bool:
        return self.has_offset or self.has_limit

    @property
    def loc(self) -> str:
        return f"{self.file}:{self.lineno}"


# --------------------------------------------------------------------------
# 基础抽取
# --------------------------------------------------------------------------


def _col_of_sort_arg(arg: ast.expr) -> str | None:
    """从三种排序键形态抽列名，非该形态返回 None。

    - 方法形态：`Model.created_at.desc()` / `.asc()`（ROUND_24 起支持）；
    - 函数形态：`desc(Model.created_at)` / `asc(Model.created_at)`
      （sqlalchemy 函数式导入——ROUND_24 判据完全看不见，ROUND_25 实测
      全仓 13 处，其中 3 处 offset 真分页）；
    - 裸列形态：`Model.col`（无方向词，默认 asc）。
    模块限定形态（`sa.desc(...)`）一并覆盖：方向词是 Attribute 且首参是列。
    """
    if not isinstance(arg, ast.Call):
        # 裸列形态：order_by(Model.col) / order_by(subq.c.date_key)
        if isinstance(arg, ast.Attribute):
            return arg.attr
        return None
    func = arg.func
    if isinstance(func, ast.Attribute):
        if func.attr not in DIRECTIONS:
            return None
        if isinstance(func.value, ast.Attribute):
            return func.value.attr  # 方法形态
        if arg.args and isinstance(arg.args[0], ast.Attribute):
            return arg.args[0].attr  # 模块形态 sa.desc(Model.col)
        return None
    if isinstance(func, ast.Name) and func.id in DIRECTIONS:
        if arg.args and isinstance(arg.args[0], ast.Attribute):
            return arg.args[0].attr  # 函数形态 desc(Model.col)
    return None


def _is_call(node: ast.AST, attrs: frozenset[str]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in attrs
    )


def _chain_has_attr(
    order_call: ast.Call, tree: ast.AST, attrs: frozenset[str]
) -> bool:
    """链形态：`...order_by(...).offset(x).limit(y)`。

    从 order_by Call 出发沿「谁把它当 func.value」向外扩展（中间节点如
    `.where(...)` 也要穿过），看是否命中目标 attr。这样能覆盖链式调用的
    任意长度，也能覆盖 `stmt = stmt.order_by(...)` 后接 `stmt.offset(...)`
    的**拆分形态**（见 `_variable_has_attr`）。
    """
    frontier: list[ast.AST] = [order_call]
    seen: set[int] = {id(order_call)}
    for _ in range(64):  # 深度上限，防病态结构死循环
        nxt: list[ast.AST] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if any(node.func.value is f for f in frontier):
                if node.func.attr in attrs:
                    return True
                if id(node) not in seen:
                    seen.add(id(node))
                    nxt.append(node)
        if not nxt:
            return False
        frontier = nxt
    return False


def _variable_has_attr(
    order_call: ast.Call, tree: ast.AST, scope: ast.AST, attrs: frozenset[str]
) -> bool:
    """拆分形态：`stmt = stmt.order_by(...)` 之后另起 `stmt = stmt.offset(...)`。

    做法：若 order_by 的结果被赋给某变量 v（或被链式作为 v 的新值），
    则在 scope 内寻找 `v.<attr>(...)`（含 `v.where(...).<attr>(...)`）。
    """
    target_names: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and any(node.value is order_call for _ in [0]):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    target_names.add(tgt.id)
        if isinstance(node, ast.AnnAssign) and node.value is order_call:
            if isinstance(node.target, ast.Name):
                target_names.add(node.target.id)
        # 链式：v = v.order_by(...).offset(...) 已在 chain 分支覆盖
    if not target_names:
        return False
    for node in ast.walk(scope):
        if not _is_call(node, attrs):
            continue
        # v.offset(...) 或 v.where(...).offset(...)：只要链根是 v 即算
        cur: ast.AST = node.func.value
        while isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            cur = cur.func.value
        if isinstance(cur, ast.Name) and cur.id in target_names:
            return True
    return False


def _enclosing_func(tree: ast.AST, node: ast.AST) -> tuple[str, ast.AST]:
    """返回 (所在函数名, 该函数节点/模块节点)。"""
    best: tuple[str, ast.AST] = ("<module>", tree)
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if fn.lineno <= getattr(node, "lineno", 0) <= (fn.end_lineno or fn.lineno):
                if best[0] == "<module>" or fn.lineno >= getattr(best[1], "lineno", 0):
                    best = (fn.name, fn)
    return best


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------


def iter_python_files(root: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]


def _sites_from_source(source: str, rel: str) -> list[OrderBySite]:
    """从源码字符串扫描（不落盘）——find_order_by_sites 与 scan_source 共用。"""
    tree = ast.parse(source, filename=rel)
    lines = source.splitlines()
    sites: list[OrderBySite] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "order_by"):
            continue
        cols = [c for c in (_col_of_sort_arg(a) for a in node.args) if c]
        if not any(is_non_unique_sort_column(c) for c in cols):
            continue  # 只关心非唯一排序列
        has_secondary = any(c in SECONDARY_KEYS for c in cols)
        func_name, scope = _enclosing_func(tree, node)

        offset_via = ""
        if _chain_has_attr(node, tree, OFFSET_CALLS):
            offset_via = "chain"
        elif _variable_has_attr(node, tree, scope, OFFSET_CALLS):
            offset_via = "variable"
        has_offset = bool(offset_via)
        has_limit = _chain_has_attr(node, tree, LIMIT_CALLS) or _variable_has_attr(
            node, tree, scope, LIMIT_CALLS
        )

        snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        sites.append(
            OrderBySite(
                file=rel,
                lineno=node.lineno,
                col=node.col_offset,
                func=func_name,
                sort_columns=tuple(cols),
                has_secondary_key=has_secondary,
                has_offset=has_offset,
                offset_via=offset_via,
                has_limit=has_limit,
                is_violation=(has_offset or has_limit) and not has_secondary,
                snippet=snippet,
            )
        )
    return sites


def find_order_by_sites(
    path: pathlib.Path, root: pathlib.Path
) -> list[OrderBySite]:
    """扫单个文件，返回所有含「非唯一排序列」排序键的 order_by 站点。"""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    rel = path.relative_to(root).as_posix()
    try:
        return _sites_from_source(source, rel)
    except SyntaxError:
        return []


def scan_source(source: str, rel: str = "sample.py") -> list[OrderBySite]:
    """直接从源码字符串扫描（内存态，不落盘）。

    供闸门自证用例使用：自证样本是测试内嵌字符串，走文件系统除了慢，
    还会把 tmp_path 的清理抖动引进断言（2026-10-22 实测：固定 basetemp
    复用时 pytest 的 `<name>current` copytree 竞争导致非确定性 teardown
    ERROR，15 个自证用例集体红，与判据内容无关）。
    """
    return _sites_from_source(source, rel)


def scan_tree(root: pathlib.Path) -> list[OrderBySite]:
    sites: list[OrderBySite] = []
    for path in iter_python_files(root):
        sites.extend(find_order_by_sites(path, root))
    return sites


def violations(root: pathlib.Path) -> list[OrderBySite]:
    return [s for s in scan_tree(root) if s.is_violation]


def _main() -> int:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("app")
    all_sites = scan_tree(root)
    bad = [s for s in all_sites if s.is_violation]
    print(f"scanned files: {len(iter_python_files(root))}")
    print(f"order_by sites (non-unique sort col): {len(all_sites)}")
    print(f"VIOLATIONS (paged/truncated, no tie-break): {len(bad)}")
    for s in bad:
        kind = "offset" if s.has_offset else "limit-only"
        print(f"  {s.loc:<52} {s.func:<32} {kind:<11} cols={s.sort_columns}")
    print("--- has tie-break / no paging clause ---")
    for s in all_sites:
        if s.is_violation:
            continue
        tag = "has-tiebreak" if s.has_secondary_key else "no-paging-clause"
        print(f"  {s.loc:<52} {s.func:<32} {tag}")
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
