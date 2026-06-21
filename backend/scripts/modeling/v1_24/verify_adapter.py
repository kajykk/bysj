"""Phase 4 unit tests — verifies ScoreAdapter correctness."""
from __future__ import annotations

import sys
from pathlib import Path

import importlib.util
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[4]

_spec = importlib.util.spec_from_file_location(
    "train_adapter",
    PROJECT_ROOT / "backend" / "scripts" / "modeling" / "v1_24" / "04_train_adapter.py",
)
_train_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_train_mod)
ScoreAdapter = _train_mod.ScoreAdapter

adapter_path = (
    PROJECT_ROOT / "backend" / "models" / "v1.24_adapter" / "score_adapter.pkl"
)
delta_path = (
    PROJECT_ROOT
    / "backend"
    / "models"
    / "v1.23_external_lr"
    / "model_delta_samples.csv"
)

# ============================================================
# TP-ADAPT-04: Adapter 文件可加载
# ============================================================
print("=== TP-ADAPT-04: Adapter 文件可加载 ===")
adapter = joblib.load(adapter_path)
assert isinstance(adapter, ScoreAdapter), f"Expected ScoreAdapter, got {type(adapter)}"
print(f"  Loaded: {type(adapter).__name__} ✅")

res = adapter.transform(45.0, 62.0)
assert "score" in res and "delta" in res and "safe_label" in res
print(f"  transform(45, 62) = {res} ✅")

# ============================================================
# TP-ADAPT-01: Adapter 变换正确性
# ============================================================
print("\n=== TP-ADAPT-01: Adapter 变换正确性 ===")

# Test 1: slope=1.0 — no compression
config_s1 = {
    "version": "test", "segments": [{"range": [0, 100], "slope": 1.0}],
    "clamp": 100, "smooth": 0,
}
a1 = ScoreAdapter(config_s1)
r = a1.transform(30, 50)
assert r["score"] == 50.0, f"slope=1.0: expected 50, got {r['score']}"
print(f"  Test 1 - slope=1.0: v120=30, v123=50 → {r['score']} ✅")

# Test 2: slope=0.5 — compresses delta by half
config_s05 = {
    "version": "test", "segments": [{"range": [0, 100], "slope": 0.5}],
    "clamp": 100, "smooth": 0,
}
a05 = ScoreAdapter(config_s05)
r = a05.transform(20, 40)
assert r["score"] == 30.0, f"slope=0.5: expected 30, got {r['score']}"
print(f"  Test 2 - slope=0.5: v120=20, v123=40 → {r['score']} ✅")

# Test 3: clamp — score limited to v120 ± clamp_delta
config_clamp = {
    "version": "test", "segments": [{"range": [0, 100], "slope": 0.5}],
    "clamp": 20, "smooth": 0,
}
a_clamp = ScoreAdapter(config_clamp)
r = a_clamp.transform(20, 80)
assert r["score"] <= 40.01, f"clamp failed: got {r['score']}"
print(f"  Test 3 - clamp: v120=20, v123=80 → {r['score']} (≤40) ✅")

# Test 4: boundary smoothing
config_2seg = {
    "version": "test",
    "segments": [
        {"range": [0, 49], "slope": 1.0},
        {"range": [50, 100], "slope": 0.2},
    ],
    "clamp": 100, "smooth": 3,
}
a2seg = ScoreAdapter(config_2seg)
r_edge = a2seg.transform(50, 60)
r_inside = a2seg.transform(55, 60)
assert r_edge["score"] != 60.0, f"boundary not smoothed: got {r_edge['score']}"
print(f"  Test 4 - boundary: at 50 → {r_edge['score']}, at 55 → {r_inside['score']} ✅")

# ============================================================
# TP-ADAPT-02: Adapter 标签生成正确
# ============================================================
print("\n=== TP-ADAPT-02: Adapter 标签生成正确 ===")
assert adapter._label(3) == "stable"
print("  diff=3 → stable ✅")
assert adapter._label(10) == "slight_diff"
print("  diff=10 → slight_diff ✅")
assert adapter._label(20) == "marked_diff"
print("  diff=20 → marked_diff ✅")
assert adapter._label(30) == "review"
print("  diff=30 → review ✅")

# ============================================================
# TP-ADAPT-03: Adapter 性能达标
# ============================================================
print("\n=== TP-ADAPT-03: Adapter 性能达标 ===")
full_df = pd.read_csv(delta_path)
scores = []
for _, row in full_df.iterrows():
    scores.append(adapter.transform(row["v120_risk"], row["v123_risk"])["score"])
scores = np.array(scores)
v120 = full_df["v120_risk"].values
mad = float(np.abs(scores - v120).mean())
auc_orig = float(roc_auc_score(full_df["depression_binary"], full_df["v123_risk"]))
auc_new = float(roc_auc_score(full_df["depression_binary"], scores))
auc_loss = auc_orig - auc_new

print(f"  Mean Abs Delta: {mad:.2f} (target < 15)")
assert mad < 15, f"Mean Abs Delta too high: {mad}"
print(f"  AUC original: {auc_orig:.4f}")
print(f"  AUC adjusted: {auc_new:.4f}")
print(f"  AUC Loss: {auc_loss:.4f} (target ≤ 0.02)")
assert auc_loss <= 0.02, f"AUC loss too high: {auc_loss}"
print("  ✅ All performance criteria met!")

print("\n========== ALL Phase 4 TESTS PASSED ==========")
