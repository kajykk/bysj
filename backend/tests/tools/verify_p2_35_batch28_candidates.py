"""第二十八批存在性核查：`app/core/model_engine/fallback.py` 5 条 +
`services/observability_exporter.py` 4 条（新库存）+ `monitoring/notifier.py` 5 条（复核）。

口径与 `test_batch6_bucket_counts_pinned` 完全一致（复用 `classify_p2_35_batch6`），
先重跑 scan 再逐条 classify，打印桶归属与 handler 是否已接线。

背景：
- `app/core/model_engine/fallback.py` 在 P2_11/P2_13 两份审计文档中**零裁定记载**
  （`_incr_model_fallback` 的 M 型先例只裁过 `model_engine/loading.py` L244 与
  `predict.py` 侧调用点，从未逐条裁过 fallback.py 自身的 4 个 inc 失败点）。
- `app/services/observability_exporter.py` 同样**零裁定记载**。
- `app/monitoring/notifier.py` 已在 P2_13 §1.25 逐条裁过，本批作复核（确认无漂移）。

本脚本给出机器口径的桶归属，以便逐条人工核实。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    # app/core/model_engine/fallback.py —— 启发式回退层（FB 层）
    ("app/core/model_engine/fallback.py", 81),  # _finite: float() TypeError/ValueError
    ("app/core/model_engine/fallback.py", 171),  # structured: _incr_model_fallback 失败
    ("app/core/model_engine/fallback.py", 199),  # text: _incr_model_fallback 失败
    ("app/core/model_engine/fallback.py", 233),  # anxiety_only: _incr_model_fallback 失败
    ("app/core/model_engine/fallback.py", 297),  # physiological: _incr_model_fallback 失败
    # app/services/observability_exporter.py —— 可观测性导出器
    ("app/services/observability_exporter.py", 136),  # stop: task await CancelledError
    ("app/services/observability_exporter.py", 150),  # _wait_for_db_ready: SELECT 1 失败
    ("app/services/observability_exporter.py", 168),  # _loop: _collect_all 失败退避重试
    ("app/services/observability_exporter.py", 206),  # _record_export_failure: 计数器 inc 失败
    # app/monitoring/notifier.py —— 复核（P2_13 §1.25已裁）
    ("app/monitoring/notifier.py", 198),  # SlackNotifier.send 异常
    ("app/monitoring/notifier.py", 287),  # DingTalkNotifier.send 异常
    ("app/monitoring/notifier.py", 342),  # EmailNotifier.send 异常
    ("app/monitoring/notifier.py", 413),  # _dispatch 单通道未捕获异常
    ("app/monitoring/notifier.py", 455),  # _write_channel_log 审计写失败
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