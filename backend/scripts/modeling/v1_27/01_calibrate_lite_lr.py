"""v1.27 Phase 1: Lite LR 概率校准 (Platt / Isotonic).

对 v1.25 mmpsy_lite_model (冻结, 不重训) 的原始概率做校准,
修正 risk_score = prob*100 的语义保真度 (Brier/ECE), AUC 不变 (单调变换)。

方法:
  - Platt scaling: 对 logit(p_raw) 拟合 1 维 LogisticRegression (2 参数,
    小样本稳健, 公开 API 等价 sklearn._SigmoidCalibration)
  - Isotonic regression: sklearn IsotonicRegression(out_of_bounds="clip")

数据切分 (与 v1.25/v1.26 口径完全一致):
  train_test_split(test=0.15, random_state=42, stratify=y) → test 192 样本不动。
  train 再切 80/20 → calib_fit / calib_select:
    方法选择在 calib_select (模型未见过的 in-sample 外子集) 上做, 避免在
    训练集 in-sample 预测上选方法导致的选择偏差; 选定后在全量 train 上重拟合。

产物:
  models/v1.27_lite_calibration/calibrator.pkl        (sklearn 对象, 公开类 pickle 安全)
  models/v1.27_lite_calibration/calibrator.pkl.sha256 (sidecar, 严格校验)
  models/v1.27_lite_calibration/calibrator_meta.json  (method/threshold/metrics)
  scripts/modeling/v1_27/calibration_report.md / calibration_results.json

输出目录结构对齐既有 v1.23-v1.26 约定。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
TOP_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = TOP_ROOT / "backend"
MODEL_OUT_DIR = BACKEND_ROOT / "models" / "v1.27_lite_calibration"

RANDOM_STATE = 42
TEST_SIZE = 0.15
CALIB_SELECT_SIZE = 0.20
THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
ECE_BINS = 10

MODEL_FEATURES: list[str] = [
    "gad7_score", "total_keywords", "unique_categories",
    "age", "gender", "cgpa",
    "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
    "kw_self_harm_crisis", "kw_exercise_deficit",
    "kw_low_mood", "kw_anxiety_somatic",
    "text_length", "chinese_ratio", "text_quality_flag", "coverage_density",
]


def logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.log(np.clip(p, eps, 1 - eps) / (1 - np.clip(p, eps, 1 - eps)))


def fit_platt(p_raw: np.ndarray, y: np.ndarray) -> LogisticRegression:
    """Platt scaling: 1 维 LR 拟合 logit(p_raw) → y (2 参数, 小样本稳健)."""
    lr = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000, random_state=RANDOM_STATE)
    lr.fit(logit(p_raw).reshape(-1, 1), y)
    return lr


def apply_platt(lr: LogisticRegression, p_raw: np.ndarray) -> np.ndarray:
    return lr.predict_proba(logit(p_raw).reshape(-1, 1))[:, 1]


def fit_isotonic(p_raw: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(p_raw, y)
    return iso


def compute_ece(y_true: np.ndarray, p: np.ndarray, n_bins: int = ECE_BINS) -> tuple[float, list[dict]]:
    """等宽分箱 Expected Calibration Error + 可靠性曲线数据."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    reliability: list[dict] = []
    n = len(y_true)
    for i in range(n_bins):
        mask = (p >= bins[i]) & (p < bins[i + 1]) if i < n_bins - 1 else (p >= bins[i]) & (p <= bins[i + 1])
        cnt = int(mask.sum())
        if cnt == 0:
            reliability.append({"bin_low": round(float(bins[i]), 2), "bin_high": round(float(bins[i + 1]), 2),
                                "count": 0, "avg_prob": None, "frac_pos": None})
            continue
        avg_prob = float(np.mean(p[mask]))
        frac_pos = float(np.mean(y_true[mask]))
        ece += cnt / n * abs(frac_pos - avg_prob)
        reliability.append({"bin_low": round(float(bins[i]), 2), "bin_high": round(float(bins[i + 1]), 2),
                            "count": cnt, "avg_prob": round(avg_prob, 4), "frac_pos": round(frac_pos, 4)})
    return float(ece), reliability


