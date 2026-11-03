#!/usr/bin/env python
"""ROUND_46 P0-5: physiological evaluation boundary and dose-response audit.

The physiological v2 model is a 13-feature numpy MLP evaluated on 157 test rows
from one deterministic split. This script documents:
- how wide the test uncertainty is;
- whether the model's exercise / sleep / heart-rate response is monotonic;
- why the ROUND_45 `corrected_13` candidate (better F1) is not production-ready;
- the raw vs Platt-calibrated test behaviour.

Read-only: no model artifact, threshold, or production behavior is modified.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_46/05_physio_boundary.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
for path in (BACKEND, HERE, PROJECT_ROOT / "scripts" / "ml_training"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.ml.feature_engineering import engineer_features  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    load_cleaner,
    load_feature_names,
    load_model,
    load_scaler,
)

OUT_JSON = HERE / "physio_boundary.json"
MIRROR_JSON = PROJECT_ROOT / "outputs" / "candidates" / "round46" / "physio_boundary.json"
REPORT_MD = PROJECT_ROOT / "outputs" / "ROUND_46_PHYSIO_BOUNDARY.md"
ROUND45_JSON = PROJECT_ROOT / "outputs" / "candidates" / "round45" / "physio_candidates_2026-11-01.json"
THRESHOLD_JSON = HERE / "threshold_decision.json"

RAW_FIELDS = (
    "sleep_hours",
    "sleep_quality",
    "exercise_minutes",
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "steps",
)
BASE = {
    "sleep_hours": 7.0,
    "sleep_quality": 3.0,
    "exercise_minutes": 30.0,
    "heart_rate": 70.0,
    "systolic_bp": 120.0,
    "diastolic_bp": 80.0,
    "steps": 5000.0,
}


def _finite(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return _finite(obj.item())
    return obj


def _load_model_cards_module():
    spec = importlib.util.spec_from_file_location("round46_model_cards", HERE / "01_model_cards.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MC = _load_model_cards_module()


class Scorer:
    def __init__(self):
        self.cleaner = load_cleaner()
        self.scaler = load_scaler()
        self.model = load_model()
        self.feats = load_feature_names()

    def score(self, payload: dict) -> float:
        raw = {**BASE, **payload}
        cleaned = self.cleaner.transform_single(raw)
        engineered = engineer_features(pd.DataFrame([cleaned]))
        x = engineered[self.feats].values.astype(np.float32)
        return float(np.asarray(self.model.predict_proba(self.scaler.transform(x))).reshape(-1)[0])

    def feature_row(self, payload: dict) -> dict:
        raw = {**BASE, **payload}
        cleaned = self.cleaner.transform_single(raw)
        engineered = engineer_features(pd.DataFrame([cleaned]))
        return {k: float(engineered.iloc[0][k]) for k in engineered.columns}


def monotonicity(values, scores) -> dict:
    values = np.asarray(values, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    diff = np.diff(scores)
    sign = np.sign(diff)
    sign_nonzero = sign[sign != 0]
    direction_changes = int(np.sum(sign_nonzero[1:] != sign_nonzero[:-1])) if sign_nonzero.size > 1 else 0
    max_jump_idx = int(np.argmax(np.abs(diff))) if diff.size else 0
    rho = float(spearmanr(values, scores)[0]) if len(np.unique(scores)) > 1 else float("nan")
    return {
        "n_points": int(values.size),
        "min_value": float(values.min()),
        "max_value": float(values.max()),
        "score_at_min": float(scores[0]),
        "score_at_max": float(scores[-1]),
        "score_min": float(scores.min()),
        "score_max": float(scores.max()),
        "score_range": float(scores.max() - scores.min()),
        "max_adjacent_jump": float(np.max(np.abs(diff))) if diff.size else 0.0,
        "max_adjacent_jump_at": [float(values[max_jump_idx]), float(values[max_jump_idx + 1])]
        if diff.size
        else None,
        "direction_changes": direction_changes,
        "monotonic": bool(direction_changes == 0),
        "spearman_rho": rho,
    }


def sweep(scorer: Scorer, field: str, values) -> dict:
    values = list(values)
    scores = [scorer.score({field: v}) for v in values]
    return {
        "field": field,
        "values": [float(v) for v in values],
        "scores": [float(s) for s in scores],
        "monotonicity": monotonicity(values, scores),
    }


def exercise_feature_sweep(scorer: Scorer) -> dict:
    values = list(range(0, 121))
    rows = []
    for v in values:
        feats = scorer.feature_row({"exercise_minutes": float(v)})
        rows.append(
            {
                "exercise_minutes": float(v),
                "activity_intensity": feats["activity_intensity"],
                "overall_activity": feats["overall_activity"],
                "score": scorer.score({"exercise_minutes": float(v)}),
            }
        )
    intensity = [r["activity_intensity"] for r in rows]
    jump_idx = int(np.argmax(np.abs(np.diff(intensity))))
    return {
        "values": values,
        "rows": rows,
        "activity_intensity_max_adjacent_jump": float(
            np.max(np.abs(np.diff(intensity)))
        ),
        "activity_intensity_max_jump_between": [values[jump_idx], values[jump_idx + 1]],
        "note": (
            "activity_intensity = steps / exercise for exercise > 0, and steps when "
            "exercise = 0. With steps fixed at 5000 the feature jumps from 5000 (exercise 1) "
            "to 2500 (exercise 2); the MLP output is not constrained to be monotonic."
        ),
    }


def main() -> int:
    scorer = Scorer()
    df, y, vai, tei, p_val, p_test, feats, max_abs_diff, existing = MC.physio_predictions()
    cards = json.loads((HERE / "model_cards.json").read_text(encoding="utf-8"))
    unit = cards["units"]["physio_v2_current_split"]

    sweeps = {
        "exercise_fixed_steps_5000": sweep(scorer, "exercise_minutes", range(0, 121)),
        "exercise_steps_scale": {
            "field": "exercise_minutes with steps=1000+40*exercise",
            "values": list(range(0, 121)),
            "scores": [
                scorer.score(
                    {"exercise_minutes": float(v), "steps": float(1000 + 40 * v)}
                )
                for v in range(0, 121)
            ],
        },
        "sleep_hours": sweep(scorer, "sleep_hours", [round(3 + 0.1 * i, 1) for i in range(71)]),
        "heart_rate": sweep(scorer, "heart_rate", range(50, 101)),
        "steps_fixed_exercise_30": sweep(scorer, "steps", range(1000, 6601, 100)),
    }
    sweeps["exercise_steps_scale"]["monotonicity"] = monotonicity(
        sweeps["exercise_steps_scale"]["values"], sweeps["exercise_steps_scale"]["scores"]
    )
    exercise_features = exercise_feature_sweep(scorer)

    # test-range coverage vs training range
    raw_train = df.iloc[MC.load_eval01().split_indices(y)[0]][list(RAW_FIELDS)]
    raw_test = df.iloc[tei][list(RAW_FIELDS)]
    range_table = {}
    for col in RAW_FIELDS:
        lo, hi = float(raw_train[col].min()), float(raw_train[col].max())
        outside = int(((raw_test[col] < lo) | (raw_test[col] > hi)).sum())
        range_table[col] = {
            "train_min": lo,
            "train_max": hi,
            "test_min": float(raw_test[col].min()),
            "test_max": float(raw_test[col].max()),
            "test_rows_outside_train_range": outside,
        }

    # ROUND_45 candidate context
    candidate = {}
    if ROUND45_JSON.exists():
        r45 = json.loads(ROUND45_JSON.read_text(encoding="utf-8"))
        for name in ("current_13", "corrected_13", "raw7_bp_8"):
            if name not in r45:
                continue
            candidate[name] = {
                "metrics_test": r45[name]["metrics_test"],
                "exercise_sweep": r45[name]["sweep"]["exercise_minutes"],
                "sleep_sweep": r45[name]["sweep"]["sleep_hours"],
                "note": (
                    "Single deterministic 719/153/157 split; no repeated CV. "
                    "corrected_13 changes activity_intensity to steps/max(exercise,30)."
                ),
            }

    threshold_rows = {}
    if THRESHOLD_JSON.exists():
        td = json.loads(THRESHOLD_JSON.read_text(encoding="utf-8"))
        for row in td["units"]["physio_v2_current_split"]["cuts"]:
            threshold_rows[f"{row['cut']:.2f}"] = {
                "level_onset": row["level_onset"],
                "sensitivity": row["sensitivity"],
                "specificity": row["specificity"],
                "ppv": row["ppv"],
                "ppv_at_15pct": row["ppv_at_15pct"],
                "ci95": row["bootstrap_ci95"],
            }

    verdict = (
        f"生理 v2 测试 n={unit['card']['n']}，AUC={unit['card']['auroc']:.4f} "
        f"(95%CI {unit['bootstrap']['auroc']['ci95'][0]:.3f}-{unit['bootstrap']['auroc']['ci95'][1]:.3f})，"
        f"F1={unit['card']['f1']:.4f} (95%CI {unit['bootstrap']['f1']['ci95'][0]:.3f}-"
        f"{unit['bootstrap']['f1']['ci95'][1]:.3f})，Brier={unit['card']['brier']:.4f}。"
        f"原始概率校准差（ECE={unit['card']['ece']:.4f}，slope={unit['card']['calibration_slope']:.3f}）；"
        f"运动剂量反应非单调（方向反转 {sweeps['exercise_fixed_steps_5000']['monotonicity']['direction_changes']} 次，"
        f"最大相邻跳变 {sweeps['exercise_fixed_steps_5000']['monotonicity']['max_adjacent_jump']:.4f}）。"
        "生理模型只能作次级、小样本内部读数；不得用于运动处方、因果解释或稳定外部验证。"
    )

    payload = {
        "_note": (
            "ROUND_46 P0-5 physiological boundary audit. Read-only. n=157 deterministic "
            "test split; dose-response sweeps are synthetic one-variable-at-a-time profiles, "
            "not causal effects. No model artifact or threshold modified."
        ),
        "reproduction": {
            "production_predictions_reproduced": bool(max_abs_diff < 1e-6),
            "max_abs_diff_vs_artifact_csv": max_abs_diff,
            "n_validation": int(len(vai)),
            "n_test": int(len(tei)),
            "feature_names": feats,
        },
        "model_card": {
            "test_n": unit["card"]["n"],
            "positive_rate": unit["card"]["positive_rate"],
            "auroc": unit["card"]["auroc"],
            "auroc_ci95": unit["bootstrap"]["auroc"]["ci95"],
            "auprc": unit["card"]["auprc"],
            "auprc_ci95": unit["bootstrap"]["auprc"]["ci95"],
            "f1": unit["card"]["f1"],
            "f1_ci95": unit["bootstrap"]["f1"]["ci95"],
            "brier": unit["card"]["brier"],
            "brier_ci95": unit["bootstrap"]["brier"]["ci95"],
            "ece": unit["card"]["ece"],
            "calibration_slope": unit["card"]["calibration_slope"],
            "calibration_intercept": unit["card"]["calibration_intercept"],
        },
        "calibration_candidate": {
            "method": unit["calibration_candidate"]["method"],
            "platt": unit["calibration_candidate"]["platt"],
            "raw": {
                "brier": unit["card"]["brier"],
                "ece": unit["card"]["ece"],
                "slope": unit["card"]["calibration_slope"],
            },
            "platt_on_validation": {
                "brier": unit["calibration_candidate"]["card"]["brier"],
                "ece": unit["calibration_candidate"]["card"]["ece"],
                "slope": unit["calibration_candidate"]["card"]["calibration_slope"],
            },
            "note": "153 validation rows -> 157 test rows; exploratory, not a production calibration.",
        },
        "threshold_rows": threshold_rows,
        "range_check": range_table,
        "dose_response": sweeps,
        "exercise_feature_sweep": exercise_features,
        "round45_candidate": candidate,
        "verdict": verdict,
    }
    cleaned = _finite(payload)
    OUT_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    MIRROR_JSON.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_report(cleaned), encoding="utf-8")

    print("[physio_boundary]")
    print(
        f"  n={unit['card']['n']} AUC={unit['card']['auroc']:.4f} "
        f"CI={unit['bootstrap']['auroc']['ci95']} F1={unit['card']['f1']:.4f} "
        f"CI={unit['bootstrap']['f1']['ci95']} Brier={unit['card']['brier']:.4f}"
    )
    for name in ("exercise_fixed_steps_5000", "exercise_steps_scale", "sleep_hours", "heart_rate", "steps_fixed_exercise_30"):
        m = sweeps[name]["monotonicity"]
        print(
            f"  {name:32s} monotonic={m['monotonic']} dir_changes={m['direction_changes']} "
            f"max_jump={m['max_adjacent_jump']:.4f} range={m['score_range']:.4f}"
        )
    if "corrected_13" in candidate:
        print(f"  corrected_13 test F1={candidate['corrected_13']['metrics_test']['f1']}")
    print(f"  -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  -> {REPORT_MD.relative_to(PROJECT_ROOT)}")
    return 0


def render_report(payload: dict) -> str:
    mc = payload["model_card"]
    cal = payload["calibration_candidate"]
    rep = payload["reproduction"]
    lines = [
        "# ROUND_46 生理论证边界（P0-5）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_46/05_physio_boundary.py` 生成。",
        "只读审计，**没有修改生理模型、工件或阈值**。",
        "",
        "## 数据与复现",
        "",
        f"- 生产 13 特征：{', '.join(f'`{f}`' for f in rep['feature_names'])}",
        f"- 固定切分：validation {rep['n_validation']} 行 / test {rep['n_test']} 行",
        f"- 生产预测复现：{rep['production_predictions_reproduced']}，"
        f"与归档 csv 最大差 {rep['max_abs_diff_vs_artifact_csv']:.2e}",
        "",
        "## 小样本不确定性",
        "",
        "| 指标 | 点估计 | 95% bootstrap CI |",
        "|---|---|---|",
        f"| AUC | {mc['auroc']:.4f} | {mc['auroc_ci95'][0]:.4f}–{mc['auroc_ci95'][1]:.4f} |",
        f"| AUPRC | {mc['auprc']:.4f} | {mc['auprc_ci95'][0]:.4f}–{mc['auprc_ci95'][1]:.4f} |",
        f"| F1 | {mc['f1']:.4f} | {mc['f1_ci95'][0]:.4f}–{mc['f1_ci95'][1]:.4f} |",
        f"| Brier | {mc['brier']:.4f} | {mc['brier_ci95'][0]:.4f}–{mc['brier_ci95'][1]:.4f} |",
        "",
        f"测试阳性率 {mc['positive_rate']:.4f}；n=157 下 CI 宽度本身就是结论的一部分，",
        "不能把点估计当作稳定性能。",
        "",
        "## 校准",
        "",
        "| 口径 | Brier | ECE | 校准斜率 |",
        "|---|---|---|---|",
        f"| 原始概率 | {cal['raw']['brier']:.4f} | {cal['raw']['ece']:.4f} | {cal['raw']['slope']:.3f} |",
        f"| Platt（153 validation 拟合） | {cal['platt_on_validation']['brier']:.4f} "
        f"| {cal['platt_on_validation']['ece']:.4f} | {cal['platt_on_validation']['slope']:.3f} |",
        "",
        f"校准方法：{cal['method']}。Platt 只在 153 行验证集上拟合，**探索性**，",
        "不构成生产校准或模型替换。",
        "",
        "## 剂量反应扫描（单变量合成剖面）",
        "",
        "| 扫描 | 单调 | 方向反转次数 | 最大相邻跳变 | 分数范围 | Spearman ρ |",
        "|---|---|---|---|---|---|",
    ]
    for name in (
        "exercise_fixed_steps_5000",
        "exercise_steps_scale",
        "sleep_hours",
        "heart_rate",
        "steps_fixed_exercise_30",
    ):
        s = payload["dose_response"][name]
        m = s["monotonicity"]
        lines.append(
            f"| {name} | {m['monotonic']} | {m['direction_changes']} | {m['max_adjacent_jump']:.4f} "
            f"| {m['score_range']:.4f} | {m['spearman_rho']:.3f} |"
        )
    ef = payload["exercise_feature_sweep"]
    lines += [
        "",
        f"运动固定步数扫描中，`activity_intensity` 在 "
        f"{ef['activity_intensity_max_jump_between'][0]}→{ef['activity_intensity_max_jump_between'][1]} "
        f"分钟之间跳变 {ef['activity_intensity_max_adjacent_jump']:.1f}；"
        f"{ef['note']}",
        "",
        "### 运动分数（固定 steps=5000，节选）",
        "",
        "| exercise_minutes | score | activity_intensity |",
        "|---|---|---|",
    ]
    for row in ef["rows"]:
        if row["exercise_minutes"] in (0, 1, 2, 5, 10, 15, 30, 45, 60, 90, 120):
            lines.append(
                f"| {row['exercise_minutes']:.0f} | {row['score']:.4f} | {row['activity_intensity']:.1f} |"
            )
    lines += [
        "",
        "分数随运动量并非单调下降/上升；这是 MLP 在观测数据上学到的非单调关系，",
        "不能解释为「运动增加导致风险增加/降低」的因果效应。",
        "",
        "## 生产阈值切点（P0-2 摘录）",
        "",
        "| 切点 | 等级起点 | 灵敏度 | 特异度 | PPV | PPV@15% |",
        "|---|---|---|---|---|---|",
    ]
    for cut, row in payload["threshold_rows"].items():
        lines.append(
            f"| {cut} | {row['level_onset']} | {row['sensitivity']:.3f} | {row['specificity']:.3f} "
            f"| {row['ppv']:.3f} | {row['ppv_at_15pct']:.3f} |"
        )
    lines += [
        "",
        "0.35 与 0.55 之间灵敏度/特异度大幅互换；在 n=157 上这些切点的稳定性有限，",
        "阈值表的 CI 见 `ROUND_46_THRESHOLD_DECISION.md`。",
        "",
        "## ROUND_45 候选 `corrected_13` 的定位",
        "",
    ]
    if "corrected_13" in payload["round45_candidate"]:
        c = payload["round45_candidate"]["corrected_13"]
        cur = payload["round45_candidate"]["current_13"]
        lines += [
            f"- `current_13` test：F1 {cur['metrics_test']['f1']}，AUC {cur['metrics_test']['roc_auc']}，"
            f"Brier {cur['metrics_test']['brier']}",
            f"- `corrected_13` test：F1 {c['metrics_test']['f1']}，AUC {c['metrics_test']['roc_auc']}，"
            f"Brier {c['metrics_test']['brier']}",
            f"- `corrected_13` 运动扫描：{c['exercise_sweep']}",
            "",
            "`corrected_13` 的判别指标更好，但运动扫描仍有明显非单调/跳变；它只是单次固定切分的离线候选，",
            "没有重复 CV、没有单调性约束、没有工件快照与替换评审 ⇒ **不进入生产**。",
        ]
    else:
        lines.append("ROUND_45 候选文件不存在，本轮未引用。")
    lines += [
        "",
        "## 判定",
        "",
        payload["verdict"],
        "",
        "## 边界",
        "",
        "1. 剂量反应是单变量合成剖面，其他特征固定在 BASE；不是对真实用户运动的干预估计。",
        "2. 固定 719/153/157 单切分，n=157；CI 只覆盖测试抽样，不覆盖训练/切分不确定性。",
        "3. 训练数据为 Depresjon；跨数据集（如 Kaggle Wearable）只做过特征映射下界，见既有 TRANSFER_MATRIX。",
        "4. 本轮不改阈值、不重训、不替换工件；`corrected_13` 仅记录为候选。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
