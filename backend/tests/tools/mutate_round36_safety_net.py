#!/usr/bin/env python
"""ROUND_36 漏报安全网闸门变异验证（结果见 mutate_round36_safety_net_result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个新闸门必须有一次真实的「红 → 恢复绿」。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
LIB = BACKEND / "scripts" / "modeling" / "eval" / "v1_36" / "safety_net_lib.py"
SCRIPT = BACKEND / "scripts" / "modeling" / "eval" / "v1_36" / "safety_net_analysis.py"

T = "tests/test_p2_60_round36_safety_net.py"


def node(test: str) -> str:
    return f"{T}::{test}"


TARGETS_FAST = [
    node("test_apply_safety_net_hand_computed_with_fp_and_sn"),
    node("test_apply_safety_net_counts_partition"),
    node("test_apply_safety_net_rejects_degenerate_thresholds"),
    node("test_burden_identity_holds_across_grid"),
    node("test_net_recall_identity_holds_across_grid"),
    node("test_double_threshold_cost_equals_single_threshold_at_t_low"),
    node("test_t_high_only_reallocates_between_alert_and_review"),
    node("test_pick_operating_point_respects_preset_target"),
    node("test_pick_operating_point_minimizes_burden_among_feasible"),
    node("test_pick_operating_point_reports_infeasible_honestly"),
    node("test_safety_net_json_uses_posix_source_path"),
    node("test_safety_net_json_structural_identity_self_consistent"),
]


def run_pytest(node_ids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", *node_ids,
         "-o", "addopts=--strict-markers --import-mode=importlib",
         "-p", "no:cacheprovider", "-q", "--no-header", "--tb=no"],
        cwd=str(BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def summarize(out: str) -> str:
    keep = []
    for line in out.splitlines():
        s = line.strip()
        if any(k in s for k in ("passed", "failed", "AssertionError", "ValueError")):
            keep.append(s[:140])
    return "\n".join(keep[:5]) or "(无关键行)"


MUTATIONS: list[tuple[str, Path, str, str, list[str], bool]] = [
    (
        "M1 review_burden 分子用 sn_caught 而非 sn_total（少算阴性送审）",
        LIB,
        '"review_burden": float((tp + fp + sn_total) / n),',
        '"review_burden": float((tp + fp + sn_caught) / n),',
        [node("test_burden_identity_holds_across_grid"),
         node("test_apply_safety_net_hand_computed_with_fp_and_sn")],
        False,
    ),
    (
        "M2 net_recall 分母用 n 而非阳性数 P",
        LIB,
        '"net_recall": float(net_recall),',
        '"net_recall": float((tp + sn_caught) / n),',
        [node("test_apply_safety_net_hand_computed_with_fp_and_sn"),
         node("test_net_recall_identity_holds_across_grid")],
        False,
    ),
    (
        "M3 工作点筛选退回 `x < target`（NaN 逃逸复发）",
        LIB,
        "if not (m[\"net_recall\"] >= target_net_recall):",
        "if m[\"net_recall\"] < target_net_recall:",
        [node("test_pick_operating_point_reports_infeasible_honestly")],
        False,
    ),
    (
        "M4 alert_precision 把安全网样本算进分母（污染预警精确率）",
        LIB,
        '"alert_precision": float(tp / (tp + fp)) if (tp + fp) else float("nan"),',
        '"alert_precision": float(tp / (tp + fp + sn_total)) if (tp + fp + sn_total) else float("nan"),',
        [node("test_apply_safety_net_hand_computed_with_fp_and_sn")],
        False,
    ),
    (
        "M5 sn_precision 用 sn_total 而非 sn_caught（恒等于 1，掩盖无判别力）",
        LIB,
        '"sn_precision": float(sn_caught / sn_total) if sn_total else float("nan"),',
        '"sn_precision": float(sn_total / sn_total) if sn_total else float("nan"),',
        [node("test_apply_safety_net_hand_computed_with_fp_and_sn"),
         node("test_safety_net_sn_precision_below_prevalence_is_reported")],
        False,
    ),
    (
        "M6 放开 0 < t_low < t_high 约束（退化配置可入网）",
        LIB,
        "    if not (0.0 < t_low < t_high < 1.0):\n        raise ValueError(f\"要求 0 < t_low < t_high < 1，收到 {t_low} / {t_high}\")",
        "    if not (0.0 <= t_low <= t_high < 1.0):\n        raise ValueError",
        [node("test_apply_safety_net_rejects_degenerate_thresholds")],
        False,
    ),
    (
        "M7 source 改回 str(Path)（ROUND_33 被 CI 抓出的 Windows 反斜杠缺陷形态）",
        SCRIPT,
        '"source": OOF_CSV.relative_to(BACKEND.parent).as_posix(),',
        '"source": str(OOF_CSV.relative_to(BACKEND.parent)),',
        [node("test_safety_net_json_uses_posix_source_path")],
        True,
    ),
]


def main() -> int:
    log: list[str] = []
    failures = 0

    rc, out = run_pytest(TARGETS_FAST)
    log.append("=== 基线（未变异，必须绿） ===")
    log.append(f"exit = {rc}")
    log.append(summarize(out))
    if rc != 0:
        log.append("!!! 基线就红，后续变异结论无效")
        Path(__file__).with_name("mutate_round36_safety_net_result.log").write_text(
            "\n".join(log) + "\n", encoding="utf-8")
        print("\n".join(log))
        return 1

    for name, path, old, new, targets, needs_rerun in MUTATIONS:
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
            if needs_rerun:
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

    # M7 动过 json ⇒ 恢复后重跑脚本，确保产物回到真值
    subprocess.run([str(PY), str(SCRIPT)], cwd=str(BACKEND), capture_output=True, text=True)

    rc, out = run_pytest(TARGETS_FAST)
    log.append("\n=== 恢复后 GREEN 对照 ===")
    log.append(f"exit = {rc}（期望 0）")
    log.append(summarize(out))
    if rc != 0:
        failures += 1

    log.append(f"\n===== 结论：{'全部通过' if failures == 0 else f'{failures} 项异常'} =====")
    report = "\n".join(log)
    print(report)
    Path(__file__).with_name("mutate_round36_safety_net_result.log").write_text(
        report + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
