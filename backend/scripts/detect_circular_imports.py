"""检测 Python 模块循环依赖。

使用 AST 解析 `app/` 目录下所有 .py 文件的 import 语句，构建模块依赖图，
用 Tarjan 强连通分量 (SCC) + DFS 环路枚举检测环并输出环路径。

检测维度：
  1. 启动期循环（top-level import 构成的环）—— 会导致 ImportError / 部分初始化模块
  2. 运行期循环（包含 lazy import 的环）—— 调用时才会触发，通常更隐蔽

用法：
    python backend/scripts/detect_circular_imports.py
    python backend/scripts/detect_circular_imports.py --json report.json
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ImportEdge:
    """一条 import 边。"""

    source: str          # 源模块（app.xxx.yyy）
    target: str          # 目标模块（app.xxx.yyy）
    is_top_level: bool   # 是否为模块顶层 import（非函数/类内部）
    line: int            # import 语句所在行
    source_file: str     # 源文件路径


@dataclass
class CycleReport:
    """一条循环依赖报告。"""

    path: List[str]              # 环上的模块名序列（首尾相同）
    edges: List[ImportEdge]      # 环上的边
    is_startup_cycle: bool       # 是否为启动期循环（全部边为 top-level）
    has_lazy_edge: bool          # 是否含 lazy import 边


# ---------------------------------------------------------------------------
# AST 解析
# ---------------------------------------------------------------------------


def _module_name_for_file(file_path: Path, project_root: Path, pkg_name: str) -> str:
    """根据文件路径推断模块名。

    例如 project_root=.../app, file=.../app/core/config.py -> app.core.config
         file=.../app/models/__init__.py -> app.models
    """
    rel = file_path.relative_to(project_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # 去掉 .py
    if not parts:
        return pkg_name
    return f"{pkg_name}.{'.'.join(parts)}"


def _resolve_relative(module: str, level: int, current_module: str) -> str:
    """解析相对导入。例如 from . import x / from ..core import y"""
    if level == 0:
        return module
    parts = current_module.split(".")
    # level=1 表示当前包，level=2 表示上一级包
    base_parts = parts[: len(parts) - level] if level <= len(parts) else []
    base = ".".join(base_parts)
    if not module:
        return base
    return f"{base}.{module}" if base else module


def _normalize_target(target_module: str, pkg_name: str) -> str | None:
    """将 import 目标规范化为 app/ 包内具体模块。

    import app.core       -> app.core（可能是包，也可能映射到 app/core/__init__.py）
    from app.core import config -> app.core.config
    """
    if not target_module.startswith(pkg_name + ".") and target_module != pkg_name:
        return None  # 外部依赖，忽略
    return target_module


class ImportVisitor(ast.NodeVisitor):
    """收集模块中所有 import 语句，标注是否 top-level。"""

    def __init__(self, source_module: str, source_file: str):
        self.source_module = source_module
        self.source_file = source_file
        self.edges: List[ImportEdge] = []
        self._scope_depth = 0  # >0 表示在函数/类体内

    def _add_import(self, target_module: str | None, line: int, is_from: bool, names: List[str]):
        if not target_module:
            return
        is_top_level = self._scope_depth == 0

        if is_from:
            # from app.pkg import a, b —— 每个被导入的名字都可能映射到 app.pkg.a 子模块
            # 但实践中我们只关心到「包/模块」级别的依赖；同时若名字是子模块名也尝试记录
            # 这里同时记录「目标包」以及「目标包.名字」(若存在该子模块)
            self.edges.append(
                ImportEdge(
                    source=self.source_module,
                    target=target_module,
                    is_top_level=is_top_level,
                    line=line,
                    source_file=self.source_file,
                )
            )
            # 也尝试 app.pkg.name 作为潜在子模块依赖（后处理时再过滤实际存在的）
            for n in names:
                self.edges.append(
                    ImportEdge(
                        source=self.source_module,
                        target=f"{target_module}.{n}",
                        is_top_level=is_top_level,
                        line=line,
                        source_file=self.source_file,
                    )
                )
        else:
            # import app.xxx
            self.edges.append(
                ImportEdge(
                    source=self.source_module,
                    target=target_module,
                    is_top_level=is_top_level,
                    line=line,
                    source_file=self.source_file,
                )
            )

    def visit_Import(self, node: ast.Import):  # noqa: N802
        for alias in node.names:
            target = _normalize_target(alias.name, "app")
            if target is None:
                # 可能是 import app.xxx.yyy as z 这种已处理；其它忽略
                continue
            self._add_import(target, node.lineno, is_from=False, names=[])

    def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
        if node.level and node.level > 0:
            # 相对导入
            target_module = _resolve_relative(node.module or "", node.level, self.source_module)
        else:
            target_module = node.module or ""
        target = _normalize_target(target_module, "app")
        if target is None:
            return
        names = [a.name for a in node.names]
        self._add_import(target, node.lineno, is_from=True, names=names)

    def _enter_scope(self):
        self._scope_depth += 1

    def _leave_scope(self):
        self._scope_depth -= 1

    def visit_FunctionDef(self, node):  # noqa: N802
        self._enter_scope()
        self.generic_visit(node)
        self._leave_scope()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_ClassDef(self, node):  # noqa: N802
        # 类体内的 import 在 Python 中会被视为「类体执行时导入」，通常也会影响启动期；
        # 但模块层级的类定义本身在模块导入时执行，故仍记为 top_level
        # 仅当类被定义在函数内时才进入更深层 scope —— 已由 visit_FunctionDef 处理
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# 构建依赖图
# ---------------------------------------------------------------------------


def build_dependency_graph(
    project_root: Path, pkg_name: str = "app"
) -> Tuple[Dict[str, List[ImportEdge]], Set[str]]:
    """扫描所有 .py 文件，构建模块依赖图。

    返回:
        edges_by_source: {源模块: [ImportEdge, ...]}
        known_modules: 实际存在的模块名集合（用于过滤无效子模块依赖）
    """
    edges_by_source: Dict[str, List[ImportEdge]] = defaultdict(list)
    known_modules: Set[str] = set()

    py_files = sorted(project_root.rglob("*.py"))

    # 第一遍：收集所有模块名
    for f in py_files:
        mod = _module_name_for_file(f, project_root, pkg_name)
        known_modules.add(mod)

    # 第二遍：解析 import
    for f in py_files:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(f))
        except SyntaxError:
            continue
        source_module = _module_name_for_file(f, project_root, pkg_name)
        visitor = ImportVisitor(source_module=source_module, source_file=str(f))
        visitor.visit(tree)
        for edge in visitor.edges:
            # 过滤：仅保留目标为已知模块的边
            # 注意：from app.core import config 会产生 app.core 与 app.core.config 两条候选
            if edge.target in known_modules:
                edges_by_source[edge.source].append(edge)

    return edges_by_source, known_modules


# ---------------------------------------------------------------------------
# 环检测
# ---------------------------------------------------------------------------


def _tarjan_scc(nodes: Set[str], adj: Dict[str, List[str]]) -> List[List[str]]:
    """Tarjan 强连通分量算法。"""
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    result: List[List[str]] = []

    def strongconnect(v: str):
        indices[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in adj.get(v, []):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            result.append(comp)

    # 增加递归上限保护（项目不大，用默认即可）
    sys.setrecursionlimit(10000)
    for v in nodes:
        if v not in indices:
            strongconnect(v)

    return result


def _find_simple_cycles_in_scc(
    scc_nodes: List[str], adj: Dict[str, List[str]]
) -> List[List[str]]:
    """在一个强连通分量内枚举简单环（每个节点出发找回到自身的环）。

    为避免组合爆炸，限制每个 SCC 内枚举的环数量上限。
    """
    scc_set = set(scc_nodes)
    cycles: List[List[str]] = []
    found_signatures: Set[Tuple[str, ...]] = set()
    MAX_CYCLES_PER_SCC = 50
    MAX_DEPTH = 12

    def dfs(start: str, current: str, path: List[str], visited: Set[str]):
        if len(cycles) >= MAX_CYCLES_PER_SCC:
            return
        for nxt in adj.get(current, []):
            if nxt not in scc_set:
                continue
            if nxt == start:
                # 找到一个环
                cycle = path + [start]
                # 规范化：以字典序最小的节点为起点，去除方向歧义
                min_idx = cycle[:-1].index(min(cycle[:-1]))
                rotated = cycle[:-1][min_idx:] + cycle[:-1][:min_idx] + [cycle[:-1][min_idx]]
                sig = tuple(rotated)
                if sig not in found_signatures:
                    found_signatures.add(sig)
                    cycles.append(rotated)
                continue
            if nxt in visited:
                continue
            if len(path) >= MAX_DEPTH:
                continue
            visited.add(nxt)
            dfs(start, nxt, path + [nxt], visited)
            visited.discard(nxt)

    for start in sorted(scc_nodes):
        if len(cycles) >= MAX_CYCLES_PER_SCC:
            break
        dfs(start, start, [start], {start})

    return cycles


def _edges_to_adjacency(
    edges_by_source: Dict[str, List[ImportEdge]],
) -> Dict[str, List[str]]:
    """边列表 -> 邻接表（去重）。"""
    adj: Dict[str, List[str]] = defaultdict(list)
    seen: Dict[str, Set[str]] = defaultdict(set)
    for src, edges in edges_by_source.items():
        for e in edges:
            if e.target not in seen[src]:
                seen[src].add(e.target)
                adj[src].append(e.target)
    return dict(adj)


def _find_edge(
    edges_by_source: Dict[str, List[ImportEdge]],
    source: str,
    target: str,
) -> ImportEdge | None:
    """查找源->目标的某条边（优先返回 top-level 边）。"""
    candidates = [e for e in edges_by_source.get(source, []) if e.target == target]
    if not candidates:
        return None
    # 优先返回 top-level 边
    for e in candidates:
        if e.is_top_level:
            return e
    return candidates[0]


def find_cycles(
    edges_by_source: Dict[str, List[ImportEdge]],
    known_modules: Set[str],
    include_lazy: bool = True,
) -> List[CycleReport]:
    """检测所有循环依赖。

    Args:
        edges_by_source: 依赖图
        known_modules: 已知模块集合
        include_lazy: 是否包含 lazy import 边（用于运行期循环检测）

    Returns:
        循环依赖报告列表
    """
    # 过滤边
    filtered: Dict[str, List[ImportEdge]] = defaultdict(list)
    for src, edges in edges_by_source.items():
        for e in edges:
            if not include_lazy and not e.is_top_level:
                continue
            filtered[src].append(e)

    nodes = set(filtered.keys())
    for src, edges in filtered.items():
        for e in edges:
            nodes.add(e.target)
    nodes &= known_modules | set(filtered.keys())

    adj = _edges_to_adjacency(filtered)

    # Tarjan SCC 找环组
    sccs = _tarjan_scc(nodes, adj)
    multi_sccs = [c for c in sccs if len(c) > 1]
    # 自环（自己 import 自己）
    self_loops = [c for c in sccs if len(c) == 1 and c[0] in adj.get(c[0], [])]

    reports: List[CycleReport] = []

    for scc in multi_sccs:
        cycles = _find_simple_cycles_in_scc(scc, adj)
        for cycle in cycles:
            edges_in_cycle: List[ImportEdge] = []
            for i in range(len(cycle) - 1):
                e = _find_edge(filtered, cycle[i], cycle[i + 1])
                if e:
                    edges_in_cycle.append(e)
            has_lazy = any(not e.is_top_level for e in edges_in_cycle)
            is_startup = not has_lazy
            reports.append(
                CycleReport(
                    path=cycle,
                    edges=edges_in_cycle,
                    is_startup_cycle=is_startup,
                    has_lazy_edge=has_lazy,
                )
            )

    # 自环
    for sl in self_loops:
        e = _find_edge(filtered, sl[0], sl[0])
        if e:
            reports.append(
                CycleReport(
                    path=[sl[0], sl[0]],
                    edges=[e],
                    is_startup_cycle=e.is_top_level,
                    has_lazy_edge=not e.is_top_level,
                )
            )

    # 去重（同一环路径只保留一条）
    seen_paths: Set[Tuple[str, ...]] = set()
    unique: List[CycleReport] = []
    for r in reports:
        key = tuple(r.path)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        unique.append(r)

    # 排序：启动期循环优先
    unique.sort(key=lambda r: (not r.is_startup_cycle, len(r.path)))
    return unique


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def format_report(
    startup_cycles: List[CycleReport],
    runtime_cycles: List[CycleReport],
    project_root: Path,
) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("  Python 模块循环依赖检测报告")
    lines.append(f"  扫描目录: {project_root}")
    lines.append("=" * 78)
    lines.append("")
    lines.append(
        f"启动期循环（top-level import 构成，会导致 ImportError）: {len(startup_cycles)} 个"
    )
    lines.append(
        f"运行期循环（含 lazy import，调用时触发）: {len(runtime_cycles)} 个"
    )
    lines.append("")

    def render_cycle(idx: int, r: CycleReport, kind: str):
        lines.append(f"[{kind} #{idx}] 环长度={len(r.path) - 1}")
        for i, mod in enumerate(r.path):
            edge = r.edges[i] if i < len(r.edges) else None
            if i == 0:
                lines.append(f"    {mod}")
            else:
                e = r.edges[i - 1]
                tag = "top-level" if e.is_top_level else "LAZY"
                lines.append(f"    ^-- ({tag} L{e.line} {Path(e.source_file).name}) --> {mod}")
        lines.append("")

    if startup_cycles:
        lines.append("-" * 78)
        lines.append("  A. 启动期循环（必须治理）")
        lines.append("-" * 78)
        for i, r in enumerate(startup_cycles, 1):
            render_cycle(i, r, "STARTUP")
    else:
        lines.append("✓ 未发现启动期循环依赖")

    if runtime_cycles:
        lines.append("")
        lines.append("-" * 78)
        lines.append("  B. 运行期循环（建议治理，已用 lazy import 缓解）")
        lines.append("-" * 78)
        for i, r in enumerate(runtime_cycles, 1):
            render_cycle(i, r, "RUNTIME")
    else:
        lines.append("✓ 未发现运行期循环依赖")

    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def to_json(
    startup_cycles: List[CycleReport],
    runtime_cycles: List[CycleReport],
    project_root: str,
) -> dict:
    return {
        "project_root": str(project_root),
        "startup_cycle_count": len(startup_cycles),
        "runtime_cycle_count": len(runtime_cycles),
        "startup_cycles": [
            {
                "path": r.path,
                "edges": [
                    {
                        "source": e.source,
                        "target": e.target,
                        "is_top_level": e.is_top_level,
                        "line": e.line,
                        "source_file": e.source_file,
                    }
                    for e in r.edges
                ],
            }
            for r in startup_cycles
        ],
        "runtime_cycles": [
            {
                "path": r.path,
                "edges": [
                    {
                        "source": e.source,
                        "target": e.target,
                        "is_top_level": e.is_top_level,
                        "line": e.line,
                        "source_file": e.source_file,
                    }
                    for e in r.edges
                ],
            }
            for r in runtime_cycles
        ],
    }


# ---------------------------------------------------------------------------
# 动态检测（可选）
# ---------------------------------------------------------------------------


def dynamic_check(backend_root: Path, pkg_name: str = "app") -> List[dict]:
    """尝试逐个导入 app 包下的模块，捕获 ImportError。"""
    import importlib
    import traceback

    failures: List[dict] = []
    app_root = backend_root / pkg_name
    py_files = sorted(app_root.rglob("*.py"))

    # 确保 backend 在 sys.path
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    for f in py_files:
        mod = _module_name_for_file(f, app_root, pkg_name)
        try:
            importlib.import_module(mod)
        except ImportError as e:
            failures.append(
                {
                    "module": mod,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
        except Exception:  # noqa: BLE001
            # 其它异常（如缺少环境变量、数据库连接等）不算循环依赖
            pass

    return failures


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="检测 app/ 包内的循环依赖")
    parser.add_argument(
        "--package",
        default="app",
        help="包名（默认 app）",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="将报告以 JSON 形式写入指定文件",
    )
    parser.add_argument(
        "--dynamic",
        action="store_true",
        help="同时执行动态导入检测（可能产生大量副作用，慎用）",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parent.parent
    project_root = backend_root / args.package

    if not project_root.exists():
        print(f"错误：包目录不存在 {project_root}", file=sys.stderr)
        return 2

    print(f"[*] 扫描 {project_root} ...")
    edges_by_source, known_modules = build_dependency_graph(project_root, args.package)
    print(f"[*] 已知模块数: {len(known_modules)}")
    print(f"[*] import 边数: {sum(len(v) for v in edges_by_source.values())}")

    # 启动期循环（仅 top-level）
    startup_cycles = find_cycles(
        edges_by_source, known_modules, include_lazy=False
    )
    # 全部循环（含 lazy）
    all_cycles = find_cycles(
        edges_by_source, known_modules, include_lazy=True
    )
    runtime_only = [c for c in all_cycles if c.has_lazy_edge]

    report = format_report(startup_cycles, runtime_only, project_root)
    print(report)

    if args.json_path:
        data = to_json(startup_cycles, runtime_only, str(project_root))
        Path(args.json_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[*] JSON 报告已写入 {args.json_path}")

    if args.dynamic:
        print("\n[*] 执行动态导入检测 ...")
        failures = dynamic_check(backend_root, args.package)
        if failures:
            print(f"[!] 动态导入失败 {len(failures)} 个模块：")
            for f in failures:
                print(f"    - {f['module']}: {f['error']}")
        else:
            print("[✓] 动态导入全部成功")

    # 退出码：发现启动期循环则非 0
    return 1 if startup_cycles else 0


if __name__ == "__main__":
    sys.exit(main())