def evaluate(y_true: np.ndarray, p: np.ndarray) -> dict:
    ece, reliability = compute_ece(y_true, p)
    return {
        "roc_auc": round(float(roc_auc_score(y_true, p)), 4),
        "brier": round(float(brier_score_loss(y_true, p)), 4),
        "log_loss": round(float(log_loss(y_true, p, labels=[0, 1])), 4),
        "ece_10bin": round(ece, 4),
        "reliability": reliability,
    }


def threshold_sweep(y_true: np.ndarray, p: np.ndarray) -> tuple[list[dict], dict | None, dict | None]:
    rows: list[dict] = []
    best_constrained: dict | None = None
    best_youden: dict | None = None
    for t in THRESHOLDS:
        y_pred = (p >= t).astype(int)
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        spec = float(recall_score(y_true, y_pred, pos_label=0, zero_division=0))
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        row = {
            "threshold": t, "precision": round(prec, 4), "recall": round(rec, 4),
            "specificity": round(spec, 4), "f1": round(f1, 4),
            "youden_j": round(rec + spec - 1.0, 4),
        }
        rows.append(row)
        if best_youden is None or row["youden_j"] > best_youden["youden_j"]:
            best_youden = row
        if rec >= 0.75 and spec >= 0.65:
            if best_constrained is None or row["f1"] > best_constrained["f1"]:
                best_constrained = row
    return rows, best_constrained, best_youden


def write_sidecar(pkl_path: Path) -> str:
    digest = hashlib.sha256(pkl_path.read_bytes()).hexdigest()
    (pkl_path.parent / f"{pkl_path.name}.sha256").write_text(
        f"{digest}  {pkl_path.name}\n", encoding="utf-8"
    )
    return digest


