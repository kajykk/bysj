"""
ROUND_28 (T5)：论文数字校验闸门的测试接入。

背景与纪律
----------
论文里每个数字必须能由**已提交产物**一条命令复算（ROUND_28 提示词 §〇）。
`backend/scripts/modeling/eval/verify_thesis_numbers.py` 是这条纪律的机器化：
它从已提交的逐样本 csv / 评估 json **复算**台账 36 条登记的点估计与 95% CI，
再与 `docs/thesis/` 四份文档逐一比对（容差 = 展示精度），任一漂移即红；
黑名单数字无拒绝标记出现在任何论文文档即红。

本测试文件的职责（不重复闸门自身的逻辑，只做「接入 + 只读性 + 存在性」）：
1. **集成证据**：以子进程跑真闸门（`sys.executable` 即本测试运行的解释器，
   不是替身），断言 returncode 0 且输出 "论文数字校验 OK"——这是 CI 里
   「文档数字 == 已提交产物数字」的唯一权威断言；
2. **只读性**：AST 断言闸门源码不含任何写文件调用（write_text/write_bytes/
   mkdir/unlink/rename/rmdir/touch 与 open(..., "w")）——闸门承诺只读，
   否则它会在 CI checkout 里污染工作树；
3. **存在性**：四份论文文档必须存在（闸门对缺失文档的报错是 fail 集合里的
   一条，但缺文件时更应该在这里给出清晰定位）。

为什么不用 mock：本闸门的价值全在「真产物 → 真复算」这一段，mock 掉 csv/json
读取等于把被测对象换成空壳（ROUND_27 的教训：单测绿、缺陷照旧）。因此这里
没有任何 patch；跑的是真实子进程、真实文件、真实 bootstrap（约 20s，可接受）。

复算边界（闸门 docstring 已如实记账，此处仅引述）：
- 点估计/混淆矩阵/AUC 为闸门内**独立实现**（与 v1_29 评估脚本互为交叉验证）；
- bootstrap CI 复用 v1_29 同一抽样序列（rng.randint(0, n, n)、B=10000、seed=42）；
- 「提交产物 == 单命令产物」硬闸门需原始数据集（不在版本库），ROUND_27 未重跑；
- PHQ-9 682 行只做跨文档对齐；敏感性 csv 只验内部一致性。

变异见证：`backend/tests/tools/mutate_p2_55_round28.py`（8 臂 + 末臂 GREEN），
结果日志 `mutate_p2_55_round28_result.log`。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
GATE = BACKEND / "scripts" / "modeling" / "eval" / "verify_thesis_numbers.py"
THESIS = REPO / "docs" / "thesis"

# 闸门 docstring 承诺的只读边界：这些名字一个都不许以「调用」形态出现
WRITE_CALLS = frozenset({
    "write_text", "write_bytes", "mkdir", "makedirs",
    "unlink", "rename", "rmdir", "touch", "remove", "rmtree",
})


class TestThesisNumbersGate:
    """论文数字校验闸门（ROUND_28 / P2-55）。"""

    def test_gate_passes_on_committed_artifacts(self) -> None:
        """真闸门子进程全量跑过：文档数字与已提交产物零漂移。"""
        out = subprocess.run(
            [sys.executable, str(GATE)],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert out.returncode == 0, (
            "论文数字校验未通过（文档与已提交产物漂移，或产物缺失）：\n"
            f"STDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}"
        )
        assert "论文数字校验 OK" in out.stdout, out.stdout

    def test_gate_source_is_read_only(self) -> None:
        """AST 断言闸门只读：无写文件调用、无 open(..., 'w')。"""
        tree = ast.parse(GATE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            else:
                continue
            assert name not in WRITE_CALLS, (
                f"闸门第 {node.lineno} 行调用 {name}()——只读承诺被破坏"
            )
            if name == "open":
                modes = [a for a in node.args[1:2]]
                for arg in modes:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert not any(ch in arg.value for ch in "wax+"), (
                            f"闸门第 {node.lineno} 行以写模式 open()——只读承诺被破坏"
                        )

    def test_thesis_docs_exist(self) -> None:
        """四份论文文档必须存在（缺任何一份，论文数字纪律即无载体）。"""
        for name in ("CLAIMS_LEDGER.md", "RESULTS_CHAPTER.md",
                     "REVIEWER_QA.md", "LIMITATIONS.md"):
            path = THESIS / name
            assert path.exists(), f"缺少论文文档：{path}"


def test_gate_script_exists() -> None:
    """闸门脚本本身必须入库且在预期路径。"""
    assert GATE.exists(), f"缺少闸门脚本：{GATE}"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(GATE)],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    assert tracked.returncode == 0, (
        f"闸门脚本未入库（CI checkout 里不存在它，闸门形同虚设）：{tracked.stderr}"
    )
