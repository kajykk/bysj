#!/usr/bin/env python
"""ROUND_29 (P2-56) 变异脚本：scaler 一致性闸门（三层）必须红。

设计纪律（继承 mutate_* 惯例）
------------------------------
1. 每个臂只动**一个**漂移点，验证闸门的一类判据；
2. 全部变异在 `try/finally` 里以**字节快照**还原（artifact 不在版本库、
   工作树有预先存在的脏文件，`git checkout --` 不可用）；
3. 闸门是 pytest 模块而非脚本 ⇒ 每臂起**全新子进程**跑 pytest
   （model_loader 有 lru_cache、测试模块有模块级状态，进程内复用会读到
   上一臂的真值——假绿）；
4. 每臂变异后**重生成 .sha256 侧车**，让红落在预期断言上而不是完整性层；
5. 变异字面量 = 修复前存档 `scaler.json.broken_round29` 的**真实坏值**
   （脚本启动时与存档交叉核对），不是凭空编的数；
6. 末臂还原后必须 GREEN——否则前面的红全是环境性假红，整轮作废。

臂位与判据对应
--------------
M1 overall_activity mean→460098.75（域内错配 5 倍，域检盲区）
                            → 第一层（可复现性主闸门）RED
M2 sleep_quality mean→5.4279（越 1-5 量表界）
                            → 第二层（域合理性）RED
M3 sleep_quality scale→2.5924（超 Popoviciu 上界 2.0）
                            → 第二层 RED
M4 n_features_in→12（mean/scale 仍 13 项）
                            → 结构层 RED
M5 交换 heart_rate/systolic_bp 两个 mean（71.41∈[30,220]、
   117.68∈[60,260]，两值均域内合法，第二层抓不到）
                            → 第一层 RED（证明域检盲区确由主闸门兜底）
M6 修复前存档放回生产目录（scaler.json）
                            → TestFixIsInPlace RED
M7（末臂）全部还原           → 必须 GREEN

跑法（结果日志随脚本入库）：
    cd backend
    .venv/Scripts/python.exe tests/tools/mutate_p2_56_round29.py 2>&1 | tee tests/tools/mutate_p2_56_round29_result.log
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
ART = BACKEND / "models" / "artifacts" / "physiological_optimized"
SCALER_JSON = ART / "scaler.json"
SCALER_SHA = ART / "scaler.json.sha256"
ARCHIVE = ART / "scaler.json.broken_round29"
TEST_REL = "tests/test_p2_56_round29_scaler_consistency.py"
# 数据集在仓库根（app/ml/data_loader.py 的 _PROJECT_ROOT 口径），被 .gitignore 整体忽略
DATASET = (
    REPO / "datasets" / "physiological" / "external" / "depresjon_processed"
    / "depresjon_physiological.csv"
)

PYTEST_ARGS = [
    sys.executable, "-m", "pytest", TEST_REL,
    "-o",
    "addopts=--strict-markers --import-mode=importlib "
    "--ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt",
    "-p", "no:cacheprovider", "-q",
]

# 修复前存档的真实坏值（启动时与存档交叉核对；存档不在时以字面量为准）
BROKEN_OVERALL_ACTIVITY_MEAN = 460098.75        # 域内但错配约 5 倍
BROKEN_SLEEP_QUALITY_MEAN = 5.427905082702637   # 越 1-5 量表界
BROKEN_SLEEP_QUALITY_SCALE = 2.5924177169799805  # 超 Popoviciu 上界 (5-1)/2=2.0

# feature_names.json 的顺序下标（与 test_p2_56 的 FEATURE_DOMAINS 同序）
IDX_SLEEP_QUALITY = 1
IDX_HEART_RATE = 3
IDX_SYSTOLIC_BP = 4
IDX_OVERALL_ACTIVITY = 11

# ────────────────────────── 闸门运行（子进程，全新进程） ──────────────────────────


def run_gate() -> tuple[int, str]:
    """跑一次闸门（全新子进程）。返回 (returncode, 合并输出)。"""
    proc = subprocess.run(
        PYTEST_ARGS, cwd=BACKEND, capture_output=True, encoding="utf-8", errors="replace"
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def failed_tests(out: str) -> list[str]:
    """从 -q 短摘要里提 FAILED 行的测试 ID（证明红落在哪一层）。"""
    return [ln.split(" - ")[0].strip() for ln in out.splitlines() if ln.startswith("FAILED ")]


def evidence_line(out: str, fragment: str) -> str:
    """找出包含预期片段的输出行（该层断言的原文）。"""
    for ln in out.splitlines():
        if fragment in ln:
            return ln.strip()
    return ""


# ────────────────────────── 变异原语 ──────────────────────────


def _regen_sidecar() -> None:
    """变异后重生成侧车，让红落在预期断言上而非完整性层。"""
    digest = hashlib.sha256(SCALER_JSON.read_bytes()).hexdigest()
    SCALER_SHA.write_text(f"{digest}  {SCALER_JSON.name}\n", encoding="utf-8")


def _edit_scaler(edit) -> None:
    data = json.loads(SCALER_JSON.read_text(encoding="utf-8"))
    edit(data)
    SCALER_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _regen_sidecar()


def arm_m1() -> None:
    def edit(d: dict) -> None:
        d["mean"][IDX_OVERALL_ACTIVITY] = BROKEN_OVERALL_ACTIVITY_MEAN

    _edit_scaler(edit)


def arm_m2() -> None:
    def edit(d: dict) -> None:
        d["mean"][IDX_SLEEP_QUALITY] = BROKEN_SLEEP_QUALITY_MEAN

    _edit_scaler(edit)


def arm_m3() -> None:
    def edit(d: dict) -> None:
        d["scale"][IDX_SLEEP_QUALITY] = BROKEN_SLEEP_QUALITY_SCALE

    _edit_scaler(edit)


def arm_m4() -> None:
    def edit(d: dict) -> None:
        d["n_features_in"] = 12  # mean/scale 仍 13 项：只有结构层能抓

    _edit_scaler(edit)


def arm_m5() -> None:
    def edit(d: dict) -> None:
        d["mean"][IDX_HEART_RATE], d["mean"][IDX_SYSTOLIC_BP] = (
            d["mean"][IDX_SYSTOLIC_BP],
            d["mean"][IDX_HEART_RATE],
        )

    _edit_scaler(edit)


def arm_m6() -> None:
    SCALER_JSON.write_bytes(ARCHIVE.read_bytes())  # 错把坏工件放回生产目录
    _regen_sidecar()


ARMS = [
    ("M1", "overall_activity mean→460098.75（域内错配 5 倍，域检盲区）", arm_m1,
     "部署 scaler 的 mean 与 train-only 重拟合不一致"),
    ("M2", "sleep_quality mean→5.4279（越 1-5 量表界）", arm_m2,
     "部署 scaler 违反域合法性"),
    ("M3", "sleep_quality scale→2.5924（超 Popoviciu 上界 2.0）", arm_m3,
     "Popoviciu"),
    ("M4", "n_features_in→12（mean/scale 仍 13 项）", arm_m4,
     "n_features_in=12 != 13"),
    ("M5", "交换 heart_rate/systolic_bp 两个 mean（两值均域内合法）", arm_m5,
     "部署 scaler 的 mean 与 train-only 重拟合不一致"),
    ("M6", "修复前存档放回生产目录（scaler.json）", arm_m6,
     "修复未落地"),
]


def main() -> int:
    # ── 前置断言：跑不起来的脚本结论等于没有依据 ──
    for p in (SCALER_JSON, SCALER_SHA):
        assert p.exists(), f"缺少 {p}——artifact 不在，闸门整体 skip，变异无意义"
    assert DATASET.exists(), (
        "数据集不在（.gitignore 分层）——第一层可复现性会 skip，"
        "M1/M5 两条主闸门臂失去判据；本见证只能在数据机器跑"
    )
    assert ARCHIVE.exists(), f"缺少修复前存档 {ARCHIVE.name}（M6 臂与 TestFixIsInPlace 依赖它）"
    probe = subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True)
    assert probe.returncode == 0, "子进程无法 import pytest（managed python 假红防护）"

    # 变异字面量与存档交叉核对（防手抄漂移）
    arc = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    assert arc["mean"][IDX_OVERALL_ACTIVITY] == BROKEN_OVERALL_ACTIVITY_MEAN, (
        f"存档 overall_activity mean={arc['mean'][IDX_OVERALL_ACTIVITY]!r} 与字面量不符"
    )
    assert arc["mean"][IDX_SLEEP_QUALITY] == BROKEN_SLEEP_QUALITY_MEAN, (
        f"存档 sleep_quality mean={arc['mean'][IDX_SLEEP_QUALITY]!r} 与字面量不符"
    )
    assert arc["scale"][IDX_SLEEP_QUALITY] == BROKEN_SLEEP_QUALITY_SCALE, (
        f"存档 sleep_quality scale={arc['scale'][IDX_SLEEP_QUALITY]!r} 与字面量不符"
    )

    touched = [SCALER_JSON, SCALER_SHA]
    initial = {p: p.read_bytes() for p in touched}
    results: list[tuple[str, str, bool, list[str], str]] = []

    for code, desc, fn, expect in ARMS:
        snap = {p: p.read_bytes() for p in touched}
        note = ""
        try:
            fn()
            rc, out = run_gate()
            red = rc != 0
            failed = failed_tests(out)
            ev = evidence_line(out, expect)
            if not red:
                note = "（未拦截！闸门放行了该漂移）"
            elif not ev:
                note = f"（红但未见预期片段 {expect!r}，检查判据是否移位）"
            results.append((code, desc, red, failed, (ev or note)[:150]))
        finally:
            for p, data in snap.items():
                p.write_bytes(data)

    # 末臂：还原后必须 GREEN
    rc, out = run_gate()
    green_ok = rc == 0 and "passed" in out and not failed_tests(out)
    results.append(("M7", "还原后必须 GREEN", green_ok, failed_tests(out),
                    "" if green_ok else (out.strip().splitlines() or [""])[-1][:150]))

    print("=" * 78)
    print("ROUND_29 (P2-56) scaler 一致性闸门 · 变异报告")
    print("=" * 78)
    all_red = True
    for code, desc, red, failed, ev in results:
        if code == "M7":
            continue
        mark = "RED-OK " if red else "GREEN-BAD"
        if not red:
            all_red = False
        print(f"[{mark}] {code} {desc}")
        for t in failed:
            print(f"         FAILED {t}")
        if ev:
            print(f"         证据: {ev}")
    if green_ok:
        print("[GREEN-OK] M7 还原后闸门全绿（前面的红不是环境性假红）")
    else:
        all_red = False
        print("[GREEN-BAD] M7 还原后闸门未全绿——本轮变异结果作废")
    print("-" * 78)
    n_arms = len(ARMS)
    print(f"合计：{n_arms} 臂变异，{sum(1 for r in results if r[0] != 'M7' and r[2])} 臂被拦截；"
          f"末臂 {'GREEN' if green_ok else 'RED'}")

    # 残留检测：与脚本启动时的字节快照比对（防 finally 静默失败）
    residue = False
    for p in touched:
        now = p.read_bytes() if p.exists() else None
        if now != initial[p]:
            print(f"[RESIDUE] {p} 未还原到初始字节！")
            residue = True
    if not residue:
        print("[RESIDUE-OK] scaler.json 与侧车均已字节级还原")
    return 0 if (all_red and green_ok and not residue) else 1


if __name__ == "__main__":
    sys.exit(main())