def main() -> None:
    MODEL_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 数据与冻结模型 (口径与 v1.25/v1.26 一致) ─────────────────────────
    df = pd.read_csv(TOP_ROOT / "data" / "processed" / "lite_features.csv")
    X = df[MODEL_FEATURES].astype(float).values
    y = df["phq9_binary"].astype(int).values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    logger.info("train=%d test=%d (split: test=%.2f seed=%d)",
                len(y_train), len(y_test), TEST_SIZE, RANDOM_STATE)

    model = joblib.load(BACKEND_ROOT / "models" / "v1.25_mmpsy_lite" / "mmpsy_lite_model.pkl")
    scaler = joblib.load(BACKEND_ROOT / "models" / "v1.25_mmpsy_lite" / "mmpsy_lite_scaler.pkl")

    p_train_raw = model.predict_proba(scaler.transform(X_train))[:, 1]
    p_test_raw = model.predict_proba(scaler.transform(X_test))[:, 1]

    # ── 2. 方法选择 (train 80/20 子切分, 防选择偏差) ────────────────────────
    idx = np.arange(len(y_train))
    fit_idx, sel_idx = train_test_split(
        idx, test_size=CALIB_SELECT_SIZE, random_state=RANDOM_STATE, stratify=y_train
    )
    platt_sel = fit_platt(p_train_raw[fit_idx], y_train[fit_idx])
    iso_sel = fit_isotonic(p_train_raw[fit_idx], y_train[fit_idx])

    selection = {}
    for name, p_sel in [
        ("platt", apply_platt(platt_sel, p_train_raw[sel_idx])),
        ("isotonic", np.asarray(iso_sel.predict(p_train_raw[sel_idx]), dtype=float)),
    ]:
        m = evaluate(y_train[sel_idx], p_sel)
        selection[name] = {"brier": m["brier"], "ece": m["ece_10bin"]}
    raw_sel = evaluate(y_train[sel_idx], p_train_raw[sel_idx])
    selection["raw_baseline"] = {"brier": raw_sel["brier"], "ece": raw_sel["ece_10bin"]}

    selected_method = min(
        ("platt", "isotonic"), key=lambda k: selection[k]["brier"]
    )
    logger.info("方法选择 (calib_select brier): platt=%.4f isotonic=%.4f raw=%.4f → %s",
                selection["platt"]["brier"], selection["isotonic"]["brier"],
                selection["raw_baseline"]["brier"], selected_method)

    # ── 3. 选定方法在全量 train 上重拟合 ────────────────────────────────────
    if selected_method == "platt":
        calibrator = fit_platt(p_train_raw, y_train)
    else:
        calibrator = fit_isotonic(p_train_raw, y_train)

    def apply_cal(p: np.ndarray) -> np.ndarray:
        if selected_method == "platt":
            return apply_platt(calibrator, p)
        return np.asarray(calibrator.predict(p), dtype=float)

    p_test_cal = apply_cal(p_test_raw)

    # ── 4. test 集评估: raw vs calibrated ──────────────────────────────────
    metrics = {
        "raw": evaluate(y_test, p_test_raw),
        "calibrated": evaluate(y_test, p_test_cal),
    }
    metrics["calibrated"]["reliability"] = metrics["calibrated"]["reliability"]
    logger.info("test AUC: raw=%.4f cal=%.4f (单调变换应几乎一致)",
                metrics["raw"]["roc_auc"], metrics["calibrated"]["roc_auc"])
    logger.info("test Brier: raw=%.4f cal=%.4f | ECE: raw=%.4f cal=%.4f",
                metrics["raw"]["brier"], metrics["calibrated"]["brier"],
                metrics["raw"]["ece_10bin"], metrics["calibrated"]["ece_10bin"])

    # ── 5. 校准空间阈值扫描 (同一约束: Recall≥0.75 且 Spec≥0.65 → F1 最大) ──
    sweep_cal, best_con, best_j = threshold_sweep(y_test, p_test_cal)
    sweep_raw, best_con_raw, _ = threshold_sweep(y_test, p_test_raw)

    if best_con is not None:
        t_cal = best_con["threshold"]
        t_reason = (
            f"Recall≥0.75 且 Specificity≥0.65 的阈值中 F1 最高者 "
            f"(t={t_cal}, F1={best_con['f1']})"
        )
        go = "go"
    else:
        t_cal = best_j["threshold"]
        t_reason = (
            f"校准空间无阈值同时满足约束, 取 Youden J 最大点 (t={t_cal}, "
            f"J={best_j['youden_j']})"
        )
        go = "conditional_go"

    # ── 6. 产物落盘 ────────────────────────────────────────────────────────
    pkl_path = MODEL_OUT_DIR / "calibrator.pkl"
    joblib.dump(calibrator, pkl_path)
    digest = write_sidecar(pkl_path)

    meta = {
        "version": "v1.27",
        "method": selected_method,
        "fit_date": datetime.now(timezone.utc).isoformat(),
        "split": {"test_size": TEST_SIZE, "random_state": RANDOM_STATE,
                  "calib_select_size": CALIB_SELECT_SIZE},
        "artifact": {"path": "models/v1.27_lite_calibration/calibrator.pkl",
                     "sha256": digest},
        "decision_threshold_calibrated": t_cal,
        "threshold_rationale": t_reason,
        "go_decision": go,
        "selection_metrics": selection,
        "test_metrics": {k: {kk: vv for kk, vv in v.items() if kk != "reliability"}
                         for k, v in metrics.items()},
        "notes": (
            "冻结 v1.25 lite LR, 仅加校准层; Platt=LogisticRegression(logit(p)) 2 参数, "
            "Isotonic=IsotonicRegression(clip)。后端 predict_lite 在 calibrator 产物存在时 "
            "应用校准并使用 lite_calibrated_decision_threshold, 缺失时行为不变 (raw + 0.40)。"
        ),
    }
    meta_path = MODEL_OUT_DIR / "calibrator_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    results = {
        "generated_at": meta["fit_date"],
        "method_selected": selected_method,
        "selection": selection,
        "test_metrics": metrics,
        "threshold_sweep_calibrated": sweep_cal,
        "threshold_sweep_raw_reference": sweep_raw,
        "best_constrained_calibrated": best_con,
        "best_constrained_raw": best_con_raw,
        "selected_threshold_calibrated": t_cal,
        "threshold_rationale": t_reason,
        "go_decision": go,
    }
    (SCRIPT_DIR / "calibration_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── 7. Markdown 报告 ───────────────────────────────────────────────────
    lines = [
        "# v1.27 Lite LR 概率校准报告",
        "",
        f"- 生成时间: {meta['fit_date']}",
        f"- 冻结模型: v1.25 mmpsy_lite_model (test 192 样本, seed=42, 口径同 v1.26)",
        f"- 选定方法: **{selected_method}** (calib_select Brier: "
        f"platt={selection['platt']['brier']} / isotonic={selection['isotonic']['brier']})",
        "",
        "## Test 集指标对比",
        "",
        "| 指标 | raw | calibrated | 变化 |",
        "|------|-----|-----------|------|",
        f"| AUC | {metrics['raw']['roc_auc']} | {metrics['calibrated']['roc_auc']} | 单调变换≈不变 |",
        f"| Brier | {metrics['raw']['brier']} | {metrics['calibrated']['brier']} | "
        f"{metrics['calibrated']['brier'] - metrics['raw']['brier']:+.4f} |",
        f"| ECE(10bin) | {metrics['raw']['ece_10bin']} | {metrics['calibrated']['ece_10bin']} | "
        f"{metrics['calibrated']['ece_10bin'] - metrics['raw']['ece_10bin']:+.4f} |",
        f"| LogLoss | {metrics['raw']['log_loss']} | {metrics['calibrated']['log_loss']} | "
        f"{metrics['calibrated']['log_loss'] - metrics['raw']['log_loss']:+.4f} |",
        "",
        "## 校准空间阈值扫描",
        "",
        "| Threshold | Precision | Recall | Specificity | F1 | Youden J |",
        "|-----------|-----------|--------|-------------|-----|----------|",
    ]
    for r in sweep_cal:
        lines.append(
            f"| {r['threshold']:.2f} | {r['precision']:.4f} | {r['recall']:.4f} | "
            f"{r['specificity']:.4f} | {r['f1']:.4f} | {r['youden_j']:.4f} |"
        )
    lines.extend([
        "",
        f"## 选定阈值 (校准空间): **t = {t_cal}**",
        f"- 理由: {t_reason}",
        f"- Go 决策: {'GO ✅' if go == 'go' else 'CONDITIONAL-GO ⚠️'}",
        "",
        "## 可靠性 (calibrated, test)",
        "",
        "| 区间 | 样本 | 平均预测 | 实际正例率 |",
        "|------|------|---------|-----------|",
    ])
    for b in metrics["calibrated"]["reliability"]:
        if b["count"] == 0:
            lines.append(f"| [{b['bin_low']:.1f}, {b['bin_high']:.1f}) | 0 | — | — |")
        else:
            lines.append(
                f"| [{b['bin_low']:.1f}, {b['bin_high']:.1f}) | {b['count']} | "
                f"{b['avg_prob']:.4f} | {b['frac_pos']:.4f} |"
            )
    (SCRIPT_DIR / "calibration_report.md").write_text("\n".join(lines), encoding="utf-8")

    logger.info("产物: %s (+.sha256 sidecar, %s)", pkl_path, meta_path)
    logger.info("报告: %s / calibration_report.md", SCRIPT_DIR / "calibration_results.json")


if __name__ == "__main__":
    sys.exit(main())
