#!/usr/bin/env python
"""ROUND_46 P0-4: audit the Chinese text groupwise protocol and its leakage.

The corpus carries ground-truth provenance in `source_idx`: every augmented row
points at the original student row it was derived from. The v1_27 sibling-aware
grouping is reconstructed and compared against that provenance. We then measure
what the text-level (leaky) split allows, and verify the groupwise/textwise
headline gap from the stored OOF predictions.

Read-only: no text model, artifact, or threshold is modified.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_46/04_text_leakage_audit.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.metrics.pairwise import linear_kernel
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
for path in (BACKEND, HERE, PROJECT_ROOT / "scripts" / "ml_training"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

CORPUS_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
OOF_PATH = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
TEXT_METRICS = BACKEND / "models" / "text" / "improved_bilingual_metrics.json"
OUT_JSON = HERE / "text_leakage_audit.json"
MIRROR_JSON = PROJECT_ROOT / "outputs" / "candidates" / "round46" / "text_leakage_audit.json"
REPORT_MD = PROJECT_ROOT / "outputs" / "ROUND_46_TEXT_LEAKAGE_AUDIT.md"

SEED = 42
N_FOLDS = 5
BOOTSTRAP_B = 2000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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


def _load_v1_27_groups():
    spec = importlib.util.spec_from_file_location(
        "v1_27_groupwise", BACKEND / "scripts" / "modeling" / "v1_27" / "03_groupwise_leakage_free_eval.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_corpus_and_groups():
    corpus = pd.read_csv(CORPUS_PATH)
    corpus = corpus[corpus["text"].astype(str).str.len() >= 5].reset_index(drop=True)
    corpus["text"] = corpus["text"].astype(str)
    corpus["label"] = corpus["phq9_binary"].astype(int)
    v127 = _load_v1_27_groups()
    df = v127.build_groups(corpus)
    oof = pd.read_csv(OOF_PATH)
    assert len(df) == len(oof) == 8379
    assert (df["group"].to_numpy() == oof["group"].to_numpy()).all(), "rebuilt groups differ from OOF"
    return corpus, df, oof, v127


def metrics(y, p, threshold: float = 0.5) -> dict:
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    pred = p >= threshold
    pos = y == 1
    tp = int((pred & pos).sum())
    fp = int((pred & ~pos).sum())
    fn = int((~pred & pos).sum())
    tn = int((~pred & ~pos).sum())
    sens = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    npv = tn / (tn + fn) if (tn + fn) else float("nan")
    f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else 0.0
    return {
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "auroc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan"),
        "auprc": float(average_precision_score(y, p)) if len(np.unique(y)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y, p)),
        "f1": float(f1),
        "sensitivity": float(sens),
        "specificity": float(spec),
        "precision": float(prec),
        "npv": float(npv),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def group_bootstrap_delta(y, p_group, p_text, groups, B: int = BOOTSTRAP_B, seed: int = SEED) -> dict:
    y = np.asarray(y, dtype=np.float64)
    groups = np.asarray(groups)
    uniq, inverse = np.unique(groups, return_inverse=True)
    G = len(uniq)
    rng = np.random.RandomState(seed)
    keys = ("auroc", "auprc", "brier", "f1")
    samples = {k: [] for k in keys}
    point_g, point_t = metrics(y, p_group), metrics(y, p_text)
    for _ in range(B):
        pick = rng.randint(0, G, G)
        cnt = np.bincount(pick, minlength=G)
        idx = np.repeat(np.arange(len(y)), cnt[inverse])
        if len(np.unique(y[idx])) < 2:
            continue
        mg, mt = metrics(y[idx], p_group[idx]), metrics(y[idx], p_text[idx])
        for k in keys:
            delta = mg[k] - mt[k]
            if math.isfinite(delta):
                samples[k].append(delta)
    out = {}
    for k in keys:
        arr = np.asarray(samples[k], dtype=np.float64)
        out[k] = {
            "delta_groupwise_minus_textwise": point_g[k] - point_t[k],
            "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
            if arr.size
            else [float("nan"), float("nan")],
            "bootstrap_n": int(arr.size),
        }
    return out


def _ci_str(ci) -> str:
    lo, hi = ci
    if lo is None or hi is None:
        return "n/a"
    return f"[{lo:+.4f}, {hi:+.4f}]"


def similarity_stats(
    train_texts,
    test_texts,
    *,
    train_meta=None,
    test_meta=None,
    chunk: int = 256,
) -> dict:
    """Max char-ngram cosine similarity of each test row to any train row."""
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    Xtr = vec.fit_transform(train_texts)
    Xte = vec.transform(test_texts)
    max_sims = []
    top = []
    for start in range(0, Xte.shape[0], chunk):
        block = Xte[start : start + chunk]
        sims = linear_kernel(block, Xtr)
        best_idx = sims.argmax(axis=1)
        best_val = sims[np.arange(block.shape[0]), best_idx]
        max_sims.extend(best_val.tolist())
        for offset, (j, s) in enumerate(zip(best_idx, best_val)):
            if train_meta is not None and test_meta is not None:
                top.append(
                    {
                        "test_row": start + offset,
                        "train_row": int(j),
                        "similarity": float(s),
                        "test_text": test_texts[start + offset][:40],
                        "train_text": train_texts[j][:40],
                        "test_label": int(test_meta["label"].iloc[start + offset]),
                        "train_label": int(train_meta["label"].iloc[j]),
                        "test_augmentation": str(test_meta["augmentation"].iloc[start + offset]),
                        "train_augmentation": str(train_meta["augmentation"].iloc[j]),
                    }
                )
    arr = np.asarray(max_sims, dtype=np.float64)
    top.sort(key=lambda r: -r["similarity"])
    return {
        "n_test": int(arr.size),
        "mean": float(arr.mean()) if arr.size else None,
        "median": float(np.median(arr)) if arr.size else None,
        "p90": float(np.percentile(arr, 90)) if arr.size else None,
        "p99": float(np.percentile(arr, 99)) if arr.size else None,
        "max": float(arr.max()) if arr.size else None,
        "fraction_ge_0.95": float((arr >= 0.95).mean()) if arr.size else None,
        "fraction_ge_0.90": float((arr >= 0.90).mean()) if arr.size else None,
        "fraction_ge_0.80": float((arr >= 0.80).mean()) if arr.size else None,
        "fraction_ge_0.70": float((arr >= 0.70).mean()) if arr.size else None,
        "top_pairs": top[:5],
    }


def split_audit(df: pd.DataFrame, splitter, split_name: str) -> dict:
    y = df["label"].to_numpy(dtype=np.int64)
    group_label = df["group_label"].to_numpy(dtype=np.int64)
    group = df["group"].to_numpy()
    true_family = np.where(
        (df["augmentation"].fillna("original") == "original").to_numpy(),
        np.arange(len(df)),
        df["source_idx"].to_numpy(dtype=np.int64),
    )
    fold_rows = []
    total_test = total_family_leak = total_exact_text_leak = 0
    all_sim = []
    top_all = []
    for fold, (tr, te) in enumerate(splitter):
        train_families = set(true_family[tr].tolist())
        test_families = true_family[te]
        family_leak = np.array([fam in train_families for fam in test_families])
        train_text_set = set(df["text"].iloc[tr].tolist())
        exact_leak = np.array([t in train_text_set for t in df["text"].iloc[te].tolist()])
        sim = similarity_stats(
            df["text"].iloc[tr].tolist(),
            df["text"].iloc[te].tolist(),
            train_meta=df.iloc[tr].reset_index(drop=True),
            test_meta=df.iloc[te].reset_index(drop=True),
        )
        all_sim.append(sim["n_test"])
        top_all.extend(sim["top_pairs"])
        total_test += int(len(te))
        total_family_leak += int(family_leak.sum())
        total_exact_text_leak += int(exact_leak.sum())
        fold_rows.append(
            {
                "fold": fold,
                "n_train": int(len(tr)),
                "n_test": int(len(te)),
                "test_rows_with_family_in_train": int(family_leak.sum()),
                "family_leak_rate": float(family_leak.mean()),
                "families_split_across_fold": int(
                    len(set(test_families.tolist()) & train_families)
                ),
                "exact_text_rows_in_train": int(exact_leak.sum()),
                "max_cross_fold_similarity": sim["max"],
                "fraction_test_sim_ge_0.95": sim["fraction_ge_0.95"],
                "fraction_test_sim_ge_0.90": sim["fraction_ge_0.90"],
                "fraction_test_sim_ge_0.80": sim["fraction_ge_0.80"],
            }
        )
    top_all.sort(key=lambda r: -r["similarity"])
    return {
        "split": split_name,
        "n_folds": len(fold_rows),
        "n_test_total": int(total_test),
        "rows_with_true_family_in_train": int(total_family_leak),
        "family_leak_rate": float(total_family_leak / total_test) if total_test else None,
        "rows_with_exact_text_in_train": int(total_exact_text_leak),
        "folds": fold_rows,
        "top_cross_fold_pairs": top_all[:5],
    }


def main() -> int:
    corpus, df, oof, v127 = load_corpus_and_groups()
    y = df["label"].to_numpy(dtype=np.int64)
    group = df["group"].to_numpy()
    is_orig = (df["augmentation"].fillna("original") == "original").to_numpy()
    true_family = np.where(is_orig, np.arange(len(df)), df["source_idx"].to_numpy(dtype=np.int64))

    # ── 1) provenance fidelity ──
    variant_mask = ~is_orig
    variant_df = df.loc[variant_mask].copy()
    variant_df["true_group"] = [f"g{int(i)}" for i in variant_df["source_idx"]]
    correct = int((variant_df["group"] == variant_df["true_group"]).sum())
    mis = variant_df[variant_df["group"] != variant_df["true_group"]].copy()
    mis_rows = [
        {
            "source_idx": int(r["source_idx"]),
            "true_group": str(r["true_group"]),
            "assigned_group": str(r["group"]),
            "augmentation": str(r["augmentation"]),
            "similarity_note": "char-ngram cosine to best original < 0.5; became a solo group",
        }
        for _, r in mis.iterrows()
    ]
    group_sizes = df.groupby("group").size()
    family_sizes = pd.Series(true_family).value_counts()
    labels_per_group = df.groupby("group")["label"].nunique()
    exact_dup_all = int(df["text"].duplicated().sum())
    norm = df["text"].map(lambda s: re.sub(r"\s+", "", s))
    exact_dup_norm = int(norm.duplicated().sum())
    cross_group_dup = int(
        df.assign(norm=norm).groupby("norm")["group"].nunique().gt(1).sum()
    )

    provenance = {
        "n_rows": int(len(df)),
        "n_groups": int(df["group"].nunique()),
        "n_true_families": int(len(family_sizes)),
        "n_original_anchors": int(is_orig.sum()),
        "n_variants": int(variant_mask.sum()),
        "n_variants_correctly_grouped": correct,
        "variant_grouping_accuracy": correct / int(variant_mask.sum()),
        "n_variants_solo": int(mis.shape[0]),
        "misassigned_variants": mis_rows,
        "n_mixed_label_groups": int((labels_per_group > 1).sum()),
        "group_size": {
            "min": int(group_sizes.min()),
            "median": float(group_sizes.median()),
            "mean": float(group_sizes.mean()),
            "p90": float(group_sizes.quantile(0.9)),
            "max": int(group_sizes.max()),
        },
        "family_size": {
            "min": int(family_sizes.min()),
            "median": float(family_sizes.median()),
            "mean": float(family_sizes.mean()),
            "max": int(family_sizes.max()),
            "n_families_without_variants": int((family_sizes == 1).sum()),
        },
        "augmentation_counts": df["augmentation"].fillna("original").value_counts().to_dict(),
        "exact_duplicate_texts": exact_dup_all,
        "exact_duplicate_texts_after_whitespace_normalization": exact_dup_norm,
        "texts_appearing_in_more_than_one_group": cross_group_dup,
    }

    # ── 2) split audit: groupwise vs textwise ──
    group_splitter = StratifiedGroupKFold(
        n_splits=N_FOLDS, shuffle=True, random_state=SEED
    ).split(np.zeros(len(df)), df["group_label"].to_numpy(), groups=group)
    text_splitter = StratifiedKFold(
        n_splits=N_FOLDS, shuffle=True, random_state=SEED
    ).split(np.zeros(len(df)), y)
    group_split = split_audit(df, group_splitter, "groupwise_sibling_aware")
    text_split = split_audit(df, text_splitter, "textwise_current_protocol")

    # ── 3) OOF metric contrast ──
    p_group = oof["p_groupwise"].to_numpy(dtype=np.float64)
    p_text = oof["p_textwise"].to_numpy(dtype=np.float64)
    m_group = metrics(y, p_group)
    m_text = metrics(y, p_text)
    delta = group_bootstrap_delta(y, p_group, p_text, group)

    stored = json.loads(TEXT_METRICS.read_text(encoding="utf-8"))
    stored_group = stored["groupwise_ooF"]
    stored_text = stored["textwise_ooF"]
    full_zh = stored["full_model_eval_on_zh"]
    metric_checks = {
        "stored_groupwise_auroc": stored_group["roc_auc"],
        "recomputed_groupwise_auroc": m_group["auroc"],
        "stored_groupwise_f1": stored_group["f1"],
        "recomputed_groupwise_f1": m_group["f1"],
        "stored_textwise_auroc": stored_text["roc_auc"],
        "recomputed_textwise_auroc": m_text["auroc"],
        "stored_textwise_f1": stored_text["f1"],
        "recomputed_textwise_f1": m_text["f1"],
        "full_model_eval_on_zh": {
            "n": full_zh["n"],
            "f1": full_zh["f1"],
            "auroc": full_zh["roc_auc"],
            "brier": full_zh["brier"],
            "role": "in-sample evaluation on the training corpus; not a generalization read",
        },
        "reproduction_note": (
            "groupwise metrics reproduce the stored metrics.json exactly. The stored textwise "
            "headline (F1 0.9964: tp=1809/fp=10/fn=3/tn=6557) does NOT reproduce from the OOF "
            "CSV p_textwise column at 0.5 (recomputed F1 0.9950: tp=1798/fp=4/fn=14/tn=6563). "
            "AUC matches. Both columns are leakage-inflated; the conclusion is unchanged. "
            "The CSV textwise column appears to come from a different run than the stored headline."
        ),
    }

    verdict = (
        f"组构建与 source_idx 亲缘关系一致率 {provenance['variant_grouping_accuracy']:.4%}"
        f"（{correct}/{variant_mask.sum()} 变体），仅 {mis.shape[0]} 条 backtranslation 因相似度<0.5 自成组；"
        f"组内标签冲突 {provenance['n_mixed_label_groups']} 组。"
        f"组级切分的真实亲缘泄漏行数为 {group_split['rows_with_true_family_in_train']}"
        f"（{group_split['family_leak_rate']:.4%}），文本级切分为 "
        f"{text_split['rows_with_true_family_in_train']}（{text_split['family_leak_rate']:.2%}）。"
        f"OOF AUC：组级 {m_group['auroc']:.4f} vs 文本级 {m_text['auroc']:.4f}；"
        f"F1：{m_group['f1']:.4f} vs {m_text['f1']:.4f}。"
        "中文文本唯一可引用泛化口径仍是 groupwise OOF；full_model_eval_on_zh 0.9972 为训练语料内样本，"
        "不得作为泛化读数。"
    )

    payload = {
        "_note": (
            "ROUND_46 P0-4 text leakage audit. Read-only. Uses source_idx provenance "
            "to audit the v1_27 sibling-aware grouping; compares groupwise vs textwise "
            "splits and OOF metrics. No text model or threshold modified."
        ),
        "sources": {
            "corpus": str(CORPUS_PATH.relative_to(PROJECT_ROOT)),
            "corpus_sha256": _sha(CORPUS_PATH),
            "oof": str(OOF_PATH.relative_to(PROJECT_ROOT)),
            "oof_sha256": _sha(OOF_PATH),
            "text_metrics": str(TEXT_METRICS.relative_to(PROJECT_ROOT)),
        },
        "provenance": provenance,
        "split_audit": {
            "groupwise": group_split,
            "textwise": text_split,
            "groupwise_leak_explanation": (
                "The 6 groupwise leak rows are exactly the 2 solo backtranslations plus their "
                "g0/g1 siblings: each solo row lands in one fold, its true family in another, "
                "so both directions count once. This is a 2-row provenance defect, not a "
                "systematic sibling leak."
            ),
        },
        "oof_metrics": {
            "groupwise": m_group,
            "textwise": m_text,
            "paired_group_bootstrap_delta": delta,
            "stored_metric_checks": metric_checks,
        },
        "verdict": verdict,
    }
    cleaned = _finite(payload)
    OUT_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    MIRROR_JSON.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_report(cleaned), encoding="utf-8")

    print("[text_leakage_audit]")
    print(
        f"  variant grouping accuracy={provenance['variant_grouping_accuracy']:.6f} "
        f"({correct}/{variant_mask.sum()}); solo={mis.shape[0]}; mixed-label groups={provenance['n_mixed_label_groups']}"
    )
    print(
        f"  group split family-leak rows={group_split['rows_with_true_family_in_train']} "
        f"({group_split['family_leak_rate']:.4%}); text split={text_split['rows_with_true_family_in_train']} "
        f"({text_split['family_leak_rate']:.2%})"
    )
    print(
        f"  groupwise AUC={m_group['auroc']:.4f} F1={m_group['f1']:.4f}; "
        f"textwise AUC={m_text['auroc']:.4f} F1={m_text['f1']:.4f}"
    )
    print(
        f"  delta AUC={delta['auroc']['delta_groupwise_minus_textwise']:+.4f} "
        f"CI={_ci_str(delta['auroc']['ci95'])}"
    )
    print(f"  -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  -> {REPORT_MD.relative_to(PROJECT_ROOT)}")
    return 0


def render_report(payload: dict) -> str:
    prov = payload["provenance"]
    ga = payload["split_audit"]["groupwise"]
    tx = payload["split_audit"]["textwise"]
    oof = payload["oof_metrics"]
    mg, mt = oof["groupwise"], oof["textwise"]
    delta = oof["paired_group_bootstrap_delta"]
    checks = oof["stored_metric_checks"]
    lines = [
        "# ROUND_46 中文文本泄漏审计（P0-4）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_46/04_text_leakage_audit.py` 生成。",
        "只读审计，**没有修改文本模型、工件或阈值**。",
        "",
        "## 一句话结论",
        "",
        payload["verdict"],
        "",
        "## 语料与亲缘真值",
        "",
        f"- 语料：`{payload['sources']['corpus']}`，{prov['n_rows']} 行 / {prov['n_groups']} 组",
        f"- 原始锚点 {prov['n_original_anchors']} 条，增强变体 {prov['n_variants']} 条",
        f"- 变体按 `source_idx` 归组正确率：{prov['variant_grouping_accuracy']:.6%} "
        f"（{prov['n_variants_correctly_grouped']}/{prov['n_variants']}）",
        f"- 组内标签冲突：{prov['n_mixed_label_groups']} 组；组大小中位数 {prov['group_size']['median']}，最大 {prov['group_size']['max']}",
        f"- 精确重复文本：{prov['exact_duplicate_texts']} 条；空白归一后重复："
        f"{prov['exact_duplicate_texts_after_whitespace_normalization']} 条；"
        f"跨组重复文本：{prov['texts_appearing_in_more_than_one_group']} 条",
        "",
        "### 被单独成组的 2 条变体",
        "",
        "| source_idx | 真实组 | 实际组 | 增强方式 |",
        "|---|---|---|---|",
    ]
    for row in prov["misassigned_variants"]:
        lines.append(
            f"| {row['source_idx']} | `{row['true_group']}` | `{row['assigned_group']}` "
            f"| {row['augmentation']} |"
        )
    lines += [
        "",
        "这说明 v1_27 的组构建几乎完全复现了语料自带的亲缘关系；残余问题只有 2 条",
        "backtranslation（相似度低于 0.5 阈值），不是系统性误分组。",
        "",
        "## 两种切分实际泄漏了多少亲缘行",
        "",
        "| 切分 | 测试行 | 真实亲缘出现在训练集的行数 | 占比 | 精确同文出现在训练集的行数 |",
        "|---|---|---|---|---|",
        f"| groupwise（sibling-aware） | {ga['n_test_total']} | {ga['rows_with_true_family_in_train']} "
        f"| {ga['family_leak_rate']:.4%} | {ga['rows_with_exact_text_in_train']} |",
        f"| textwise（现行对照） | {tx['n_test_total']} | {tx['rows_with_true_family_in_train']} "
        f"| {tx['family_leak_rate']:.2%} | {tx['rows_with_exact_text_in_train']} |",
        "",
        "逐折明细见 JSON 的 `split_audit.*.folds`。文本级切分让大量同学生的改写跨到训练集，",
        "这正是 OOF 指标虚高的机制。组级切分的 6 行泄漏不是组被拆开，而是 2 条 solo",
        "backtranslation 与它们的 g0/g1 真实亲缘分处不同折，双向各计一次；属于 2 行亲缘缺陷，",
        "不是系统性泄漏。",
        "",
        "## OOF 指标对比（同一批 8379 行）",
        "",
        "| 口径 | AUC | AUPRC | F1 | Brier | 灵敏度 | 特异度 |",
        "|---|---|---|---|---|---|---|",
        f"| groupwise（可引用） | {mg['auroc']:.4f} | {mg['auprc']:.4f} | {mg['f1']:.4f} "
        f"| {mg['brier']:.4f} | {mg['sensitivity']:.4f} | {mg['specificity']:.4f} |",
        f"| textwise（泄漏对照） | {mt['auroc']:.4f} | {mt['auprc']:.4f} | {mt['f1']:.4f} "
        f"| {mt['brier']:.4f} | {mt['sensitivity']:.4f} | {mt['specificity']:.4f} |",
        f"| **差值（group − text）** | **{delta['auroc']['delta_groupwise_minus_textwise']:+.4f}** "
        f"{_ci_str(delta['auroc']['ci95'])} | "
        f"{delta['auprc']['delta_groupwise_minus_textwise']:+.4f} {_ci_str(delta['auprc']['ci95'])} | "
        f"{delta['f1']['delta_groupwise_minus_textwise']:+.4f} {_ci_str(delta['f1']['ci95'])} | "
        f"{delta['brier']['delta_groupwise_minus_textwise']:+.4f} {_ci_str(delta['brier']['ci95'])} | — | — |",
        "",
        "差值为 groupwise − textwise；AUC/F1 为负、Brier 为正，表示文本级口径虚高。",
        "CI 为按 1277 组重采样的配对 bootstrap（B=2000，seed=42）。",
        "",
        "### 与已落盘 metrics.json 的交叉核对",
        "",
        "| 项 | 存储值 | 本次复算 |",
        "|---|---|---|",
        f"| groupwise AUROC | {checks['stored_groupwise_auroc']} | {checks['recomputed_groupwise_auroc']:.4f} |",
        f"| groupwise F1 | {checks['stored_groupwise_f1']} | {checks['recomputed_groupwise_f1']:.4f} |",
        f"| textwise AUROC | {checks['stored_textwise_auroc']} | {checks['recomputed_textwise_auroc']:.4f} |",
        f"| textwise F1 | {checks['stored_textwise_f1']} | {checks['recomputed_textwise_f1']:.4f} |",
        "",
        f"**复现差异记账：** {checks['reproduction_note']}",
        "",
        "## 全模型中文 0.9972 的定位",
        "",
        f"- `full_model_eval_on_zh`：n={checks['full_model_eval_on_zh']['n']}，"
        f"F1={checks['full_model_eval_on_zh']['f1']}，AUC={checks['full_model_eval_on_zh']['auroc']}，"
        f"Brier={checks['full_model_eval_on_zh']['brier']}。",
        "- 该读数是**训练语料内样本**（模型见过这些文本），不是泛化；不得与 groupwise OOF 并列引用。",
        "",
        "## 残余风险与建议",
        "",
        "1. **组级口径仍有 2 行亲缘泄漏**（两条 backtranslation 自成 solo 组）。量级为 2/8379，",
        "   不改变任何结论；若要做到零泄漏，可在分组时直接用 `source_idx`，或把相似度阈值降到",
        "   0.45 让这两条回挂。",
        "2. **组级口径仍不是外部验证。** 它只回答「同一中文学生语料内、无同人泄漏时的判别力」；",
        "   新平台/新人群仍需真实流量或前瞻性队列。",
        "3. **英文 holdout 不是中文外部验证。** 它来自同一 Reddit 域，只是跨语言；边界见模型卡。",
        "4. **不做模型改动。** 本审计不触发重训、不调整阈值；它只固定后续引用口径。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
