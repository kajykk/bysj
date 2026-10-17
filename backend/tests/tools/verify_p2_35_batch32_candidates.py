"""第三十二批存在性核查：四簇 15 条（函数名级零记载）。

簇来源：`probe_p2_35_batch29_unjudged.py` 的**函数名级**零记载候选清单
（裁定记载的检索单位是函数名，不是文件名 —— 第二十九批确立的口径）。
本批取其中四簇：

- `app/api/v1/metrics_helpers.py` 4 条 —— 10 个函数中 9 个零记载
  （`_load_json` / `collect_ml_quality_metrics` / `collect_drift_metrics` /
  `collect_canary_metrics` 等）。其中 3 条机器判 W（已接线），
  **L116 `_load_json` 是本批唯一待裁项**。
- `app/core/celery_breaker.py` 4 条 —— 4 个函数全部零记载
  （`_collect_infra_exceptions` / `_is_celery_failure`）。
- `app/services/user_data_service.py` 4 条 —— 10 个函数中 8 个零记载
  （`_generate_physio_factors` 四处脏数据 handler）。
- `app/core/idempotency.py` 3 条 —— 4 个函数全部零记载，机器判 W（复核）。

运行时证据见 `probe_p2_35_batch32_runtime.py`。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    # app/api/v1/metrics_helpers.py —— 指标采集/暴露解析共享层
    ("app/api/v1/metrics_helpers.py", 116, "_load_json"),
    # 注：下列三行在为本批接线 `_load_json` 加注释后整体后移 6 行（223/249/275
    # → 231/257/283）。行号以接线后的落盘文本为准。
    ("app/api/v1/metrics_helpers.py", 231, "collect_ml_quality_metrics"),
    ("app/api/v1/metrics_helpers.py", 257, "collect_drift_metrics"),
    ("app/api/v1/metrics_helpers.py", 283, "collect_canary_metrics"),
    # app/core/celery_breaker.py —— Celery broker 熔断器（STAB-P1-005）
    ("app/core/celery_breaker.py", 89, "_collect_infra_exceptions"),
    ("app/core/celery_breaker.py", 97, "_collect_infra_exceptions"),
    ("app/core/celery_breaker.py", 107, "_collect_infra_exceptions"),
    ("app/core/celery_breaker.py", 153, "_is_celery_failure"),
    # app/services/user_data_service.py —— 生理数据因子生成
    ("app/services/user_data_service.py", 165, "_generate_physio_factors"),
    ("app/services/user_data_service.py", 180, "_generate_physio_factors"),
    ("app/services/user_data_service.py", 197, "_generate_physio_factors"),
    ("app/services/user_data_service.py", 212, "_generate_physio_factors"),
    # app/core/idempotency.py —— 幂等键（ISS-094 / SEC-FIX-2026-10-05）
    ("app/core/idempotency.py", 76, "begin_idempotent_call"),
    ("app/core/idempotency.py", 98, "settle_idempotent_call"),
    ("app/core/idempotency.py", 112, "dismiss_idempotent_call"),
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
    for rel, line, fn_name in TARGETS:
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
        fn_actual = classify_mod.enclosing(target, tree)
        body_src = classify_mod.unparse(target)
        func_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_actual:
                if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                    func_src = classify_mod.unparse(fn)
        bucket = classify_mod.classify(rec, body_src, func_src)
        seg = ast.get_source_segment(src, target) or ""
        wired = "record_silent_degradation" in seg
        flag = "" if fn_actual == fn_name else f"  <<FUNC-DRIFT 期望={fn_name}"
        print(
            f"{rel}:{line}  func={fn_actual}  bucket={bucket}  "
            f"wired={rec['wired']}  handler_has_wiring={wired}  "
            f"handled={'/'.join(rec['handled'])}  returns={rec.get('returns')}{flag}"
        )
    print(f"\nMISSING={missing}（>0 说明行号漂移，需重定位后再裁）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
