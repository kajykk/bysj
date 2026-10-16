"""第二十六批存在性核查：对 app/core/model_engine/loading.py 7 条候选现场重算分类。

口径与 test_batch6_bucket_counts_pinned 完全一致（复用 classify_p2_35_batch6），
先重跑 scan 再逐条 classify，打印桶归属与 handler 是否已接线。

背景：第七批已裁 loading.py 8 条（当时的行号 82/425/284/290/588/704 + 2 处
接线 audit_path_resolve_failed / keras_compat_load_failed），第十九批又对
loading 4 条做了精细钉复核。挑簇器本轮再列 7 条——多半是旧 complain 的
行号平移或文档格式匹配失配，本脚本给出**机器口径**的桶归属以便逐条核实。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    ("app/core/model_engine/loading.py", 244),
    ("app/core/model_engine/loading.py", 82),
    ("app/core/model_engine/loading.py", 429),
    ("app/core/model_engine/loading.py", 288),
    ("app/core/model_engine/loading.py", 294),
    ("app/core/model_engine/loading.py", 596),
    ("app/core/model_engine/loading.py", 712),
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

    for rel, line in TARGETS:
        rec = by_key.get((rel, line))
        if rec is None:
            print(f"{rel}:{line}  NOT-IN-SCAN（候选消失或位移）")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
