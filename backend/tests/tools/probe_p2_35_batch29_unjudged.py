"""第二十九批存在性核查：按「文件 + handler 所在函数名」精确检索裁定记载。

**为什么不用挑簇器也不用 basename**：前七次实证两者都不可靠——
-挑簇器「文档未提及 = 未裁定」已七次误报；
- basename 更宽松，但短名（`_common` / `training_jobs`）会被别的句子误命中，
  零提及集被压缩到只剩 4 个簇、>=3 条的0 个 —— 明显是把已裁的也算成零提及。

本脚本的口径：某候选算「已裁定」当且仅当它的**函数名**在三份审计文档
（P2_10 / P2_11 / P2_13）任一份中出现；否则算「真新库存候选」。
函数名是裁定文档的登记单位（P2_13 各节均以「文件 L号（函数名）」格式记账），
比文件名更细、也不受短名误命中影响。

同时打印分类器现场重算的桶归属，便于逐条人工核实。
"""

from __future__ import annotations

import ast
import collections
import importlib.util
import json
import os
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
TOOLS = BACKEND / "tests" / "tools"
DOC_PATHS = (
    REPO / "docs" / "P2_10_ROUND10_AUDIT.md",
    REPO / "docs" / "P2_11_ROUND11_AUDIT.md",
    REPO / "docs" / "P2_13_ROUND13_AUDIT.md",
)

# 本批重点关注的簇（零记载 + 条数较多者优先）
FOCUS = (
    "app/api/v1/model_predict/_common.py",
    "app/services/model_predict/training_jobs.py",
    "app/monitoring/dedup_lock.py",
    "app/api/v1/alerts/__init__.py",
    "app/core/cache.py",
    "app/tasks/pdf_report.py",
    "app/api/v1/reports.py",
    "app/core/model_registry_v2.py",
    "app/ml/unified_model_interface.py",
    "app/services/user_data_service.py",
    "app/core/idempotency.py",
    "app/core/safe_pickle.py",
    "app/core/celery_breaker.py",
    "app/core/fire_forget_metrics.py",
    "app/core/kill_switch.py",
    "app/monitoring/dedup.py",
)


def load(modname: str):
    spec = importlib.util.spec_from_file_location(modname, TOOLS / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    scan_mod = load("scan_p2_35_batch6")
    scan_mod.main()  # 重跑 scan 落盘，保证不是陈旧快照
    classify_mod = load("classify_p2_35_batch6")

    docs = "\n".join(p.read_text(encoding="utf-8") for p in DOC_PATHS if p.exists())
    result = json.loads((TOOLS / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8"))
    rows = result["real_list"] + result["probe_list"]

    by_file: dict[str, list[dict]] = collections.defaultdict(list)
    for rec in rows:
        by_file[rec["file"]].append(rec)

    # 逐候选算：所在函数名是否被裁定文档登记过
    unjudged: list[tuple[str, int, str, str]] = []  # (file, line, func, bucket)
    per_file_new: dict[str, int] = collections.Counter()
    per_file_judged: dict[str, int] = collections.Counter()

    for rel in sorted(by_file):
        p = BACKEND / rel
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        for rec in by_file[rel]:
            target = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.lineno == rec["line"]:
                    target = node
                    break
            if target is None:
                continue
            fn_name = classify_mod.enclosing(target, tree)
            body_src = classify_mod.unparse(target)
            func_src = ""
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_name:
                    if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                        func_src = classify_mod.unparse(fn)
            bucket = classify_mod.classify(rec, body_src, func_src)
            judged = bool(fn_name) and fn_name in docs
            if judged:
                per_file_judged[rel] += 1
            else:
                per_file_new[rel] += 1
                unjudged.append((rel, rec["line"], fn_name, bucket))

    print("\n" + "=" * 78)
    print("按「函数名是否被裁定文档登记」分簇（新库存 = 该簇有函数名未被登记者）")
    print("=" * 78)
    rank = sorted(
        by_file,
        key=lambda f: (-per_file_new.get(f, 0), -len(by_file[f])),
    )
    for rel in rank:
        tag = "★新库存" if per_file_new.get(rel) else "已裁"
        focus = "  <<本批关注" if rel in FOCUS else ""
        print(
            f"{tag}  total={len(by_file[rel]):2d} new={per_file_new.get(rel, 0):2d} "
            f"judged={per_file_judged.get(rel, 0):2d}  {rel}{focus}"
        )

    print("\n" + "=" * 78)
    print(f"真新库存候选合计 {len(unjudged)} 条：")
    print("=" * 78)
    buckets = collections.Counter(b for *_, b in unjudged)
    print("机器桶分布:", dict(sorted(buckets.items())))
    for rel, line, fn, bucket in unjudged:
        focus = "  <<" if rel in FOCUS else ""
        print(f"  {rel}:{line}  func={fn}  bucket={bucket}{focus}")

    out = TOOLS / "probe_p2_35_batch29_unjudged.json"
    out.write_text(
        json.dumps(
            {
                "unjudged": [
                    {"file": f, "line": ln, "func": fn, "bucket": b}
                    for f, ln, fn, b in unjudged
                ],
                "counts": dict(buckets),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n落盘: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())