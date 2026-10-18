"""P2-38 方向 B 守卫的真实变异验证。

纪律：
  1. 变异必须 **try/finally 还原**（无论红还是假绿）
  2. 变异前先审强度：只翻转实现、没翻转断言真值空间 ⇒ 无效变异，不能用来证明闸门有效
  3. 每个闸门至少一次真实变异（红 → 还原绿）
  4. 变异脚本与常规测试禁止并发跑（sqlite 争用会造假失败）
  5. 工作树有未提交改动时，还原只能用 in-memory 文本回写，禁用 `git checkout --`

变异清单（含强度评估）：
  M1  组级口径退化为随机（_oof_predict 的 groups 分支失效）
      强度【强】：直接废掉分组语义 ⇒ 两口径同形 ⇒ ΔAUC 必变 0
      覆盖：G1.test_synthetic_sibling_leakage_detected
  M2  目标泄漏阈值抬到 2.0（永不报警）
      强度【强】：检测器恒判 ok ⇒ 真实数据锚定断言必红
      覆盖：G2.test_deterministic_derived_feature_flagged / test_real_mmpsy_stress_is_leaky
  M3  去掉反向 AUC 折叠（max(auc, 1-auc) → auc）
      强度【弱→中】：仅当存在「反向单调」特征时才翻转断言真值空间。
      若此变异不红 ⇒ 说明闸门对反向泄漏有盲区 ⇒ 必须补断言（见 M3 备注）。
      覆盖：G2 反向特征盲区
  M4  扫描器取消排除第三方副本目录
      强度【强】：外部仓库文件涌入 ⇒ 清单规模必变
      覆盖：G4.test_scanner_sees_full_inventory

用法：
    cd backend
    .venv/Scripts/python.exe tests/tools/mutate_p2_38_round14.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import uuid
from typing import NamedTuple

BACKEND = pathlib.Path(__file__).resolve().parents[1]
TOOLS = BACKEND / "tests" / "tools"
GATE = "tests/test_p2_38_leakage_audit_guard.py"


class Mutation(NamedTuple):
    mid: str
    desc: str
    target: pathlib.Path
    old: str
    new: str
    expect_red_gates: tuple[str, ...]


PROBE = TOOLS / "leakage_delta_probe.py"
SCAN = TOOLS / "leakage_audit_scan.py"

MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        mid="M1",
        desc="组级口径退化为随机划分（groups 分支失效）",
        target=PROBE,
        old="    if groups is not None:\n        splitter = StratifiedGroupKFold(",
        new="    if False:\n        splitter = StratifiedGroupKFold(",
        expect_red_gates=(
            "TestG1ProbeEffectiveness::test_synthetic_sibling_leakage_detected",
        ),
    ),
    Mutation(
        mid="M2",
        desc="目标泄漏阈值抬到 2.0（检测器恒判 ok）",
        target=PROBE,
        old="    auc_threshold: float = 0.99",
        new="    auc_threshold: float = 2.0",
        expect_red_gates=(
            "TestG2TargetLeakageDetection::test_deterministic_derived_feature_flagged",
            "TestG2TargetLeakageDetection::test_real_mmpsy_stress_is_leaky",
        ),
    ),
    Mutation(
        mid="M3",
        desc="去掉反向 AUC 折叠（仅判正向单调）",
        target=PROBE,
        old="        auc = max(auc, 1.0 - auc)  # 反向也判泄漏",
        new="        auc = auc  # 变异：不折叠反向",
        expect_red_gates=(
            "TestG2TargetLeakageDetection::test_reverse_signed_feature_flagged",
        ),
    ),
    Mutation(
        mid="M4",
        desc="扫描器取消排除 datasets/external 第三方副本",
        target=SCAN,
        old='    # 第三方仓库副本（datasets/external/...），不属本仓自研评估口径\n    "external",\n',
        new="",
        expect_red_gates=(
            "TestG4InventoryCoverageRatchet::test_scanner_sees_full_inventory",
        ),
    ),
)


def _run_gate(basetemp: str) -> tuple[int, str]:
    """跑闸门，返回 (returncode, 输出文本)。

    两处环境坑（均实测）：
    1. **不要用 capture_output=True**：Windows 下 pytest 的子进程会继承 stdout
       管道写端，父进程的 communicate() 要等所有持有者退出才返回 EOF ⇒
       实测挂起 15 分钟以上。改为重定向到文件后读回。
    2. **不要 unlink() 产物文件**：本环境有 safe-delete 钩子，
       对仓库内文件做 trash 操作会 FAIL_CLOSED 抛错。因此日志统一写到
       系统临时目录并**保留**（由系统清理），脚本内不做任何删除。
    """
    # basetemp 必须每次唯一且放在系统临时目录：
    # ① 复用同一名字会撞上 pytest 的 bulk-delete guard（实测挂起）；
    # ② 放在仓库内会污染工作树，且本环境 safe-delete 钩子会拦截删除。
    bt_dir = pathlib.Path(tempfile.gettempdir()) / "p2_38_basetemp"
    bt_dir.mkdir(parents=True, exist_ok=True)
    unique = f"{basetemp}_{uuid.uuid4().hex[:8]}"

    out_path = bt_dir / f"_gate_{unique}.log"
    with out_path.open("w", encoding="utf-8") as fh:
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    GATE,
                    "-o",
                    "addopts=--strict-markers --import-mode=importlib",
                    "-p",
                    "no:cacheprovider",
                    "-q",
                    f"--basetemp={bt_dir / unique}",
                ],
                cwd=str(BACKEND),
                stdout=fh,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=600,
            )
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = 124
    text = out_path.read_text(encoding="utf-8")
    # 故意不删除：本环境 safe-delete 钩子对仓库内文件的 trash 操作会 FAIL_CLOSED。
    # 临时目录由系统清理，脚本保持「只读 + 写」、不做任何删除动作。
    return rc, text


def main() -> int:
    print("=" * 72)
    print("P2-38 方向 B 守卫 —— 真实变异验证")
    print("=" * 72)

    # 0) 基线：未变异必须全绿
    rc, out = _run_gate("bt_mut_base")
    if rc != 0:
        print("[FATAL] 基线未通过，先修闸门再谈变异", file=sys.stderr)
        print(out[-3000:], file=sys.stderr)
        return 1
    print(f"[BASE] 基线全绿 ({out.strip().splitlines()[-1]})\n")

    all_ok = True
    for m in MUTATIONS:
        original = m.target.read_text(encoding="utf-8")
        if m.old not in original:
            print(f"[{m.mid}] 锚点缺失，无法变异：{m.target.name}", file=sys.stderr)
            all_ok = False
            continue

        red_gates: list[str] = []
        try:
            m.target.write_text(original.replace(m.old, m.new, 1), encoding="utf-8")
            rc, out = _run_gate(f"bt_mut_{m.mid}")
            if rc == 0:
                print(f"[{m.mid}] ✗ 假绿：变异后闸门仍全绿 ⇒ 闸门无效")
                all_ok = False
            else:
                red_gates = [
                    line.split(" ")[0]
                    for line in out.splitlines()
                    if line.startswith("FAILED")
                ]
                print(f"[{m.mid}] ✓ 变异后闸门变红")
                for g in red_gates:
                    print(f"        RED {g}")
                missing = set(m.expect_red_gates) - {
                    g.split("::")[-2] + "::" + g.split("::")[-1] for g in red_gates
                }
                if missing:
                    print(f"[{m.mid}] ⚠ 预期红但未红的闸门：{missing}")
                    all_ok = False
        finally:
            m.target.write_text(original, encoding="utf-8")

        # 还原后必须恢复绿
        rc, vout = _run_gate(f"bt_restore_{m.mid}")
        if rc != 0:
            print(vout[-2000:], file=sys.stderr)
            print(f"[{m.mid}] ✗ 还原后未恢复绿 ⇒ 变异残留", file=sys.stderr)
            all_ok = False
        else:
            print(f"[{m.mid}] ✓ 还原后恢复绿\n")

    print("=" * 72)
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES PRESENT")
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
