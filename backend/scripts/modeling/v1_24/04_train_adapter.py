"""v1.24 Phase 4: Train Score Adapter.

Trains a piecewise-monotonic ScoreAdapter that maps v1.23 raw scores
to v1.24 adjusted scores, reducing systematic delta while preserving
discriminative power (AUC). Includes Pareto frontier experiments.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class ScoreAdapter:
    def __init__(self, config: dict):
        self.version = config["version"]
        self.segments = config["segments"]
        self.clamp_delta = config["clamp"]
        self.buffer = config["smooth"]

    def transform(self, v1_20_score: float, v1_23_raw_score: float) -> dict:
        delta = v1_23_raw_score - v1_20_score
        seg = self._find_segment(v1_20_score)
        adjusted = v1_20_score + delta * seg["slope"]
        adjusted = max(
            v1_20_score - self.clamp_delta,
            min(v1_20_score + self.clamp_delta, adjusted),
        )
        if self._near_boundary(v1_20_score, seg):
            adjusted = self._smooth(v1_20_score, delta, seg)
        diff = abs(adjusted - v1_20_score)
        return {
            "score": round(adjusted, 2),
            "delta": round(adjusted - v1_23_raw_score, 2),
            "safe_label": self._label(diff),
        }

    def _find_segment(self, score: float) -> dict:
        for seg in self.segments:
            lo, hi = seg["range"]
            if lo <= score <= hi:
                return seg
        return self.segments[-1]

    def _near_boundary(self, score: float, seg: dict) -> bool:
        lo, hi = seg["range"]
        return abs(score - lo) <= self.buffer or abs(score - hi) <= self.buffer

    def _smooth(self, score: float, delta: float, seg: dict) -> float:
        idx = -1
        for i, s in enumerate(self.segments):
            if s is seg:
                idx = i
                break
        if idx < 0:
            return score + delta * seg["slope"]

        result = score + delta * seg["slope"]
        lo, hi = seg["range"]
        if abs(score - lo) <= self.buffer and idx > 0:
            neighbor = self.segments[idx - 1]
            t = (score - (lo - self.buffer)) / (2 * self.buffer)
            t = max(0.0, min(1.0, t))
            neighbor_val = score + delta * neighbor["slope"]
            result = result * t + neighbor_val * (1 - t)
        elif abs(score - hi) <= self.buffer and idx < len(self.segments) - 1:
            neighbor = self.segments[idx + 1]
            t = (score - (hi - self.buffer)) / (2 * self.buffer)
            t = max(0.0, min(1.0, t))
            neighbor_val = score + delta * neighbor["slope"]
            result = result * (1 - t) + neighbor_val * t

        return max(
            score - self.clamp_delta,
            min(score + self.clamp_delta, result),
        )

    def _label(self, diff: float) -> str:
        if diff <= 5:
            return "stable"
        if diff <= 15:
            return "slight_diff"
        if diff <= 25:
            return "marked_diff"
        return "review"


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def build_config(
    delta_df: pd.DataFrame,
    slope_multiplier: float = 1.0,
) -> dict:
    segments = []
    target_deltas = [5, 10, 12, 10, 5]
    for i, (_, row) in enumerate(delta_df.iterrows()):
        lo_str, hi_str = row["score_range"].split("-")
        lo, hi = int(lo_str), int(hi_str)
        target = target_deltas[i] if i < len(target_deltas) else 5
        raw_slope = target / max(abs(row["actual_mean_delta"]), 1.0)
        slope = clamp(raw_slope * slope_multiplier, 0.2, 1.0)
        segments.append({"range": [lo, hi], "slope": round(slope, 3)})
    return {
        "version": "v1.24",
        "type": "piecewise_monotonic",
        "segments": segments,
        "clamp": 20,
        "smooth": 3,
        "training_date": date.today().isoformat(),
    }


def validate(
    adapter: ScoreAdapter,
    full_df: pd.DataFrame,
) -> dict:
    adjusted_scores = []
    for _, row in full_df.iterrows():
        res = adapter.transform(row["v120_risk"], row["v123_risk"])
        adjusted_scores.append(res["score"])
    adjusted_scores = np.array(adjusted_scores)
    v120 = full_df["v120_risk"].values

    new_delta = np.abs(adjusted_scores - v120)
    mean_abs = float(new_delta.mean())

    y_true = full_df["depression_binary"].values
    auc_orig = float(roc_auc_score(y_true, full_df["v123_risk"].values))
    auc_new = float(roc_auc_score(y_true, adjusted_scores))

    labels = [adapter._label(abs(s - r)) for s, r in zip(adjusted_scores, v120)]
    label_counts = pd.Series(labels).value_counts().to_dict()

    return {
        "mean_abs_delta": round(mean_abs, 2),
        "auc_original": round(auc_orig, 4),
        "auc_adjusted": round(auc_new, 4),
        "auc_loss": round(auc_orig - auc_new, 4),
        "label_distribution": label_counts,
    }


def main() -> None:
    docs_dir = (
        PROJECT_ROOT
        / "docs"
        / "planning"
        / "v1.24-mmpsy-external-consistency-and-score-stability"
    )
    model_dir = PROJECT_ROOT / "backend" / "models" / "v1.24_adapter"
    model_dir.mkdir(parents=True, exist_ok=True)

    delta_path = docs_dir / "delta_by_risk_group.csv"
    delta_df = pd.read_csv(delta_path)
    if "Unnamed: 0" in delta_df.columns:
        delta_df = delta_df.drop(columns=["Unnamed: 0"])

    full_path = (
        PROJECT_ROOT
        / "backend"
        / "models"
        / "v1.23_external_lr"
        / "model_delta_samples.csv"
    )
    full_df = pd.read_csv(full_path)

    # ---- Primary Adapter (slope_multiplier = 1.0) ----
    config = build_config(delta_df, slope_multiplier=1.0)
    adapter = ScoreAdapter(config)
    metrics = validate(adapter, full_df)

    print("=== Primary Adapter (multiplier=1.0) ===")
    print(f"Mean Abs Delta: {metrics['mean_abs_delta']}")
    print(f"AUC original: {metrics['auc_original']} → adjusted: {metrics['auc_adjusted']}")
    print(f"AUC loss: {metrics['auc_loss']}")
    print(f"Label dist: {metrics['label_distribution']}")

    # ---- Pareto Frontier Experiments ----
    multipliers = [0.3, 0.5, 0.7, 0.9]
    pareto_results = []
    for mult in multipliers:
        exp_config = build_config(delta_df, slope_multiplier=mult)
        exp_adapter = ScoreAdapter(exp_config)
        exp_metrics = validate(exp_adapter, full_df)
        pareto_results.append(
            {
                "multiplier": mult,
                "mean_abs_delta": exp_metrics["mean_abs_delta"],
                "auc_original": exp_metrics["auc_original"],
                "auc_adjusted": exp_metrics["auc_adjusted"],
                "auc_loss": exp_metrics["auc_loss"],
            }
        )
        print(f"mult={mult}: abs={exp_metrics['mean_abs_delta']}, "
              f"auc_loss={exp_metrics['auc_loss']}")

    pareto_df = pd.DataFrame(pareto_results)
    pareto_df.to_csv(docs_dir / "adapter_experiment_results.csv", index=False)

    # ---- Select Best ----
    pareto_df["score"] = (20 - pareto_df["mean_abs_delta"]).clip(0) * 0.5 + (
        0.02 - pareto_df["auc_loss"]
    ).clip(0) * 0.5
    best_idx = int(pareto_df["score"].idxmax())
    best_mult = float(pareto_df.iloc[best_idx]["multiplier"])

    print(f"\nBest multiplier: {best_mult} (score={pareto_df.iloc[best_idx]['score']:.4f})")

    best_config = build_config(delta_df, slope_multiplier=best_mult)
    best_adapter = ScoreAdapter(best_config)
    best_metrics = validate(best_adapter, full_df)

    # ---- Save ----
    joblib.dump(best_adapter, model_dir / "score_adapter.pkl")
    (model_dir / "score_adapter_config.json").write_text(
        json.dumps(best_config, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- Selection Report ----
    pareto_md_rows = "\n".join(
        f"| {r['multiplier']} | {r['mean_abs_delta']} | {r['auc_loss']} |"
        for r in pareto_results
    )
    selection_report = f"""# v1.24 Adapter Selection Report

