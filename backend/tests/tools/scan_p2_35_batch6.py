"""P2-35 第六批收尾扫描器：剩余候选全清单 + 逐条裁定底稿。

口径与第十一轮 `scripts/scan_p2_11_audit.py::scan_silent_except` **完全一致**
（except 处理器无 raise，且体内有 logger.debug/warning、pass 或 continue），
在此之上做三件第十一轮没做的事：

1. **扣除已接线**：把「except 体内（含嵌套函数/闭包）出现
   `record_silent_degradation(`」的候选标记为已接线 —— 第十一轮的
   has_metric 只认 `inc/labels` 直调，看不到本仓 SSOT helper 的间接接线，
   导致「已接线 3」严重低报（实际 20）。
2. **ImportError 特性探测分桶**（沿用第十一轮裁定：不计入降级债）。
3. 输出每个剩余候选的 **判别特征**（handler 类型 / 是否有 return 值 /
   是否 fire-and-forget / 是否 metrics-sentry 自报失败），供逐条裁定。

产物：`tests/tools/scan_p2_35_batch6_result.json`（静态审计产物，
须在无变异窗口生成）。
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"

SILENT_LOG_METHODS = {"debug", "warning", "info", "error", "exception", "critical"}
METRIC_SELF = {"inc", "labels", "observe"}
# 这些模块内的 except 属于「上报机制自身失败」，不是业务降级（第五批裁定）
SELF_REPORT_HINTS = ("metrics", "sentry", "degradation", "prometheus")


def iter_py(root: pathlib.Path):
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p


def rel(p: pathlib.Path) -> str:
    return str(p.relative_to(BACKEND)).replace("\\", "/")


def handler_types(node: ast.ExceptHandler) -> list[str]:
    if node.type is None:
        return ["<bare>"]
    if isinstance(node.type, ast.Tuple):
        return [getattr(e, "id", getattr(e, "attr", "?")) for e in node.type.elts]
    return [getattr(node.type, "id", getattr(node.type, "attr", "?"))]


def calls_in(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def call_name(c: ast.Call) -> str:
    f = c.func
    if isinstance(f, ast.Attribute):
        base = ast.unparse(f.value)
        return f"{base}.{f.attr}"
    return getattr(f, "id", "?")


def has_fire_and_forget(node: ast.ExceptHandler) -> bool:
    """except 体内是否创建后台任务（create_task / ensure_future）。"""
    for c in calls_in(node):
        nm = call_name(c)
        if nm.endswith("create_task") or nm.endswith("ensure_future"):
            return True
    return False


def returns_fallback(node: ast.ExceptHandler) -> str | None:
    """except 体内 return 的值的形态（fallback / None / 空容器）。"""
    for n in ast.walk(node):
        if isinstance(n, ast.Return) and n.value is not None:
            try:
                return ast.unparse(n.value)[:60]
            except Exception:
                return "?"
    return None


def scan() -> dict:
    real: list[dict] = []
    probe: list[dict] = []
    for p in iter_py(APP):
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(p))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            types = handler_types(node)
            has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
            logs = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in SILENT_LOG_METHODS
                for n in ast.walk(node)
            )
            silent = (not has_raise) and (
                logs
                or any(isinstance(n, ast.Pass) for n in node.body)
                or any(isinstance(n, ast.Continue) for n in node.body)
            )
            if not silent:
                continue
            wired = any(
                isinstance(n, ast.Call)
                and (
                    getattr(n.func, "id", None) == "record_silent_degradation"
                    or getattr(n.func, "attr", None) == "record_silent_degradation"
                )
                for n in ast.walk(node)
            )
            rec = {
                "file": rel(p),
                "line": node.lineno,
                "handled": types,
                "wired": wired,
                "fire_and_forget": has_fire_and_forget(node),
                "returns": returns_fallback(node),
            }
            if any(h in {"ImportError", "ModuleNotFoundError"} for h in types):
                probe.append(rec)
            else:
                real.append(rec)
    return {
        "real_total": len(real),
        "real_wired": sum(1 for r in real if r["wired"]),
        "import_probe": len(probe),
        "real_list": real,
        "probe_list": probe,
    }


def main() -> int:
    result = scan()
    out = BACKEND / "tests" / "tools" / "scan_p2_35_batch6_result.json"
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    unwired = [r for r in result["real_list"] if not r["wired"]]
    print(
        f"真降级候选 {result['real_total']}（已接线 {result['real_wired']} / "
        f"未接线 {len(unwired)}）；ImportError 特性探测 {result['import_probe']}"
    )
    print(f"落盘: {out}")
    # 摘要：未接线候选按文件聚合
    by_file: dict[str, int] = {}
    for r in unwired:
        by_file[r["file"]] = by_file.get(r["file"], 0) + 1
    for f, n in sorted(by_file.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:3d}  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
