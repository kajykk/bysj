"""作品集最小闭环演示（ROUND_22 / T3）。

一条命令跑通三件事，把本项目的方法论演示成可执行的东西：

    [1/3] 审计 —— `git ls-files` + AST 盘清全仓 ML 划分/挑优入口
    [2/3] 闸门 —— 泄漏守卫（G5 目标泄漏）+ 鉴权入口闸门 + 文档数字自检
    [3/3] 变异 —— 删掉一个标签派生特征的登记，闸门**必须**变红；
                  还原后**必须**回绿（证明闸门不是摆设）

用法：

    cd backend
    python tests/tools/portfolio_demo.py

退出码 0 表示三步全部符合预期。第 3 步会临时改写
`scripts/modeling/v1_24/01_build_mmpsy_features.py`，用字节快照 + try/finally
还原；中断（Ctrl-C）同样会走 finally 还原。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent

GATE_FILES = (
    "tests/test_p2_38_leakage_audit_guard.py",
    "tests/test_p2_41_round17_auth_gate.py",
    "tests/test_p2_46_round22_portfolio_docs.py",
)
MUTATION_TARGET = "tests/test_p2_38_leakage_audit_guard.py::TestG5TargetLeakageCommitGate"
LEAKY_SCRIPT = BACKEND / "scripts" / "modeling" / "v1_24" / "01_build_mmpsy_features.py"

# 变异锚点：把标签派生特征登记表整体清空（强变异：登记集合 ∅，而派生分支仍在）
MUTATION_OLD = """LABEL_DERIVED_FEATURES: dict[str, str] = {
    "stress_level": (
        "⛔ 标签同源：round(phq9_score / 27.0 * 5.0, 4)，而标签 "
        "phq9_binary = (phq9_score >= 10)。实测 corr=1.0、单特征 AUC=1.0000 "
        "⇒ L4 目标泄漏，禁止进入任何评估。"
    ),
}"""
MUTATION_NEW = "LABEL_DERIVED_FEATURES: dict[str, str] = {}"


def _load_checker():
    """复用数字自检脚本里的扫描探针（同一份口径，不重复实现）。"""
    import importlib.util

    name = "check_portfolio_numbers_for_demo"
    spec = importlib.util.spec_from_file_location(
        name, TOOLS / "check_portfolio_numbers.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("无法加载 check_portfolio_numbers.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass 解析字符串注解时需要
    spec.loader.exec_module(module)
    return module


def _run_pytest(targets: tuple[str, ...] | list[str]) -> tuple[int, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=--strict-markers --import-mode=importlib --ignore=functional_test.py",
        "-p",
        "no:cacheprovider",
        "-q",
        *targets,
    ]
    proc = subprocess.run(cmd, cwd=str(BACKEND), capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def _tail(text: str) -> str:
    """取出 pytest 的结论行（形如 `16 passed, 31 warnings in 22.56s`）。

    只认"以数字开头 + passed/failed/error"的行：否则会把 warning 里出现的
    `onerror` 之类的词误当结论（首版就踩过）。
    """
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if re.match(r"^\d+ (passed|failed|error)", stripped):
            return stripped
        if re.match(r"^=+ .*(passed|failed|error)", stripped):
            return stripped
    return text.strip().splitlines()[-1] if text.strip() else "<无输出>"


def step_audit() -> bool:
    print("[1/3] 审计  git ls-files + AST 扫描 ML 划分/挑优入口 ...", flush=True)
    stats = _load_checker().probe_scan()
    print(
        f"      → {stats['files']} 个交付脚本 / {stats['entries']} 处调用点"
        f"（口径：排除 tests/，只认 git 跟踪文件）"
    )
    ok = stats["files"] > 0 and stats["entries"] > 0
    print(f"      {'OK' if ok else 'FAIL：审计没扫到任何入口，检查 git 与路径常量'}")
    return ok


def step_gates() -> bool:
    print("[2/3] 闸门  泄漏守卫 + 鉴权入口 + 文档数字自检 ...", flush=True)
    code, out = _run_pytest(GATE_FILES)
    print(f"      → {_tail(out)}")
    ok = code == 0
    print(f"      {'OK' if ok else 'FAIL：闸门未全绿'}")
    if not ok:
        print(out[-2000:])
    return ok


def step_mutation() -> bool:
    print("[3/3] 变异  清空 LABEL_DERIVED_FEATURES（L4 目标泄漏登记表）...", flush=True)
    snapshot = LEAKY_SCRIPT.read_bytes()
    text = snapshot.decode("utf-8")
    # 仓库在 Windows 上是 CRLF（git 的 autocrlf），锚点按文件实际换行符拼接，
    # 否则 `\n` 版本永远匹配不上 —— 首版就因此误报"锚点不存在"。
    newline = "\r\n" if "\r\n" in text else "\n"
    anchor = MUTATION_OLD.replace("\n", newline)
    if anchor not in text:
        print("      SKIP：变异锚点不存在（护栏脚本已改名，请同步本脚本）")
        return False

    try:
        mutated = text.replace(anchor, MUTATION_NEW)
        LEAKY_SCRIPT.write_bytes(mutated.encode("utf-8"))
        red_code, red_out = _run_pytest((MUTATION_TARGET,))
        red_ok = red_code != 0
        print(f"      → 变异后：{_tail(red_out)}")
        print(f"      {'RED（符合预期）' if red_ok else 'GREEN（不符合预期：闸门没抓住！）'}")
    finally:
        LEAKY_SCRIPT.write_bytes(snapshot)
        restored = LEAKY_SCRIPT.read_bytes() == snapshot
    print(f"      → 还原：{'字节一致' if restored else '还原失败'}")

    if not restored:
        return False
    green_code, green_out = _run_pytest((MUTATION_TARGET,))
    print(f"      → 还原后：{_tail(green_out)}")
    green_ok = green_code == 0
    print(f"      {'OK' if green_ok else 'FAIL：还原后闸门仍是红的'}")
    return red_ok and green_ok


def main() -> int:
    print("=" * 68)
    print("作品集最小闭环：审计 → 闸门 → 变异见证")
    print("=" * 68)
    results = [step_audit(), step_gates(), step_mutation()]
    print("-" * 68)
    if all(results):
        print("DEMO OK（三步全部符合预期）")
        return 0
    print(f"DEMO FAIL（通过 {sum(results)}/3）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
