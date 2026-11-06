"""ROUND_34 / S-03：缺 baseline 工件时禁止伪造指标。

缺陷背景：``scripts/compare_text_models.py::evaluate_baseline_model`` 在
tfidf/model pkl 不存在时返回硬编码 F1 0.9681 / AUC 0.98 的「实测外观」
字典（与 evaluate_bert_model 失败返回 None 的口径不一致），绕过 main()
的 ``if bert_metrics is None or baseline_metrics is None: sys.exit(1)``，
直接参与 make_switch_decision 并写入 comparison_report.json 与
switch_decision.txt ⇒ 无数据支撑的模型切换结论。

替换层说明：直接调用**真实函数**，用 tmp_path 造「工件缺失」这一真实
输入，不做 mock。翻转实现（把 return None 改回模拟字典）本用例立即红。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SCRIPT_PATH = REPO_ROOT / "scripts" / "compare_text_models.py"


def test_missing_baseline_artifacts_return_none(tmp_path):
    from scripts.compare_text_models import evaluate_baseline_model

    # tmp_path 里既没有 text_depression_tfidf.pkl 也没有 text_depression_model.pkl
    assert evaluate_baseline_model(tmp_path, [], []) is None


def test_partial_artifacts_also_return_none(tmp_path):
    """只放一个 pkl 仍不得产出指标（防止「有一个就凑合算」的实现蒙混）。"""
    from scripts.compare_text_models import evaluate_baseline_model

    (tmp_path / "text_depression_tfidf.pkl").write_bytes(b"not-a-real-pickle")
    assert evaluate_baseline_model(tmp_path, [], []) is None


def test_no_fabricated_constants_left_in_function():
    """AST：函数体内不得残留伪造指标字面量（docstring/注释不算命中）。"""
    tree = ast.parse(_SCRIPT_PATH.read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_baseline_model"
    )
    literals = {
        node.value
        for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    }
    assert 0.9681 not in literals, "baseline 缺文件时仍在返回硬编码 F1 0.9681"
    assert 0.98 not in literals, "baseline 缺文件时仍在返回硬编码 AUC 0.98"


def test_main_still_fails_closed_on_none():
    """AST：main() 的失败检查不得被删（None 必须导致非 0 退出）。"""
    tree = ast.parse(_SCRIPT_PATH.read_text(encoding="utf-8"))
    main_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    has_guard = any(
        isinstance(node, ast.If)
        and "baseline_metrics is None" in ast.unparse(node.test)
        for node in ast.walk(main_fn)
    )
    assert has_guard, "main() 不再检查 baseline_metrics is None"
