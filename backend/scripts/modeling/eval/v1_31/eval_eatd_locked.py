#!/usr/bin/env python
"""EATD 一次性锁定评估（transform-only，复用生产文本模型，不 refit）。

预注册见同目录 EATD_PREREGISTRATION.md。本脚本严格按预注册执行：
- 只 transform（生产 improved_bilingual_tfidf.pkl + improved_bilingual_model.pkl），绝不 refit；
- 主阈值 0.5（与 groupwise/论文一致）；附部署阈值 0.30 描述；
- 二分类：new_label >= 53 为阳性（主），>=60 为敏感性描述；
- CI：按 subject 分组 bootstrap（抽志愿者），B=10000 seed=42；
- 落盘逐样本预测 csv + metrics json + 按 subject 的 bootstrap 样本。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_31/eval_eatd_locked.py --data-root ../data/external/eatd
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[5]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

MODEL_DIR = BACKEND / "models" / "text"
SEG_ORDER = ("positive", "negative", "neutral")
SDS_MAIN = 53.0
SDS_SEVERE = 60.0
HEADLINE_THR = 0.5
DEPLOY_THR = 0.30
BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42


def _read_score(folder: Path) -> float | None:
    import re
    def _first(path: Path) -> float | None:
        raw = path.read_text(encoding="utf-8-sig", errors="ignore")
        m = re.search(r"-?\d+(?:\.\d+)?", raw)
        return float(m.group(0)) if m else None
    nl = folder / "new_label.txt"
    lb = folder / "label.txt"
    if nl.exists():
        return _first(nl)
    if lb.exists():
        v = _first(lb)
        return v * 1.25 if v is not None else None
    return None


def _find(folder: Path, seg: str) -> Path | None:
    for name in (f"{seg}.txt", f"{seg}_out.txt"):
        p = folder / name
        if p.exists():
            return p
    return None


def collect(data_root: Path) -> list[dict]:
    out = []
    for folder in sorted(p for p in data_root.rglob("*") if p.is_dir()):
        segs = {s: f.read_text(encoding="utf-8", errors="ignore")
                for s in SEG_ORDER if (f := _find(folder, s)) is not None}
        if not segs:
            continue
        text = "\n".join(segs[s] for s in SEG_ORDER if s in segs).strip()
        score = _read_score(folder)
        if text and score is not None:
            out.append({"subject": folder.name, "text": text, "score": score})
    return out


def _metrics(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    pred = p >= thr
    pos = y == 1
    tp = int((pred & pos).sum()); fp = int((pred & ~pos).sum())
    fn = int((~pred & pos).sum()); tn = int((~pred & ~pos).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    return {"n": len(y), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": prec, "recall": rec, "f1": f1, "specificity": spec}


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    from scipy.stats import rankdata
    npos = int((y == 1).sum()); nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    r = rankdata(p, method="average")
    return float((r[y == 1].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def _group_bootstrap(y, p, subj, thr, B=BOOTSTRAP_B, seed=BOOTSTRAP_SEED) -> dict:
    uniq = np.array(sorted(set(subj)))
    idx_by = {s: np.where(subj == s)[0] for s in uniq}
    rng = np.random.RandomState(seed)
    fs = {"f1": [], "recall": [], "precision": [], "auc": []}
    for _ in range(B):
        pick = rng.choice(uniq, len(uniq), replace=True)
        idx = np.concatenate([idx_by[s] for s in pick])
        yb, pb = y[idx], p[idx]
        m = _metrics(yb, pb, thr); a = _auc(yb, pb)
        if not np.isnan(a):
            fs["f1"].append(m["f1"]); fs["recall"].append(m["recall"])
            fs["precision"].append(m["precision"]); fs["auc"].append(a)
    return {k: [float(np.percentile(np.array(v), 2.5)), float(np.percentile(np.array(v), 97.5))]
            for k, v in fs.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    args = ap.parse_args()

    import joblib
    tfidf = joblib.load(MODEL_DIR / "improved_bilingual_tfidf.pkl")
    model = joblib.load(MODEL_DIR / "improved_bilingual_model.pkl")

    rows = collect(Path(args.data_root))
    texts = [r["text"] for r in rows]
    scores = np.array([r["score"] for r in rows], dtype=np.float64)
    subj = np.array([r["subject"] for r in rows])
    y_main = (scores >= SDS_MAIN).astype(int)
    y_sev = (scores >= SDS_SEVERE).astype(int)

    X = tfidf.transform(texts)              # transform-only，绝不 fit
    p = model.predict_proba(X)[:, 1]

    main = _metrics(y_main, p, HEADLINE_THR)
    main["auc"] = _auc(y_main, p)
    main_ci = _group_bootstrap(y_main, p, subj, HEADLINE_THR)
    deploy = _metrics(y_main, p, DEPLOY_THR)
    severe = _metrics(y_sev, p, HEADLINE_THR)

    outdir = Path(__file__).resolve().parent
    # 逐样本预测
    with open(outdir / "eatd_predictions.csv", "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["subject", "score", "y_ge53", "y_ge60", "prob"])
        for r, pp, yb, ys in zip(rows, p, y_main, y_sev):
            w.writerow([r["subject"], r["score"], int(yb), int(ys), f"{pp:.6f}"])

    payload = {
        "_note": "EATD 外部锁定评估（transform-only，生产模型，未 refit）。",
        "preregistration": "v1_31/EATD_PREREGISTRATION.md",
        "n_subjects": len(rows),
        "positive_ge53": int(y_main.sum()),
        "positive_ge60_desc": int(y_sev.sum()),
        "headline_threshold": HEADLINE_THR,
        "deploy_threshold_desc": DEPLOY_THR,
        "model_artifacts": {
            "tfidf": "models/text/improved_bilingual_tfidf.pkl",
            "model": "models/text/improved_bilingual_model.pkl",
            "tfidf_sha256": hashlib.sha256((MODEL_DIR / "improved_bilingual_tfidf.pkl").read_bytes()).hexdigest(),
            "model_sha256": hashlib.sha256((MODEL_DIR / "improved_bilingual_model.pkl").read_bytes()).hexdigest(),
        },
        "main_ge53_at_0.5": main,
        "main_ci_group_bootstrap": main_ci,
        "severe_ge60_at_0.5": severe,
        "deploy_ge53_at_0.30": deploy,
    }
    (outdir / "eatd_eval.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[eatd] subjects={len(rows)} pos>=53={int(y_main.sum())}")
    print(f"  F1={main['f1']:.4f} {main_ci['f1']}  AUC={main['auc']:.4f} {main_ci['auc']}")
    print(f"  Recall={main['recall']:.4f} {main_ci['recall']}  Prec={main['precision']:.4f}")
    print(f"  -> {outdir/'eatd_eval.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())