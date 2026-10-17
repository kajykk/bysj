"""第三十三批存在性核查：文档**文件名级**零记载的 12 个文件 15 条候选。

挑簇口径（第二十七批确立 + 第三十二批沿用）：「函数名是否被裁定文档登记」
只是粗排——函数名级零记载里混着大量已裁残留（如 `tasks/pdf_report.py`
的三个函数在第三十二批仍报零记载，但该文件早在 §1.9 就被整簇裁过）。
本批改用**更硬的信号**：候选文件名的 basename 在
P2_10 / P2_11 / P2_13 三份文档全文**出现 0 次** ⇒ 该文件从未被点名裁定过。

命中该口径的 12 个文件（basename 0 命中）：

    app/api/v1/alerts/_schemas.py        2 条
    app/api/v1/user_upload.py            1 条
    app/core/db_breaker.py               2 条
    app/core/deps.py                     1 条
    app/core/fire_forget_metrics.py      2 条
    app/core/logging_config.py           1 条
    app/core/ml_breaker.py               1 条
    app/core/smtp_breaker.py             1 条
    app/ml/drift_detector.py             1 条
    app/services/email_service.py        1 条
    app/services/excel_job_store.py      1 条
    app/services/pdf_job_store.py        1 条

运行时证据见 `probe_p2_35_batch33_runtime.py`。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    ("app/api/v1/alerts/_schemas.py", 63, "_validate_url_safety"),
    ("app/api/v1/alerts/_schemas.py", 68, "_validate_url_safety"),
    # 接线后本条的行号为 162（接线用的 import 插在 L23，其后整体 +1），
    # 且 scan 会把它标成 wired=True ⇒ 它已从「待接候选」转为「已接线」。
    ("app/api/v1/user_upload.py", 162, "_validate_mime_type"),
    ("app/core/db_breaker.py", 100, "_check_exception_is_connection_failure"),
    ("app/core/db_breaker.py", 109, "_check_exception_is_connection_failure"),
    ("app/core/deps.py", 184, "_role_for_request"),
    ("app/core/fire_forget_metrics.py", 41, "record_scheduled"),
    ("app/core/fire_forget_metrics.py", 77, "_callback"),
    ("app/core/logging_config.py", 235, "configure_logging"),
    ("app/core/ml_breaker.py", 107, "_is_ml_failure"),
    ("app/core/smtp_breaker.py", 113, "_is_smtp_failure"),
    ("app/ml/drift_detector.py", 128, "compute_ks_test"),
    ("app/services/email_service.py", 164, "_send_smtp"),
    ("app/services/excel_job_store.py", 131, "_cleanup_expired"),
    ("app/services/pdf_job_store.py", 129, "_cleanup_expired"),
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
