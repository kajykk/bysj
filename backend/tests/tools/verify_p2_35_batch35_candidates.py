"""第三十五批存在性核查：single-flight / 指标自报 / 死代码簇，8 文件 8 条。

挑簇口径（第三十五批第三次换信号 —— 见第三十三、三十四批收口记录）：
- 第三十三批的「basename 零记载」口径：第三十四批初耗尽，且**反向失效**
  （短名被文档别处的同名串命中 ⇒ 假负）。
- 第三十四批的「函数名级零记载」口径：本批实测**彻底退化** —— 25 个候选
  函数名在三份审计文档全文命中数**全为 0**，因为它只按 location 登记、
  不按函数名登记，故该信号已无区分力。
- 本批改用**结构信号**：候选文件是否从未在任何 location 登记表的
  「| `a.b.c` | `path/to/x.py` |」行里出现过（登记表共收录 22 个文件），
  再减去第二十至三十四批已处理簇，逐簇人工核对。命中 8 个文件 8 条。

    app/api/v1/observability/__init__.py   1 条（cached_or_compute）
    app/core/metrics.py                    1 条（track_model_inference）
    app/ml/canary_controller.py            1 条（_log_comparison）
    app/monitoring/escalation.py           1 条（_observe_escalation_latency）
    app/services/observability_service.py  1 条（_flush_loop）
    app/services/risk_service.py           1 条（_schedule_warning_and_intervention）
    app/services/risk_service_warning.py   1 条（_check_warning_trigger）
    app/tasks/anomaly_detection.py         1 条（_detect_impl）

运行时证据见 `probe_p2_35_batch35_runtime.py`。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

# (文件, 行号, 所属函数, 本批人工裁定)
TARGETS = [
    ("app/api/v1/observability/__init__.py", 228, "cached_or_compute", "X-键可分辨"),
    ("app/core/metrics.py", 868, "track_model_inference", "S-同源"),
    ("app/ml/canary_controller.py", 235, "_log_comparison", "DEAD"),
    ("app/monitoring/escalation.py", 59, "_observe_escalation_latency", "S-同源"),
    ("app/services/observability_service.py", 135, "_flush_loop", "DEAD"),
    ("app/services/risk_service.py", 138, "_schedule_warning_and_intervention", "P-内层全捕获"),
    ("app/services/risk_service_warning.py", 136, "_check_warning_trigger", "P-内层全捕获"),
    ("app/tasks/anomaly_detection.py", 140, "_detect_impl", "P-跨进程"),
]


def load(modname: str):
    spec = importlib.util.spec_from_file_location(modname, TOOLS / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def enclosing_func(tree: ast.AST, line: int) -> str | None:
    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1] if best else None


def main() -> int:
    scan = load("scan_p2_35_batch6")
    classify = load("classify_p2_35_batch6")
    scan.main()  # 重跑 scan 落盘，保证不是陈旧快照
    result = json.loads(
        (TOOLS / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8")
    )
    by_key = {
        (r["file"], r["line"]): r for r in result["real_list"] + result["probe_list"]
    }

    print("=" * 78)
    print("第三十五批存在性核查（8 文件 8 条）")
    print("=" * 78)

    missing = 0
    drift = 0
    buckets: dict[str, int] = {}

    for rel, line, fn_name, verdict in TARGETS:
        rec = by_key.get((rel, line))
        if rec is None:
            missing += 1
            print(f"  MISSING  {rel}:{line} ({fn_name})  <- scan 未收录")
            continue

        src = (BACKEND / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)

        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.lineno == line:
                target = node
                break
        if target is None:
            missing += 1
            print(f"  MISSING  {rel}:{line} ({fn_name})  <- 该行没有 except handler")
            continue

        actual_fn = enclosing_func(tree, line)
        if actual_fn != fn_name:
            drift += 1
            print(f"  FUNC-DRIFT {rel}:{line} 期望 {fn_name}，实际 {actual_fn}")

        body_src = ast.unparse(target)
        func_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_name:
                if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                    func_src = ast.unparse(fn)

        bucket = classify.classify(rec, body_src, func_src)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        wired = "record_silent_degradation" in body_src
        print(
            f"  OK  {rel}:{line} ({fn_name})  "
            f"分类器={bucket}  人工={verdict}  接线={'是' if wired else '否'}"
        )

    print("-" * 78)
    print(f"MISSING={missing}  FUNC-DRIFT={drift}")
    print(f"分类器桶分布：{buckets}")
    return 0 if (missing == 0 and drift == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