## Pareto Frontier

| Multiplier | Mean Abs Delta | AUC Loss |
|------------|---------------|----------|
{pareto_md_rows}

## Selected Configuration

| Parameter | Value |
|-----------|-------|
| Multiplier | {best_mult} |
| Mean Abs Delta | {best_metrics['mean_abs_delta']} |
| AUC Original | {best_metrics['auc_original']} |
| AUC Adjusted | {best_metrics['auc_adjusted']} |
| AUC Loss | {best_metrics['auc_loss']} |

## Acceptance Criteria

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Mean Abs Delta | < 15 | {best_metrics['mean_abs_delta']} | {"✅" if best_metrics['mean_abs_delta'] < 15 else "⚠️ Pareto"} |
| AUC Loss | ≤ 0.02 | {best_metrics['auc_loss']} | {"✅" if best_metrics['auc_loss'] <= 0.02 else "⚠️ Pareto"} |

## Segment Configuration

```json
{json.dumps(best_config, indent=2, ensure_ascii=False)}
```
"""
    (docs_dir / "adapter_selection_report.md").write_text(
        selection_report, encoding="utf-8"
    )

    print(f"\nAdapter saved to: {model_dir}")
    print(f"Selection report: {docs_dir / 'adapter_selection_report.md'}")


if __name__ == "__main__":
    main()
