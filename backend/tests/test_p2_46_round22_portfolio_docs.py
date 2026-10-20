"""ROUND_22 / T4：作品集对外材料的数字自检闸门。

判据
----
对外材料（`README.md`、`docs/EVALUATION_TRUST_SUMMARY.md`）里的关键数字，
必须与仓库内可复算的产物一致。检查逻辑放在
`tests/tools/check_portfolio_numbers.py`，本文件只做三件事：

1. 把它接进 CI（否则"文档钉事实"只是本地纪律）；
2. **反弱化**：检查表必须同时覆盖 README 与摘要，且条数不得低于基线
   （防止有人把不好维护的检查删掉，让闸门悄悄变松）；
3. **自证**：造一份被改坏一个数字的 README，闸门必须能指到那一条
   —— 证明它不是"跑一次绿就算过"的摆设。

变异见证（见 `tests/tools/mutate_p2_46_round22.py`）：
直接把 README 里的桶计数 341 改成 342 ⇒ 本文件红；还原后绿。
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent / "tools"
CHECKER = TOOLS / "check_portfolio_numbers.py"

# 检查表条数基线（新增数字时上调；下调必须给出理由）
MIN_CHECKS = 21


def _load_checker():
    name = "check_portfolio_numbers_gate"
    spec = importlib.util.spec_from_file_location(name, CHECKER)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"无法加载 {CHECKER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass 解析字符串注解时需要
    spec.loader.exec_module(module)
    return module


def test_portfolio_numbers_match_repo_artifacts() -> None:
    """文档里的每个关键数字都必须能在仓库里复算出来。"""
    checker = _load_checker()
    failures = checker.run_checks()
    assert failures == [], (
        "对外材料里的数字与仓库产物不一致（改文档或改产物，两边都要动）：\n"
        + "\n".join(f"  - {item}" for item in failures)
    )


def test_checker_covers_all_portfolio_docs() -> None:
    """反弱化：覆盖范围与条数不得悄悄缩水。"""
    checker = _load_checker()
    covered = {check.doc.name for check in checker.CHECKS}
    assert {"README.md", "EVALUATION_TRUST_SUMMARY.md"} <= covered, (
        f"数字自检未覆盖全部对外材料，当前覆盖：{sorted(covered)}"
    )
    assert len(checker.CHECKS) >= MIN_CHECKS, (
        f"数字自检只剩 {len(checker.CHECKS)} 条 < 基线 {MIN_CHECKS}："
        "删检查比改数字更容易让闸门失效"
    )


@pytest.mark.parametrize(
    ("cid", "original", "tampered"),
    [
        ("readme.buckets", "341 处 except 候选", "342 处 except 候选"),
        ("readme.scan", "88 处划分与挑优调用点", "188 处划分与挑优调用点"),
        ("summary.single_auc", "单特征 AUC 1.0000", "单特征 AUC 0.9999"),
    ],
)
def test_gate_catches_single_digit_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cid: str,
    original: str,
    tampered: str,
) -> None:
    """自证：改坏一个数字，闸门必须**指名**报出那一条（而不是整体模糊变红）。"""
    checker = _load_checker()
    target = next(check for check in checker.CHECKS if check.cid == cid)

    text = target.doc.read_text(encoding="utf-8")
    assert original in text, f"自证样本失效：{target.doc.name} 里找不到 {original!r}"
    forged = tmp_path / target.doc.name
    forged.write_text(text.replace(original, tampered), encoding="utf-8")

    patched = tuple(
        dataclasses.replace(check, doc=forged) if check.cid == cid else check
        for check in checker.CHECKS
    )
    monkeypatch.setattr(checker, "CHECKS", patched)

    failures = checker.run_checks()
    assert any(item.startswith(f"[{cid}]") for item in failures), (
        f"改坏 {cid} 后闸门没有指到这一条，实际失败：{failures}"
    )
