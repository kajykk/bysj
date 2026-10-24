#!/usr/bin/env python
"""ROUND_33 校准闸门变异验证（一次性工具，结果见 mutate_round33_calibration_result.log）。

纪律：
- 每个变异在 try/finally 里用字节快照还原，禁用 git checkout --（工作树有未提交改动）。
- 变异与测试不并发；同一时刻只跑一个 pytest。
- 每个新闸门必须有一次真实的「红 → 恢复绿」，否则不算闸门。
- 目标测试只选「快」的子集（纯函数 + 产物自洽），不跑 80s 的 verify 子进程用例。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
LIB = BACKEND / "scripts" / "modeling" / "eval" / "v1_33" / "calibration_lib.py"
SCRIPT = BACKEND / "scripts" / "modeling" / "eval" / "v1_33" / "calibration_analysis.py"
JSON = BACKEND / "scripts" / "modeling" / "eval" / "v1_33" / "calibration_analysis.json"

# 目标测试（变异要杀死的用例）
FUNC_TESTS = [
    "tests/test_p2_59_round33_calibration.py::test_brier_hand_computed",
    "tests/test_p2_59_round33_calibration.py::test_ece_perfectly_calibrated_bins",
    "tests/test_p2_59_round33_calibration.py::test_ece_single_miscalibrated_bin",
    "tests/test_p2_59_round33_calibration.py::test_ece_bin_assignment_edges",
    "tests/test_p2_59_round33_calibration.py::test_ece_weights_by_count_not_equal_bins",
    "tests/test_p2_59_round33_calibration.py::test_dca_net_benefit_formula",
    "tests/test_p2_59_round33_calibration.py::test_dca_rejects_open_interval_thresholds",
    "tests/test_p2_59_round33_calibration.py::test_probability_bounds_enforced",
]
ART_TESTS = [
    "tests/test_p2_59_round33_calibration.py::test_calibration_json_units_and_roles",
    "tests/test_p2_59_round33_calibration.py::test_calibration_slope_has_no_ci",
    "tests/test_p2_59_round33_calibration.py::test_calibration_json_n_matches_csv",
]


def run_pytest(node_ids: list[str]) -> tuple[int, str]:
    cmd = [
        str(PY), "-m", "pytest", *node_ids,
        "-o", "addopts=--strict-markers --import-mode=importlib",
        "-p", "no:cacheprovider", "-q", "--no-header", "-x",
    ]
    proc = subprocess.run(cmd, cwd=str(BACKEND), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def summarize(out: str) -> str:
    keep = []
    for line in out.splitlines():
        s = line.strip()
        if any(k in s for k in ("passed", "failed", "AssertionError", "ValueError", "KeyError")):
            keep.append(s[:150])
    return "\n".join(keep[:6]) or "(无关键行)"


MUTATIONS: list[tuple[str, Path, str, str, list[str]]] = [
    (
        "M1 Brier 公式翻转成 L1（mean|y-p|）",
        LIB,
        "return float(np.mean((p - y) ** 2))",
        "return float(np.mean(np.abs(p - y)))",
        ["tests/test_p2_59_round33_calibration.py::test_brier_hand_computed"],
    ),
    (
        "M2 ECE 去掉样本数加权（退化成按箱平均）",
        LIB,
        "return float(np.sum(weights * np.abs(acc - conf)))",
        "nz = counts > 0\n        return float(np.mean(np.abs(acc[nz] - conf[nz]))) if nz.any() else 0.0",
        ["tests/test_p2_59_round33_calibration.py::test_ece_weights_by_count_not_equal_bins"],
    ),
    (
        "M3 ECE 距离量翻成 |acc+conf|（符号翻转）",
        LIB,
        "return float(np.sum(weights * np.abs(acc - conf)))",
        "return float(np.sum(weights * np.abs(acc + conf)))",
        [
            "tests/test_p2_59_round33_calibration.py::test_ece_perfectly_calibrated_bins",
            "tests/test_p2_59_round33_calibration.py::test_ece_single_miscalibrated_bin",
        ],
    ),
    (
        "M4 DCA 假阳性惩罚符号翻转（加号）",
        LIB,
        "nb_model = tp / n - (fp / n) * odds",
        "nb_model = tp / n + (fp / n) * odds",
        ["tests/test_p2_59_round33_calibration.py::test_dca_net_benefit_formula"],
    ),
    (
        "M5 DCA 阈值放开到闭区间（接受 0/1）",
        LIB,
        '    if np.any((t <= 0.0) | (t >= 1.0)):\n        raise ValueError("阈值必须落在 (0, 1) 开区间")',
        "    if False:\n        raise ValueError",
        ["tests/test_p2_59_round33_calibration.py::test_dca_rejects_open_interval_thresholds"],
    ),
    (
        "M6 概率越界检查被拆掉",
        LIB,
        "    if np.any((p < 0.0) | (p > 1.0)):\n        raise ValueError(\"p 必须落在 [0, 1]：存在越界概率值\")",
        "    if False:\n        raise ValueError",
        ["tests/test_p2_59_round33_calibration.py::test_probability_bounds_enforced"],
    ),
    (
        "M7 transfer 单元口径悄悄升级为 citable",
        SCRIPT,
        '"role": "stress_only",\n            "source": str(ood.relative_to(BACKEND.parent)),',
        '"role": "citable",\n            "source": str(ood.relative_to(BACKEND.parent)),',
        ART_TESTS,
    ),
]


def main() -> int:
    log: list[str] = []
    failures = 0

    # 基线：未变异必须绿（否则 RED 是环境假红）
    rc, out = run_pytest(FUNC_TESTS + ART_TESTS)
    log.append("=== 基线（未变异，必须绿） ===")
    log.append(f"exit = {rc}")
    log.append(summarize(out))
    if rc != 0:
        log.append("!!! 基线就红，后续变异结论无效")
        print("\n".join(log))
        (Path(__file__).with_name("mutate_round33_calibration_result.log")).write_text(
            "\n".join(log) + "\n", encoding="utf-8"
        )
        return 1

    for name, path, old, new, targets in MUTATIONS:
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        hits = text.count(old)
        log.append(f"\n=== {name} ===")
        log.append(f"target = {path.name} | 命中 = {hits}")
        if hits != 1:
            log.append("SKIP：替换点不唯一或未命中，变异无效")
            failures += 1
            continue
        try:
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            # M7 改的是脚本源码，需要重跑脚本刷新 json 才能让产物测试看到变异
            if path == SCRIPT:
                subprocess.run([str(PY), str(SCRIPT)], cwd=str(BACKEND),
                               capture_output=True, text=True)
            rc, out = run_pytest(targets)
            log.append(f"exit = {rc}（期望非 0 = RED）")
            log.append(summarize(out))
            if rc == 0:
                log.append("!!! 变异未被杀死：闸门失效")
                failures += 1
            else:
                log.append("OK：变异被杀死（RED）")
        finally:
            path.write_bytes(original)
            ok = hashlib.sha256(path.read_bytes()).hexdigest() == digest
            log.append(f"还原 sha 一致 = {ok}")
            if not ok:
                failures += 1

    # M7 动过 json ⇒ 恢复后必须重跑脚本，确保产物回到真值
    subprocess.run([str(PY), str(SCRIPT)], cwd=str(BACKEND), capture_output=True, text=True)

    rc, out = run_pytest(FUNC_TESTS + ART_TESTS)
    log.append("\n=== 恢复后 GREEN 对照 ===")
    log.append(f"exit = {rc}（期望 0）")
    log.append(summarize(out))
    if rc != 0:
        failures += 1

    log.append(f"\n===== 结论：{'全部通过' if failures == 0 else f'{failures} 项异常'} =====")
    report = "\n".join(log)
    print(report)
    (Path(__file__).with_name("mutate_round33_calibration_result.log")).write_text(
        report + "\n", encoding="utf-8"
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
