"""方向 B：全仓 ML 评估入口的泄漏/选择偏差粗排扫描器。

用途：产出**候选清单**，不是裁定结论。
- 扫描所有 .py 中 sklearn 划分/交叉验证调用点
- 按「是否按组分 / 是否随机划分 / 阈值是否在评估集上选」三类打标
- 输出 JSON 到 stdout 或 -o 指定文件

纪律：
1. 调用提取一律 AST（文本扫描会命中自己的 docstring）
2. 本脚本只做粗排，**每条候选必须人工核对后才进审计清单**
3. 退出码 0 表示扫描完成（不代表无风险）

用法：
    .venv/Scripts/python.exe tests/tools/leakage_audit_scan.py
    .venv/Scripts/python.exe tests/tools/leakage_audit_scan.py -o pool_leakage.json
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
BE = BACKEND
BEPKG = BE / "app"

# 扫描范围：仓库根 + backend，排除第三方/产物目录
EXCLUDE_PARTS = {
    "node_modules",
    ".venv",
    "venv",
    "htmlcov",
    ".git",
    "__pycache__",
    "site-packages",
    "dist",
    "build",
    ".hypothesis",
    "catboost_info",
    # 第三方仓库副本（datasets/external/...），不属本仓自研评估口径
    "external",
}

# 划分/交叉验证入口
SPLIT_CALLS = {
    "train_test_split",
    "KFold",
    "GroupKFold",
    "StratifiedKFold",
    "StratifiedGroupKFold",
    "ShuffleSplit",
    "GroupShuffleSplit",
    "LeaveOneGroupOut",
    "LeavePGroupsOut",
    "TimeSeriesSplit",
    "cross_val_score",
    "cross_validate",
    "cross_val_predict",
}

# 天然支持 groups 的划分器/方式 ⇒ 视为安全（前提是 groups 真的传了）
GROUP_AWARE = {
    "GroupKFold",
    "StratifiedGroupKFold",
    "LeaveOneGroupOut",
    "LeavePGroupsOut",
    "GroupShuffleSplit",
}

# 不支持 groups 参数的入口 ⇒ 无法按组分，天然风险
GROUP_INCAPABLE = {
    "train_test_split",
    "KFold",
    "StratifiedKFold",
    "ShuffleSplit",
    "TimeSeriesSplit",
}

# 阈值/超参在评估集上挑优的可疑信号（AST 层面只抓明显的名字）
THRESHOLD_PICKING_HINTS = {
    "best_threshold",
    "best_f1",
    "best_thresh",
    "optimal_threshold",
    "tune_threshold",
    "select_threshold",
    "best_score",
    "max_f1",
}


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def _iter_py_files() -> list[Path]:
    """只扫 **git 跟踪的** .py 文件。

    为什么不用 `rglob`（2026-10-19 CI 红的实锤）：
    `rglob` 扫的是**本机工作树**，会把未入库的 .py 也算进候选。
    本机 42 个候选中有 3 个未入库（`models/train_tabular_depression.py`、
    `models/train_text_depression_classifier.py`、`scripts/deep_analysis_fix.py`），
    而 CI 的干净 checkout 只有入库的 39 个 ⇒ 清单棘轮在 CI 上必红。

    审计的对象是**交付形态**（入库脚本），不是本机碰巧存在的文件，
    因此以 `git ls-files` 为唯一事实源。
    """
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-files 失败（审计清单必须以 git 跟踪文件为准）：{proc.stderr[:200]}"
        )

    out: list[Path] = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel.endswith(".py"):
            continue
        parts = PurePosixPath(rel).parts
        if any(part in EXCLUDE_PARTS for part in parts):
            continue
        p = REPO / PurePosixPath(rel)
        if p.exists():
            out.append(p)
    return sorted(set(out))


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _kwarg_keys(node: ast.Call) -> set[str]:
    return {kw.arg for kw in node.keywords if kw.arg}


def _is_test_file(rel: str) -> bool:
    return rel.startswith("backend/tests/") or rel.startswith("tests/") or "/tests/" in rel


def scan_file(p: Path) -> list[dict]:
    rel = _rel(p)
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except (SyntaxError, UnicodeDecodeError):
        return []

    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in SPLIT_CALLS:
            continue
        kws = _kwarg_keys(node)
        has_groups = "groups" in kws

        if name in GROUP_AWARE:
            risk = "ok" if has_groups else "group_aware_without_groups"
        elif name in GROUP_INCAPABLE:
            risk = "random_split_no_groups"
        else:
            # cross_val_* 系列：看 cv 是否为 group-aware
            cv_val = None
            for kw in node.keywords:
                if kw.arg == "cv" and isinstance(kw.value, ast.Call):
                    cv_val = _call_name(kw.value)
                elif kw.arg == "cv" and isinstance(kw.value, ast.Name):
                    cv_val = kw.value.id
            if cv_val in GROUP_AWARE and has_groups:
                risk = "ok"
            elif cv_val in GROUP_AWARE:
                risk = "group_aware_without_groups"
            else:
                risk = "random_split_no_groups"

        findings.append(
            {
                "file": rel,
                "line": node.lineno,
                "call": name,
                "kwargs": sorted(kws),
                "has_groups": has_groups,
                "risk": risk,
                "in_test": _is_test_file(rel),
            }
        )

    # 阈值在评估集上挑优的可疑信号（按 Assign 目标名抓）
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in THRESHOLD_PICKING_HINTS:
                    findings.append(
                        {
                            "file": rel,
                            "line": node.lineno,
                            "call": f"<assign:{t.id}>",
                            "kwargs": [],
                            "has_groups": False,
                            "risk": "threshold_picking",
                            "in_test": _is_test_file(rel),
                        }
                    )
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", help="输出 JSON 路径")
    ap.add_argument("--include-tests", action="store_true", help="包含 tests/ 下的调用")
    args = ap.parse_args()

    findings: list[dict] = []
    for p in _iter_py_files():
        findings += scan_file(p)

    if not args.include_tests:
        findings = [f for f in findings if not f["in_test"]]

    findings.sort(key=lambda x: (x["file"], x["line"]))

    by_risk: dict[str, list[dict]] = {}
    for f in findings:
        by_risk.setdefault(f["risk"], []).append(f)

    summary = {
        "total_findings": len(findings),
        "by_risk": {k: len(v) for k, v in sorted(by_risk.items())},
        "files_touched": len({f["file"] for f in findings}),
    }

    payload = {"summary": summary, "findings": findings, "by_risk": by_risk}
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[leakage-scan] 写入 {args.out}: {summary}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
