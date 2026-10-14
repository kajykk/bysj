"""P2-35 第六批收尾：把剩余候选**逐条裁定**到处置桶，产物供审计文档引用。

裁定规则（按优先级匹配，每条都有书面理由；规则本身是交付物的一部分）：

  W  已接线     —— handler 内有 record_silent_degradation / 直调 inc
  P  特性探测   —— ImportError/ModuleNotFoundError（第十一轮裁定：不计降级债）
  S  自报失败   —— 失败的是 metrics/sentry/otel/gauge 上报本身（第五批裁定）
  D  脏数据探测 —— JSONDecodeError/UnicodeDecodeError/InvalidTag/InvalidToken/
                   ValueError/TypeError 单条解析跳过（数据本来就是坏的）
  C  清理路径   —— aclose/close/stop/cancel 失败（资源清理，不影响业务语义）
  H  检查型     —— health check 返回 False（不健康**就是**返回值，信号即数据）
  F  保守方向   —— 宁可少清理/不发（AUDIT-P0-3 同型：安全侧 fail-safe）
  R  自恢复     —— handler 内 sleep+continue/restart（瞬时降级，会自愈）
  M  已有专用计数器 —— 同函数/邻近已有专用 metric（warning_notify_failed_total /
                   model_fallback_count），不重复接通用计数器
  G  fail-closed 安全 —— 认证/授权/校验路径返回 None/False 拒绝（安全方向，
                   不是"降级"，是设计上的 fail-closed）
  V  显式失败上报 —— handler 把业务状态写成 failed/error 且调用方可见
                   （失败被如实呈现，非静默）
  S2 自报失败-它文件 —— body 含 "inc failed"/"指标不可用"/"指标上报失败"
                   （metrics 自报失败，第五批裁定的推广）
  X  真降级留档 —— 其余：确属真降级但本批未接，逐条列待接清单

X 桶不是"没处置"——它是显式的"真降级，留待后续批"记账，清单全量列出。
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"

PROBE_TYPES = {"ImportError", "ModuleNotFoundError"}
DIRTY_TYPES = {
    "JSONDecodeError",
    "UnicodeDecodeError",
    "InvalidTag",
    "InvalidToken",
    "ValueError",
    "TypeError",
}
SELF_REPORT_FILES = (
    "app/core/metrics.py",
    "app/core/sentry.py",
    "app/core/otel.py",
    "app/core/degradation.py",
    "app/core/fire_forget_metrics.py",
    "app/core/log_sanitizer.py",
    "app/core/logging_config.py",
    "app/api/v1/metrics.py",
    "app/api/v1/metrics_helpers.py",
    "app/api/v1/observability/__init__.py",
)
CLEANUP_HINTS = ("aclose", "close(", "stop", "cancel")
SLEEP_HINTS = ("asyncio.sleep", "time.sleep", "sleep(")


def rel(p: pathlib.Path) -> str:
    return str(p.relative_to(BACKEND)).replace("\\", "/")


def handler_types(node: ast.ExceptHandler) -> list[str]:
    if node.type is None:
        return ["<bare>"]
    if isinstance(node.type, ast.Tuple):
        return [getattr(e, "id", getattr(e, "attr", "?")) for e in node.type.elts]
    return [getattr(node.type, "id", getattr(node.type, "attr", "?"))]


def unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def enclosing(node: ast.ExceptHandler, tree: ast.AST) -> str:
    """except 所在函数名（模块.函数 全限定）。"""
    best = ""
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno):
                if not best or fn.lineno > getattr(enclosing, "_ln", 0):
                    best, enclosing._ln = fn.name, fn.lineno  # type: ignore[attr-defined]
    return best


def classify(rec: dict, body_src: str, func_src: str) -> str:
    types = set(rec["handled"])
    if rec["wired"]:
        return "W"
    # 第十一轮直调风格：handler 内 silent_degradation_total.inc(location=...)
    if "silent_degradation_total" in body_src and ".inc(" in body_src:
        return "W"
    if types & PROBE_TYPES:
        return "P"
    if rec["file"] in SELF_REPORT_FILES:
        return "S"
    # S2：其它文件里的 metrics 自报失败（celery_task_failures_total inc failed 等）
    if (
        "inc failed" in body_src
        or "指标不可用" in body_src
        or "指标上报失败" in body_src
        or "gauge 更新失败" in body_src
        or "计数更新失败" in body_src
        or "记录降级指标失败" in body_src
    ):
        return "S"
    # G：fail-closed 安全路径（token 解码失败→无角色→拒绝；URL 安全校验失败→拒）
    if (
        "decode_token" in func_src
        or "_validate_url_safety" in func_src
        or "_validate_mime_type" in func_src
        or ("return None" in body_src and "role" in func_src)
    ):
        return "G"
    # V：显式把状态写成 failed/error（用户/调用方可见）
    if 'status="failed"' in body_src or "status='failed'" in body_src:
        return "V"
    if "health check" in body_src or "health_check" in body_src:
        return "H"
    if types == {"CancelledError"}:
        return "K"
    if any(h in body_src for h in CLEANUP_HINTS) and not rec["returns"]:
        return "C"
    if any(h in body_src for h in SLEEP_HINTS):
        return "R"
    if types and types <= DIRTY_TYPES:
        return "D"
    if "保守" in body_src or "跳过删除" in body_src or "fail-safe" in body_src:
        return "F"
    if "warning_notify_failed_total" in func_src or "_incr_fallback" in func_src:
        return "M"
    return "X"


def main() -> int:
    result = json.loads(
        (BACKEND / "tests" / "tools" / "scan_p2_35_batch6_result.json").read_text(
            encoding="utf-8"
        )
    )
    rows: list[dict] = []
    for rec in result["real_list"] + result["probe_list"]:
        p = BACKEND / rec["file"]
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        # 找到对应 lineno 的 handler 与所在函数
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.lineno == rec["line"]:
                target = node
                break
        if target is None:
            continue
        fn_name = enclosing(target, tree)
        body_src = unparse(target)
        # 函数体源码（用于 M 桶判定）
        func_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_name:
                if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                    func_src = unparse(fn)
        bucket = classify(rec, body_src, func_src)
        rows.append(
            {
                "file": rec["file"],
                "line": rec["line"],
                "func": fn_name,
                "handled": rec["handled"],
                "bucket": bucket,
            }
        )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    out = BACKEND / "tests" / "tools" / "classify_p2_35_batch6_result.json"
    out.write_text(
        json.dumps({"counts": counts, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("桶计数:", dict(sorted(counts.items())))
    x_rows = [r for r in rows if r["bucket"] == "X"]
    print(f"\nX 桶（真降级留档）{len(x_rows)} 条：")
    for r in x_rows:
        print(f"  {r['file']}:{r['line']}  {r['func']}  {r['handled']}")
    print(f"\n落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
