#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P2 第十一轮 机制扫描器（#33 / #34 / #35 + 已闭环清单抽验）.

与整改分离：本脚本只产出事实清单，不改任何源码。
口径一律写死在代码里，便于下一轮复算时对得上。
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
TESTS = BACKEND / "tests"


def iter_py(root: Path):
    for p in sorted(root.rglob("*.py")):
        if ".venv" in p.parts or "__pycache__" in p.parts:
            continue
        yield p


def rel(p: Path) -> str:
    return p.relative_to(BACKEND).as_posix()


# ---------------------------------------------------------------- #33
def scan_operation_log() -> dict:
    """OperationLog( 构造点：区分 模型定义 / helper 本体 / 生产构造点 / 测试。"""
    rows = []
    for p in iter_py(BACKEND):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "OperationLog":
                continue
            rows.append({"file": rel(p), "line": node.lineno})
    model_def = [r for r in rows if r["file"].endswith("app/models/admin.py")]
    helper = [r for r in rows if r["file"].endswith("app/core/audit.py")]
    tests = [r for r in rows if r["file"].startswith("tests/")]
    prod = [
        r for r in rows
        if r not in model_def and r not in helper and r not in tests
    ]
    return {
        "total_hits": len(rows),
        "model_definition": model_def,
        "helper_body": helper,
        "tests": len(tests),
        "prod_construct_sites": len(prod),
        "by_file": dict(Counter(r["file"] for r in prod)),
        "prod": prod,
    }


# ---------------------------------------------------------------- #34
SENSITIVE_HINT = re.compile(
    r"(internal|traceback|exc_info|str\(e\)|repr\(|sql|query|password|token|secret|"
    r"stack|debug|path|filename|dsn|url|dsn)",
    re.I,
)


def scan_raise_sites() -> dict:
    """全仓 raise 点分类：HTTPException / ServiceError / 其它内置 / 自定义。"""
    buckets: dict[str, list] = defaultdict(list)
    detail_leak_candidates = []
    for p in iter_py(APP):
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(p))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            exc = node.exc
            if exc is None:
                buckets["bare_re_raise"].append(rel(p) + f":{node.lineno}")
                continue
            if isinstance(exc, ast.Call):
                fn = exc.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None) or ""
                args_src = []
                for a in exc.args:
                    try:
                        args_src.append(ast.unparse(a))
                    except Exception:
                        args_src.append("<unparse>")
                joined = " ".join(args_src)
                if name == "HTTPException":
                    buckets["HTTPException"].append(f"{rel(p)}:{node.lineno}")
                    detail = extract_detail_kw(exc) or joined
                    if SENSITIVE_HINT.search(detail):
                        detail_leak_candidates.append(
                            {"file": rel(p), "line": node.lineno, "detail": detail[:160]}
                        )
                elif name.endswith("ServiceError"):
                    buckets["ServiceError"].append(f"{rel(p)}:{node.lineno}")
                elif name in {"ValueError", "TypeError", "RuntimeError", "PermissionError",
                              "LookupError", "KeyError", "AttributeError", "NotImplementedError"}:
                    buckets["builtin_" + name].append(f"{rel(p)}:{node.lineno}")
                else:
                    buckets["custom_or_other"].append(f"{rel(p)}:{node.lineno}:{name}")
            else:
                buckets["raise_name_only"].append(rel(p) + f":{node.lineno}")
    out = {k: len(v) for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]))}
    return {"counts": out, "detail_leak_candidates": detail_leak_candidates,
            "samples": {k: v[:8] for k, v in buckets.items()}}


def extract_detail_kw(call: ast.Call) -> str | None:
    for kw in call.keywords:
        if kw.arg == "detail":
            try:
                return ast.unparse(kw.value)
            except Exception:
                return None
    return None


# ---------------------------------------------------------------- #35
def scan_silent_except() -> dict:
    """except -> debug/continue/pass/return 候选，区分 ImportError 特性探测 vs 真降级。"""
    real, probe = [], []
    for p in iter_py(APP):
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(p))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            handled = []
            if node.type is None:
                handled = ["<bare>"]
            elif isinstance(node.type, ast.Tuple):
                handled = [getattr(e, "id", getattr(e, "attr", "?")) for e in node.type.elts]
            else:
                handled = [getattr(node.type, "id", getattr(node.type, "attr", "?"))]
            # 静默体判定：只有 pass / continue / return(无值) / logger.debug / logger.warning 无 raise
            body = node.body
            has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
            has_metric = False
            for n in ast.walk(node):
                if isinstance(n, ast.Call):
                    f = n.func
                    nm = getattr(f, "attr", getattr(f, "id", ""))
                    if nm in {"inc", "labels"}:
                        has_metric = True
            logs_debug = False
            for n in ast.walk(node):
                if isinstance(n, ast.Call):
                    f = n.func
                    nm = getattr(f, "attr", getattr(f, "id", ""))
                    if nm in {"debug", "warning"}:
                        logs_debug = True
            silent = (not has_raise) and (
                logs_debug
                or any(isinstance(n, ast.Pass) for n in body)
                or any(isinstance(n, ast.Continue) for n in body)
            )
            if not silent:
                continue
            rec = {
                "file": rel(p),
                "line": node.lineno,
                "handled": handled,
                "has_metric": has_metric,
                "logs_debug": logs_debug,
            }
            if any(h in {"ImportError", "ModuleNotFoundError"} for h in handled):
                probe.append(rec)
            else:
                real.append(rec)
    return {
        "real_candidates": len(real),
        "import_probe": len(probe),
        "real_wired_metric": sum(1 for r in real if r["has_metric"]),
        "real_unwired": [r for r in real if not r["has_metric"]],
        "probe_list": probe,
        "real_list": real,
    }


def scan_metric_definition() -> dict:
    hits = {}
    for p in iter_py(APP):
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if "silent_degradation_total" in src:
            hits[rel(p)] = src.count("silent_degradation_total")
    return hits


def main() -> int:
    result = {
        "operation_log": scan_operation_log(),
        "raise_sites": scan_raise_sites(),
        "silent_except": scan_silent_except(),
        "silent_degradation_total_refs": scan_metric_definition(),
    }
    out = BACKEND / "scripts" / "scan_p2_11_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ol = result["operation_log"]
    print(f"[33] OperationLog( 命中 {ol['total_hits']} = 生产构造点 {ol['prod_construct_sites']} "
          f"+ helper {len(ol['helper_body'])} + 模型定义 {len(ol['model_definition'])} + 测试 {ol['tests']}")
    rs = result["raise_sites"]
    print(f"[34] raise 分类: {json.dumps(rs['counts'], ensure_ascii=False)}")
    print(f"[34] detail 疑似泄漏内部信息候选: {len(rs['detail_leak_candidates'])}")
    se = result["silent_except"]
    print(f"[35] 静默 except 候选: 真降级 {se['real_candidates']} (已接线 {se['real_wired_metric']}) "
          f"/ ImportError 特性探测 {se['import_probe']}")
    print(f"[35] silent_degradation_total 引用文件: {result['silent_degradation_total_refs']}")
    print(f"落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
