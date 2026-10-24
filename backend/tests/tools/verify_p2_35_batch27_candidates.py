"""第二十七批存在性核查：对 app/core/sentry.py 6 条 + app/api/v1/metrics.py 5 条
候选现场重算分类。

口径与 test_batch6_bucket_counts_pinned 完全一致（复用 classify_p2_35_batch6），
先重跑 scan 再逐条 classify，打印桶归属与 handler 是否已接线。

背景：这两簇在 docs/P2_11_ROUND11_AUDIT.md 与 docs/P2_13_ROUND13_AUDIT.md 中
**完全无裁定记载**（sentry 此前只在「scheduler 里的 Sentry 调用点」语境被裁过，
metrics.py 的 5 个 _set_* 采集器从未被逐条裁过）⇒ 属真正的新库存，
不是行号平移或格式匹配失配。本脚本给出机器口径的桶归属以便逐条核实。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    # app/core/sentry.py —— Sentry SDK 集成层（自报通道本体）
    ("app/core/sentry.py", 107),  # init_sentry: import sentry_sdk 失败（ROUND_39 +5）
    ("app/core/sentry.py", 153),  # capture_exception: SDK 调用失败（ROUND_39 +5）
    ("app/core/sentry.py", 168),  # capture_message: SDK 调用失败（ROUND_39 +5）
    ("app/core/sentry.py", 27),  # _extract_status_code 路径 1 int() 失败
    ("app/core/sentry.py", 36),  # _extract_status_code 路径 2 int() 失败
    ("app/core/sentry.py", 47),  # _extract_status_code 路径 3 int() 失败
    # app/api/v1/metrics.py —— /metrics 端点的自采集快照器
    ("app/api/v1/metrics.py", 84),  # _set_breaker_metrics 采集失败
    ("app/api/v1/metrics.py", 96),  # _set_db_pool_metrics 采集失败
    ("app/api/v1/metrics.py", 117),  # _set_model_fallback_metric 采集失败
    ("app/api/v1/metrics.py", 136),  # _set_mttr_metrics 采集失败
    ("app/api/v1/metrics.py", 152),  # _set_slo_metrics 采集失败
]


def load(modname: str):
    spec = importlib.util.spec_from_file_location(modname, TOOLS / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    scan_mod = load("scan_p2_35_batch6")
    scan_mod.main()  # 重跑 scan 落盘，保证不是陈旧快照
    classify_mod = load("classify_p2_35_batch6")

    result = json.loads((TOOLS / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8"))
    by_key = {(r["file"], r["line"]): r for r in result["real_list"] + result["probe_list"]}

    missing = 0
    for rel, line in TARGETS:
        rec = by_key.get((rel, line))
        if rec is None:
            print(f"{rel}:{line}  NOT-IN-SCAN（候选消失或位移）")
            missing += 1
            continue
        p = BACKEND / rel
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.lineno == line:
                target = node
                break
        if target is None:
            print(f"{rel}:{line}  NO-HANDLER-AT-LINE（行号漂移）")
            missing += 1
            continue
        fn_name = classify_mod.enclosing(target, tree)
        body_src = classify_mod.unparse(target)
        func_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_name:
                if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                    func_src = classify_mod.unparse(fn)
        bucket = classify_mod.classify(rec, body_src, func_src)
        seg = ast.get_source_segment(src, target) or ""
        wired = "record_silent_degradation" in seg
        print(
            f"{rel}:{line}  func={fn_name}  bucket={bucket}  "
            f"wired={rec['wired']}  handler_has_wiring={wired}  "
            f"handled={'/'.join(rec['handled'])}  returns={rec.get('returns')}"
        )
    print(f"\nMISSING={missing}（>0 说明行号漂移，需重定位后再裁）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
