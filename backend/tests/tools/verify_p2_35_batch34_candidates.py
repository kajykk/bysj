"""第三十四批存在性核查：可观测聚合 / 指标上报 / 审计留痕 / 限流 簇，10 文件 12 条。

挑簇口径（第三十四批再换信号 —— 见第三十三批收口记录）：
- 第三十三批用的「basename 在裁定文档全文 0 次」口径**已耗尽**（剔除当批 12 文件后
  剩余 0 条）。它这次是**反向失效**：`cache.py`/`reports.py`/`inference.py`
  这类短名被文档里别处的同名串命中 ⇒ 产生假负。
- 本批改用：**函数名级零记载 − 第二十至三十三批已处理簇**，并逐簇人工核对。
  人工核对剔除掉两个大簇：
    * `core/model_engine/predict.py`（9 条）—— 第十二批接线 3 + 第二十一批
      剩余 6 条全部裁定不接，是已裁残留（8 条本来就是 W）。
    * `services/canary_fallback_monitor.py`（5 条）—— 第九批整簇裁过。

命中新口径的 10 个文件（含 2 个 W 复核项）：

    app/services/observability/aggregate.py   2 条（1 X + 1 W 复核）
    app/monitoring/dedup.py                   2 条
    app/core/model_engine/inference.py        2 条
    app/core/kill_switch.py                   1 条
    app/services/registry_auto_rollback.py    2 条
    app/api/v1/admin.py                       1 条
    app/core/rate_limit.py                    2 条

运行时证据见 `probe_p2_35_batch34_runtime.py`。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

TARGETS = [
    ("app/services/observability/aggregate.py", 38, "_parse_detail_json"),
    # 接线插在 L38 的 handler 体内（+10 行），本条随之后移 474 → 484
    ("app/services/observability/aggregate.py", 484, "_fetch_lock_memory_stats"),
    ("app/monitoring/dedup.py", 95, "should_send"),
    ("app/monitoring/dedup.py", 103, "should_send"),
    ("app/core/model_engine/inference.py", 350, "_publish_to_prometheus"),
    ("app/core/model_engine/inference.py", 364, "stop_persist"),
    ("app/core/kill_switch.py", 109, "_record_degraded"),
    ("app/services/registry_auto_rollback.py", 136, "stop_auto_rollback_monitor"),
    ("app/services/registry_auto_rollback.py", 138, "stop_auto_rollback_monitor"),
    ("app/api/v1/admin.py", 619, "_stream_csv"),
    ("app/core/rate_limit.py", 142, "decorator"),
    ("app/core/rate_limit.py", 198, "__call__"),
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
    print("第三十四批存在性核查（10 文件 12 条）")
    print("=" * 78)

    missing = 0
    drift = 0
    buckets: dict[str, int] = {}

    for rel, line, fn_name in TARGETS:
        rec = by_key.get((rel, line))
        if rec is None:
            missing += 1
            print(f"  MISSING  {rel}:{line} ({fn_name})  ← scan 未收录")
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
            print(f"  MISSING  {rel}:{line} ({fn_name})  ← 该行没有 except handler")
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
            f"  OK  {rel}:{line} ({fn_name})  bucket={bucket} "
            f"wired={wired}  exc={ast.unparse(target.type) if target.type else 'bare'}"
        )

    print("-" * 78)
    print(f"MISSING={missing}  FUNC-DRIFT={drift}  桶分布={dict(sorted(buckets.items()))}")
    print(f"合计 {sum(buckets.values())} 条")

    out = {
        "missing": missing,
        "func_drift": drift,
        "buckets": buckets,
        "targets": [
            {"file": f, "line": l, "func": fn} for f, l, fn in TARGETS
        ],
    }
    (TOOLS / "verify_p2_35_batch34_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if (missing == 0 and drift == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
