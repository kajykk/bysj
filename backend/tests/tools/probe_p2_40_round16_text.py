"""ROUND_16 探针 A：文本侧 T1 DCA/ECE + T5 阈值口径复现.

重跑 v1_27 groupwise OOF（同折、同种子、同规格），用途：
  1. T1：在**组级 OOF 概率**上算 DCA/ECE（比自设 Brier 目标更强的临床效用证据）；
  2. T5：复现 improved_bilingual_metrics.json 的 headline（groupwise_ooF）混淆矩阵，
     证明其按硬编码 t=0.5 计算、而顶层 threshold=0.3 与生产契约
     settings.text_bilingual_decision_threshold=0.30 不一致（口径缺陷实锤）。

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/probe_p2_40_round16_text.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

OUT = Path(__file__).resolve().parent / "probe_p2_40_round16_text_result.json"
METRICS_JSON = BACKEND_ROOT / "models" / "text" / "improved_bilingual_metrics.json"
V127_SCRIPT = (
    REPO_ROOT
    / "backend"
    / "scripts"
    / "modeling"
    / "v1_27"
    / "04_retrain_bilingual_text_groupwise.py"
)


def load_v27_module():
    spec = importlib.util.spec_from_file_location("v27_groupwise", V127_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["v27_groupwise"] = mod
    spec.loader.exec_module(mod)
    return mod


def metrics_at(y: np.ndarray, p: np.ndarray, t: float) -> dict:
    from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

    pred = (p >= t).astype(int)
    cm = confusion_matrix(y, pred)
    tn, fp, fn, tp = cm.ravel()
    return {
        "threshold": t,
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
    }


def main() -> None:
    import pandas as pd

    from app.core.config import settings
    from app.ml.model_validation import compute_ece, decision_curve_analysis
    from sklearn.metrics import roc_auc_score

    v27 = load_v27_module()

    zh = pd.read_csv(v27.ZH_CORPUS)
    zh = zh[zh["text"].astype(str).str.len() >= 5].copy()
    zh["text"] = zh["text"].astype(str)
    zh["label"] = zh["phq9_binary"].astype(int)
    zh_grouped = v27._build_groups(zh)
    _headline, oof = v27._groupwise_oof(zh_grouped)
    y = zh_grouped["label"].values.astype(int)
    p = np.asarray(oof, dtype=float)
    assert not np.isnan(p).any(), "OOF 存在未覆盖样本"

    # ── T5：口径复现 ────────────────────────────────────────────────────
    metrics_json = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
    headline = metrics_json["groupwise_ooF"]["confusion_matrix"]
    repro_05 = metrics_at(y, p, 0.5)
    repro_03 = metrics_at(y, p, 0.3)
    t5 = {
        "metrics_json_top_level_threshold": metrics_json.get("threshold"),
        "metrics_json_threshold_rationale": metrics_json.get("threshold_rationale"),
        "production_settings_threshold": settings.text_bilingual_decision_threshold,
        "script_hardcoded_eval_threshold": 0.5,
        "headline_cm_in_json": headline,
        "recomputed_cm_at_0.5": {k: repro_05[k] for k in ("tn", "fp", "fn", "tp")},
        "recomputed_cm_at_0.3": {k: repro_03[k] for k in ("tn", "fp", "fn", "tp")},
        "headline_matches_at_0.5": all(
            headline[k] == repro_05[k] for k in ("tn", "fp", "fn", "tp")
        ),
        "headline_matches_at_0.3": all(
            headline[k] == repro_03[k] for k in ("tn", "fp", "fn", "tp")
        ),
        "metrics_at_0.5_full": repro_05,
        "metrics_at_0.3_full": repro_03,
    }

    # ── T1：OOF 上的 DCA / ECE ──────────────────────────────────────────
    dca = decision_curve_analysis(y, p)
    t1 = {
        "n": int(len(y)),
        "positive_rate": round(float(y.mean()), 4),
        "auroc": round(float(roc_auc_score(y, p)), 4),
        "ece": round(compute_ece(y, p), 4),
        "dca_summary": dca["summary"],
        "dca_at_0.3": next(
            r for r in dca["curve"] if abs(r["threshold"] - 0.3) < 1e-9
        ),
        "dca_at_0.5": next(
            r for r in dca["curve"] if abs(r["threshold"] - 0.5) < 1e-9
        ),
    }

    # OOF 概率落盘（供复核/后续消融复用；运行期产物，按需 git add -f）
    np.save(OUT.with_suffix(".oof.npy"), p)
    np.save(OUT.with_suffix(".labels.npy"), y)

    result = {"probe": "p2_40_round16_text", "t5_threshold_repro": t5, "t1_text_dca_ece": t1}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[written] {OUT} (+ .oof.npy / .labels.npy)")


if __name__ == "__main__":
    main()
