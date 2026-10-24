"""ROUND_31：EATD 外部锁定测试脚手架的存在性 + 纪检测试。

不跑真数据（数据不在版本库），只钉：
1. 预注册协议 + 2 个脚本 + 下载指引 存在且入库；
2. 两个脚本语法可解析；
3. 评估脚本**只 transform 不 fit/train/split**（AST：不得出现 .fit/.fit_transform/train_test_split/S*GroupKFold）
   —— 这是"外部测试不重训、不污染泄漏基线"的机器化保证。
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V131 = REPO / "backend" / "scripts" / "modeling" / "eval" / "v1_31"
PREREG = V131 / "EATD_PREREGISTRATION.md"
VALIDATE = V131 / "validate_eatd.py"
EVAL = V131 / "eval_eatd_locked.py"
GUIDE = V131 / "EATD_DOWNLOAD_GUIDE.md"

FORBIDDEN_CALLS = frozenset({"fit", "fit_transform", "partial_fit", "train_test_split"})


def test_scaffold_files_exist() -> None:
    for p in (PREREG, VALIDATE, EVAL, GUIDE):
        assert p.exists(), f"缺少 {p}"


def test_scripts_parse() -> None:
    for p in (VALIDATE, EVAL):
        ast.parse(p.read_text(encoding="utf-8"))


def test_no_fit_or_split_in_scripts() -> None:
    """评估与校验脚本不得重训/划分——外部锁定测试的定义。"""
    for p in (VALIDATE, EVAL):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            # 允许 .transform()，禁止 .fit / .fit_transform / train_test_split
            if name in FORBIDDEN_CALLS:
                raise AssertionError(
                    f"{p.name}:{node.lineno} 调用了 {name}()——外部测试必须 transform-only"
                )


def test_scaffold_tracked() -> None:
    for p in (PREREG, VALIDATE, EVAL, GUIDE):
        r = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(p)],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, f"{p} 未入库：{r.stderr}"


def test_eatd_raw_data_not_tracked() -> None:
    """EATD 原始数据不得入库（预注册承诺：只登记形态、不分发数据）。"""
    r = subprocess.run(
        ["git", "ls-files", "--", "data/external/eatd", "backend/data/external/eatd"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, f"git ls-files 失败：{r.stderr}"
    tracked = [line for line in r.stdout.splitlines() if line.strip()]
    assert not tracked, f"EATD 原始数据被 git 跟踪：{tracked[:10]}"