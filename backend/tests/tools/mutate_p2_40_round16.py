"""ROUND_16 变异验证：每个新增闸门必须被真实变异打红（RED-OK），还原后复绿（GREEN-OK）.

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/mutate_p2_40_round16.py

铁律：
- 变异只改实现、必须能翻转某条断言的真值空间；
- 每个变异 try/finally 还原（无论红绿）；
- 先跑基线（未变异全绿）再做变异；任何残留用 git hash-object 判定。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
GATE = "tests/test_p2_40_model_validation_round16.py"
LOG = Path(__file__).resolve().parent / "mutate_p2_40_round16_result.log"

METRICS_JSON = BACKEND_ROOT / "models" / "text" / "improved_bilingual_metrics.json"
V127_SCRIPT = (
    REPO_ROOT / "backend" / "scripts" / "modeling" / "v1_27" / "04_retrain_bilingual_text_groupwise.py"
)
FUSION_ENGINE = BACKEND_ROOT / "app" / "ml" / "fusion_engine.py"
SSOT = BACKEND_ROOT / "app" / "core" / "ml_decision_thresholds.py"
RISK_THRESHOLDS = BACKEND_ROOT / "app" / "core" / "risk_thresholds.py"
MODEL_VALIDATION = BACKEND_ROOT / "app" / "ml" / "model_validation.py"
FUSION_ABLATION = BACKEND_ROOT / "app" / "ml" / "fusion_ablation.py"

LINES: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LINES.append(msg)


def run_gate() -> tuple[int, str]:
    proc = subprocess.run(
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
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"锚点未命中: {path}: {old[:60]!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def restore(path: Path, original: str, mutated: str) -> None:
    """把 mutated 串换回 original（参数顺序 = (原始, 变异后)，与 mutate 相反）."""
    text = path.read_text(encoding="utf-8")
    assert mutated in text, f"还原锚点未命中: {path}: {mutated[:60]!r}"
    path.write_text(text.replace(mutated, original, 1), encoding="utf-8")


def gate_red_for(expected_substr: str) -> bool:
    """变异后必须：returncode!=0 且 FAILED 行中含目标测试（查全量输出，非尾部几行）."""
    code, out = run_gate()
    failed_lines = [ln for ln in out.splitlines() if "FAILED" in ln]
    hit = any(expected_substr in ln for ln in failed_lines)
    ok = code != 0 and hit
    log(f"    returncode={code} | 失败 {len(failed_lines)} 项 | 含目标 '{expected_substr}': {'RED-OK' if ok else 'UNEXPECTED'}")
    for ln in failed_lines[:5]:
        log(f"      {ln.strip()}")
    if code == 0:
        log("    !!! 假绿：变异后闸门仍全绿")
    return ok


def main() -> None:
    code, out = run_gate()
    log(f"[baseline] 未变异 returncode={code}（0=全绿）")
    log(f"[baseline] {out.strip().splitlines()[-1] if out.strip() else ''}")
    assert code == 0, "基线不为绿，先修复再变异"

    results: dict[str, bool] = {}

    # ── M1: metrics JSON headline 口径漂移 0.5→0.3 ─────────────────────
    log("\n[M1] metrics.json headline_eval_threshold 0.5 → 0.3（口径漂移）")
    old = '"headline_eval_threshold": 0.5,'
    new = '"headline_eval_threshold": 0.3,'
    try:
        mutate(METRICS_JSON, old, new)
        results["M1"] = gate_red_for("headline_matches_stated_eval_threshold")
    finally:
        restore(METRICS_JSON, old, new)

    # ── M2: 脚本 headline 阈值常量漂移 ─────────────────────────────────
    log("\n[M2] v1_27 脚本 HEADLINE_EVAL_THRESHOLD 0.5 → 0.3")
    old = "HEADLINE_EVAL_THRESHOLD: float = 0.5"
    new = "HEADLINE_EVAL_THRESHOLD: float = 0.3"
    try:
        mutate(V127_SCRIPT, old, new)
        results["M2"] = gate_red_for("script_headline_threshold_pinned_by_ast")
    finally:
        restore(V127_SCRIPT, old, new)

    # ── M3: fusion_engine 死副本复活 ───────────────────────────────────
    log("\n[M3] fusion_engine 复活 CONFIDENCE_THRESHOLDS 死副本")
    anchor = "# Default fusion weights"
    dead = (
        '# Confidence thresholds\nCONFIDENCE_THRESHOLDS = {\n    "high": 0.8,\n    "medium": 0.5,\n    "low": 0.3,\n}\n\n'
    )
    try:
        mutate(FUSION_ENGINE, anchor, dead + anchor)
        results["M3"] = gate_red_for("no_confidence_thresholds_constant")
    finally:
        restore(FUSION_ENGINE, anchor, dead + anchor)

    # ── M4: SSOT 常量单边漂移（JSON 三方锁必须抓）─────────────────────
    log("\n[M4] SSOT TEXT_BILINGUAL_DECISION_THRESHOLD 0.30 → 0.31")
    old = "TEXT_BILINGUAL_DECISION_THRESHOLD: float = 0.30"
    new = "TEXT_BILINGUAL_DECISION_THRESHOLD: float = 0.31"
    try:
        mutate(SSOT, old, new)
        results["M4"] = gate_red_for("decision_threshold_matches_production")
    finally:
        restore(SSOT, old, new)

    # ── M5: 漏报安全网中性化 ───────────────────────────────────────────
    log("\n[M5] apply_false_negative_safety_net 中性化（恒返回原等级+免复核=False）")
    old = """    level = int(risk_level)
    requires_review = False
    if crisis_signal:
        level = max(level, CRISIS_FORCED_RISK_LEVEL)
        requires_review = True
    if review_signal:
        level = max(level, FN_SAFETY_MIN_LEVEL)
        requires_review = True
    return level, requires_review"""
    new = """    return int(risk_level), False"""
    try:
        mutate(RISK_THRESHOLDS, old, new)
        results["M5"] = gate_red_for("crisis_signal_never_drops_to_level_zero")
    finally:
        restore(RISK_THRESHOLDS, old, new)

    # ── M6: DCA 净获益公式符号翻转（FP 项加减颠倒）─────────────────────
    log("\n[M6] DCA 公式 nb_model = TP/n − FP/n·pt 的减号改加号")
    old = "        nb_model = tp / n - fp / n * pt"
    new = "        nb_model = tp / n + fp / n * pt"
    try:
        mutate(MODEL_VALIDATION, old, new)
        results["M6"] = gate_red_for("net_benefit_matches_vickers_formula")
    finally:
        restore(MODEL_VALIDATION, old, new)

    # ── M7: 公平性 fnr_gap 读数移除 ────────────────────────────────────
    log("\n[M7] compute_fairness_metrics 移除 fnr_gap 读数")
    old = '        disparities["fnr_gap"] = round(tpr_gap, 4)  # FNR = 1 − TPR，组间差与 TPR 差相同'
    new = "        pass  # M7: fnr_gap 读数被移除"
    try:
        mutate(MODEL_VALIDATION, old, new)
        results["M7"] = gate_red_for("include_standard_fairness_gaps")
    finally:
        restore(MODEL_VALIDATION, old, new)

    # ── M8: ΔAUROC CI 覆盖 0 判据恒真 ─────────────────────────────────
    log("\n[M8] paired_delta_auc_ci 恒 ci_covers_zero=True（判据失效）")
    old = "    auc_new = float(roc_auc_score(y_true, scores_new))\n    auc_base = float(roc_auc_score(y_true, scores_base))"
    new = "    return {\n        \"delta\": 0.0,\n        \"ci\": [0.0, 0.0],\n        \"ci_covers_zero\": True,\n        \"n_bootstrap_valid\": 0,\n    }\n    auc_new = float(roc_auc_score(y_true, scores_new))\n    auc_base = float(roc_auc_score(y_true, scores_base))"
    try:
        mutate(FUSION_ABLATION, old, new)
        results["M8"] = gate_red_for("excludes_zero_on_consistent_gap")
    finally:
        restore(FUSION_ABLATION, old, new)

    # ── M9: 分组 K 折退化为普通 K 折（组跨折泄漏——真行为变异）──────────
    # 教训：旁路内部 overlap 校验是**无效变异**（ StratifiedGroupKFold 本身
    # 不拆组，旁路后行为不变 ⇒ 测试仍绿）。必须翻转可观测行为本身：
    # 换成不感知 groups 的 KFold，组即跨折 ⇒ 断言红。
    log("\n[M9] groupwise_kfold_indices 的 StratifiedGroupKFold → KFold（组跨折泄漏）")
    orig_import = "    from sklearn.model_selection import StratifiedGroupKFold"
    mut_import = "    from sklearn.model_selection import KFold, StratifiedGroupKFold"
    orig_split = "    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)"
    mut_split = "    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)"
    try:
        mutate(FUSION_ABLATION, orig_import, mut_import)
        mutate(FUSION_ABLATION, orig_split, mut_split)
        results["M9"] = gate_red_for("never_splits_a_group")
    finally:
        restore(FUSION_ABLATION, orig_split, mut_split)
        restore(FUSION_ABLATION, orig_import, mut_import)

    # ── 收尾：还原后复绿 + 残留判定（变异标志串必须归零）────────────────
    code, _out = run_gate()
    log(f"\n[final] 全部还原后 returncode={code}（0=GREEN-OK）")
    green_ok = code == 0

    log("\n[residual-check] 变异标志串计数（全部应为 0；文件本含本轮合法改动，"
        "故不用 hash 对比 HEAD。注意标记须防子串误报）:")
    markers = [
        (FUSION_ENGINE, '\nCONFIDENCE_THRESHOLDS = {', "M3 死副本定义（注释内引用不算，故加换行前缀）"),
        (METRICS_JSON, '"headline_eval_threshold": 0.3,', "M1 JSON 口径漂移"),
        (V127_SCRIPT, "HEADLINE_EVAL_THRESHOLD: float = 0.3", "M2 脚本常量漂移"),
        (SSOT, "TEXT_BILINGUAL_DECISION_THRESHOLD: float = 0.31", "M4 SSOT 单边漂移"),
        (RISK_THRESHOLDS, "return int(risk_level), False", "M5 安全网中性化"),
        (MODEL_VALIDATION, "nb_model = tp / n + fp / n * pt", "M6 DCA 公式符号翻转"),
        (MODEL_VALIDATION, "pass  # M7: fnr_gap", "M7 fnr_gap 移除"),
        (FUSION_ABLATION, '"ci_covers_zero": True,\n        "n_bootstrap_valid": 0,\n    }\n    auc_new', "M8 ΔCI 判据恒真"),
        (FUSION_ABLATION, "    splitter = KFold(n_splits=", "M9 分组退化为 KFold（防 StratifiedGroupKFold 子串误报）"),
    ]
    residual_ok = True
    for path, marker, label in markers:
        cnt = path.read_text(encoding="utf-8").count(marker)
        if cnt:
            residual_ok = False
        log(f"    {'OK ' if cnt == 0 else '!!!'} {label}: {cnt}")

    red_count = sum(1 for v in results.values() if v)
    log(f"\n[summary] RED-OK {red_count}/{len(results)} | final GREEN-OK={green_ok} | residual-clean={residual_ok}")
    for k, v in results.items():
        log(f"    {k}: {'RED-OK' if v else '!!! 未红'}")

    LOG.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[written] {LOG}")
    if red_count != len(results) or not green_ok or not residual_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
