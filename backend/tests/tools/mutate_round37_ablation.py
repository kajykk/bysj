#!/usr/bin/env python
"""ROUND_37 融合消融闸门变异验证（结果见 mutate_round37_ablation_result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个新闸门必须有一次真实的「红 → 恢复绿」。
变异对象包含**生产代码**（fusion_engine.py）——那正是本轮验证的主体。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
ENGINE = BACKEND / "app" / "ml" / "fusion_engine.py"
SCRIPT = BACKEND / "scripts" / "modeling" / "eval" / "v1_37" / "fusion_ablation.py"

T = "tests/test_p2_61_round37_fusion_ablation.py"


def node(test: str) -> str:
    return f"{T}::{test}"


TARGETS = [
    node("test_redistribute_sums_to_one"),
    node("test_redistribute_drops_missing_modalities"),
    node("test_redistribute_preserves_relative_ratio"),
    node("test_redistribute_single_modality_gets_full_weight"),
    node("test_redistribute_all_zero_weights_branch_is_unreachable"),
    node("test_fuse_full_three_modality_hand_computed"),
    node("test_fuse_empty_scores_is_safe"),
    node("test_fuse_rejects_non_finite"),
    node("test_fuse_rejects_non_numeric"),
    node("test_ablation_json_summary_matches_recompute"),
    node("test_ablation_json_worst_case_recomputable"),
    node("test_ablation_json_engine_matches_production_defaults"),
    node("test_ablation_json_declares_synthetic_input"),
    node("test_ablation_stratified_pattern_is_monotone"),
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
        if any(k in s for k in ("passed", "failed", "AssertionError", "NameError")):
            keep.append(s[:140])
    return "\n".join(keep[:5]) or "(无关键行)"


MUTATIONS: list[tuple[str, Path, str, str, list[str], bool]] = [
    (
        "M1 redistribute 不再归一化（权重和 <1 ⇒ 融合分系统性偏低）",
        ENGINE,
        "        return {k: v / total for k, v in available_weights.items()}",
        "        return dict(available_weights)",
        [node("test_redistribute_sums_to_one"), node("test_redistribute_preserves_relative_ratio")],
        True,
    ),
    (
        "M2 redistribute 不过滤缺失模态（缺失模态以全权重混入）",
        ENGINE,
        "            k: v for k, v in self.weights.items() if k in available_modalities",
        "            k: v for k, v in self.weights.items()",
        [node("test_redistribute_drops_missing_modalities"),
         node("test_redistribute_single_modality_gets_full_weight")],
        True,
    ),
    (
        "M3 fuse 丢掉 NaN/Inf 拦截（静默裁剪成极端临床结论）",
        ENGINE,
        "            if isinstance(v, bool) or not math.isfinite(v):",
        "            if False:",
        [node("test_fuse_rejects_non_finite"), node("test_fuse_rejects_non_numeric")],
        True,
    ),
    (
        "M4 去掉 bool 拦截（True 会按 1.0 参与融合 ⇒ 静默算出 100 分危机）",
        ENGINE,
        "            if isinstance(v, bool) or not math.isfinite(v):",
        "            if not math.isfinite(v):",
        [node("test_fuse_rejects_non_numeric"), node("test_fuse_rejects_non_finite")],
        True,
    ),
    (
        "M5 空输入不再返回安全默认值",
        ENGINE,
        '                "fusion_scheme": "empty",',
        '                "fusion_scheme": "EMPTY_MUTATED",',
        [node("test_fuse_empty_scores_is_safe")],
        True,
    ),
    (
        "M6 消融脚本改用非生产权重（0.4/0.3/0.3）",
        SCRIPT,
        "    engine = FusionEngine()  # 生产默认权重 + 置信度加权",
        "    engine = FusionEngine(weights={'structured': 0.4, 'text': 0.3, 'physiological': 0.3})",
        [node("test_ablation_json_engine_matches_production_defaults"),
         node("test_ablation_json_summary_matches_recompute")],
        True,
    ),
    (
        "M7 产物声明去掉「合成/非性能」边界（口径悄悄升级）",
        SCRIPT,
        "（合成，非真实样本），验证的是融合层规则的行为边界，不是模型性能；",
        "（真实评估），可直接作为性能证据；",
        [node("test_ablation_json_declares_synthetic_input")],
        True,
    ),
]


def main() -> int:
    log: list[str] = []
    failures = 0

    rc, out = run_pytest(TARGETS)
    log.append("=== 基线（未变异，必须绿） ===")
    log.append(f"exit = {rc}")
    log.append(summarize(out))
    if rc != 0:
        log.append("!!! 基线就红，后续变异结论无效")
        Path(__file__).with_name("mutate_round37_ablation_result.log").write_text(
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

    subprocess.run([str(PY), str(SCRIPT)], cwd=str(BACKEND), capture_output=True, text=True)

    rc, out = run_pytest(TARGETS)
    log.append("\n=== 恢复后 GREEN 对照 ===")
    log.append(f"exit = {rc}（期望 0）")
    log.append(summarize(out))
    if rc != 0:
        failures += 1

    log.append(f"\n===== 结论：{'全部通过' if failures == 0 else f'{failures} 项异常'} =====")
    report = "\n".join(log)
    print(report)
    Path(__file__).with_name("mutate_round37_ablation_result.log").write_text(
        report + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
