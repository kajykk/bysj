#!/usr/bin/env python
"""ROUND_30: 文本模态 groupwise OOF 的分组级 bootstrap 95% CI.

按 group(1277 个原始用户) 重采样, 非按行 -- 组内相关, 按行会低估 CI.
B=10000 seed=42, 与 verify_thesis_numbers.py::recompute_groupwise_ci() 同序列.
只读 v1_27/groupwise_oof_predictions.csv, 只写本目录 groupwise_ci.json.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

REPO = Path(__file__).resolve().parents[5]
OOF_CSV = REPO / "backend" / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
OUT_JSON = Path(__file__).resolve().parent / "groupwise_ci.json"

THRESHOLD = 0.5
BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42
METRIC_KEYS = ("f1", "roc_auc", "rec", "prec")


def _metrics(y, s):
    """阈值指标 (f1, auc, rec, prec); 纯 numpy + scipy 平均秩."""
    pred = s >= THRESHOLD
    pos = y == 1
    tp = int((pred & pos).sum())
    fp = int((pred & ~pos).sum())
    fn = int((~pred & pos).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    n_pos = int(pos.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        auc = float("nan")
    else:
        r = rankdata(s, method="average")
        auc = float((r[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))
    return f1, auc, rec, prec


def load_oof():
    """读 OOF csv (列: label,group,p_groupwise,p_textwise)."""
    lines = OOF_CSV.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "label,group,p_groupwise,p_textwise", lines[0]
    y, s, g = [], [], []
    for ln in lines[1:]:
        parts = ln.split(",")
        y.append(int(parts[0]))
        g.append(parts[1])
        s.append(float(parts[2]))
    return np.array(y, np.int64), np.array(s, np.float64), np.array(g)


def group_bootstrap(y, s, g, B=BOOTSTRAP_B, seed=BOOTSTRAP_SEED):
    """按 group 重采样的 bootstrap 分位 CI (向量化 gather)."""
    order = np.argsort(g, kind="mergesort")
    ys, ss, gs = y[order], s[order], g[order]
    uniq = np.unique(g)
    G = len(uniq)
    pos = {gg: i for i, gg in enumerate(uniq)}
    row_g = np.array([pos[gg] for gg in gs], dtype=np.int64)

    rng = np.random.RandomState(seed)
    samples = {k: [] for k in METRIC_KEYS}
    for _ in range(B):
        pick = rng.randint(0, G, G)
        cnt = np.bincount(pick, minlength=G)
        per_row = cnt[row_g]
        idx = np.repeat(np.arange(len(ys)), per_row)
        f1, auc, rec, prec = _metrics(ys[idx], ss[idx])
        if not np.isnan(auc):
            samples["f1"].append(f1)
            samples["roc_auc"].append(auc)
            samples["rec"].append(rec)
            samples["prec"].append(prec)

    out = {}
    for k in METRIC_KEYS:
        arr = np.array(samples[k], dtype=np.float64)
        out[k] = {
            "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))],
            "bootstrap_n": int(len(arr)),
        }
    return out


def main():
    y, s, g = load_oof()
    f1, auc, rec, prec = _metrics(y, s)
    point = {"f1": f1, "roc_auc": auc, "rec": rec, "prec": prec}
    ci = group_bootstrap(y, s, g)
    oof_sha = hashlib.sha256(OOF_CSV.read_bytes()).hexdigest()

    payload = {
        "_note": (
            "文本模态 groupwise(sibling-aware 分组去泄漏) OOF 的 95% CI; "
            "CI 按 group 重采样(非按行), B=10000 seed=42. 来源 v1_27/groupwise_oof_predictions.csv."
        ),
        "method": "group-level bootstrap over OOF (resample 1277 groups with replacement), B=10000, seed=42",
        "n_rows": int(len(y)),
        "n_groups": int(len(np.unique(g))),
        "positive_rate": round(float((y == 1).mean()), 4),
        "threshold": THRESHOLD,
        "oof_csv_sha256": oof_sha,
        "metrics": {
            k: {"point": round(point[k], 6), "ci95": [round(ci[k]["ci95"][0], 6), round(ci[k]["ci95"][1], 6)]}
            for k in METRIC_KEYS
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[groupwise_ci] n={len(y)} groups={payload['n_groups']} "
          f"F1={point['f1']:.4f} {ci['f1']['ci95']} AUC={point['roc_auc']:.4f} {ci['roc_auc']['ci95']}")
    print(f"  -> {OUT_JSON.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())