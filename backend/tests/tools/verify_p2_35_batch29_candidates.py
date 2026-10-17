"""第二十九批存在性核查：`app/core/otel.py` 7 条 + `app/api/v1/model_predict/_common.py` 6 条。

口径与 `test_batch6_bucket_counts_pinned` 完全一致（复用 `classify_p2_35_batch6`），
先重跑 scan 再逐条 classify。

背景：两簇在 P2_10/P2_11/P2_13 三份审计文档中**函数名级零记载**
（口径见 `probe_p2_35_batch29_unjudged.py`：以「函数名是否被文档登记」为
裁定单位，比文件名更细、也不受短名误命中影响）：

- `app/core/otel.py` 7 条 —— STAB-P2-009 引入的 OTel SDK 集成层，
  `_check_otel_available` / `init_otel` / `_instrument_*` / `instrument_app` /
  `shutdown_otel` 五个函数名在三份文档中**一次都没出现**。
- `app/api/v1/model_predict/_common.py` 6 条 —— model_predict 包拆分时的
  共享基础设施，函数名同样零记载（其中 L184 已由第六批接线，故机器判 W）。

运行时证据见 `probe_p2_35_batch29_runtime.py`（E1 死配置 / E2 双重不可达 /
E3 启动状态误记 ok / E4 脏数据同形）。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    # app/core/otel.py —— OTel SDK + OTLP 导出集成层
    ("app/core/otel.py", 133, "init_otel"),
    ("app/core/otel.py", 151, "_instrument_fastapi"),
    ("app/core/otel.py", 166, "_instrument_sqlalchemy"),
    ("app/core/otel.py", 180, "_instrument_redis"),
    ("app/core/otel.py", 203, "instrument_app"),
    ("app/core/otel.py", 205, "instrument_app"),
    ("app/core/otel.py", 228, "shutdown_otel"),
    # app/api/v1/model_predict/_common.py —— model_predict 包共享基础设施
    ("app/api/v1/model_predict/_common.py", 184, "_save_assessment_sync"),
    ("app/api/v1/model_predict/_common.py", 261, "_generate_structured_factors"),
    ("app/api/v1/model_predict/_common.py", 317, "_generate_physio_factors"),
    ("app/api/v1/model_predict/_common.py", 333, "_generate_physio_factors"),
    ("app/api/v1/model_predict/_common.py", 349, "_generate_physio_factors"),
    ("app/api/v1/model_predict/_common.py", 365, "_generate_physio_factors"),
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