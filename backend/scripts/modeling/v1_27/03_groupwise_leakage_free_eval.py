"""v1.27 Phase 3: 组级去泄漏中文域评估 (双语模型真实判别力).

背景:
  02_ood_validate_bilingual.py 证实 ood_test_set_v2 与训练语料语义纠缠
  (mmpsy 变体 100% 在训练集; eda/original 的兄弟 — 原句 + syn_v1~v6 同义
  改写 — 均在训练集), 精确去重无法剥离, 现有"中文跨域"口径不可信。

方法 (sibling-aware group split):
  1. 组构建: v1 corpus 以 original 行为锚点; 全部非 original 行按
     char(2-4)-gram TF-IDF 余弦相似度归入最相似的 original (≥0.5),
     未配对变体自成一组 → 同一学生的原文与其全部改写同组。
  2. StratifiedGroupKFold(5): 组级切分, 同组永不跨 train/eval。
  3. 每 fold 训练同规格 pipeline (TfidfVectorizer[zh_bilingual_tokenize,
     与生产完全一致] + LogisticRegression(C=1.0, balanced)), held-out 组评估。
  4. 对照: 相同行上的文本级 StratifiedKFold(5) (现行防泄漏口径,
     original 排除但变体可跨) — 两者指标差 = 兄弟泄漏虚高幅度。

输出:
  scripts/modeling/v1_27/groupwise_eval_results.json
  scripts/modeling/v1_27/groupwise_eval_report.md
  models/v1.27_lite_calibration/../groupwise OOF 逐行概率 (csv, 供校准复用)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
TOP_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = TOP_ROOT / "backend"
DATA_ROOT = TOP_ROOT / "data"

# 与生产 train_bilingual_text.py 完全一致的向量化/模型超参
TFIDF_KWARGS = dict(
    lowercase=True,
    sublinear_tf=True,
    min_df=2,
    max_df=0.95,
    max_features=120000,
    ngram_range=(1, 2),
)
LR_KWARGS = dict(C=1.0, class_weight="balanced", max_iter=3000, random_state=42)

SIM_THRESHOLD = 0.5
N_FOLDS = 5
RANDOM_STATE = 42


def build_groups(df: pd.DataFrame) -> pd.DataFrame:
    """original 为锚点, 变体按 char-ngram 余弦相似度归组 (≥0.5), 其余自成组."""
    from sklearn.metrics.pairwise import linear_kernel

    is_orig = df["augmentation"].fillna("original") == "original"
    anchors = df[is_orig].reset_index()
    variants = df[~is_orig].reset_index()

    char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    char_vec.fit(df["text"].astype(str))
    A = char_vec.transform(anchors["text"].astype(str))
    V = char_vec.transform(variants["text"].astype(str))

    sims = linear_kernel(V, A)  # (n_variants, n_anchors)
    best = sims.argmax(axis=1)
    best_sim = sims[np.arange(len(variants)), best]

    group_id = np.empty(len(df), dtype=object)
    # 锚点组: g_orig_{row}
    for pos, row_idx in enumerate(anchors["index"]):
        group_id[row_idx] = f"g{pos}"
    # 变体归组或自成组
    n_solo = 0
    for pos, row_idx in enumerate(variants["index"]):
        if best_sim[pos] >= SIM_THRESHOLD:
            group_id[row_idx] = f"g{best[pos]}"
        else:
            group_id[row_idx] = f"solo{pos}"
            n_solo += 1
    df = df.copy()
    df["group"] = group_id
    logger.info(
        "组构建完成: %d 锚点组, %d 变体归组, %d 变体自成组 (sim<%.2f)",
        len(anchors), len(variants) - n_solo, n_solo, SIM_THRESHOLD,
    )
    # 组标签 = 组内多数标签 (增强不改语义, 应一致; 保守取多数)
    df["group_label"] = df.groupby("group")["label"].transform("mean").round().astype(int)
    return df


def evaluate_oof(y_true: np.ndarray, p: np.ndarray) -> dict:
    y_pred = (p >= 0.5).astype(int)
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = (cm.ravel() if cm.size == 4 else (0, 0, 0, 0))
    return {
        "n": int(len(y_true)),
        "positive_rate": round(float(np.mean(y_true)), 4),
        "accuracy": round(float((y_pred == y_true).mean()), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "specificity": round(float(tn / (tn + fp)) if (tn + fp) else 0.0, 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": (
            round(float(roc_auc_score(y_true, p)), 4) if len(np.unique(y_true)) > 1 else None
        ),
        "brier": round(float(brier_score_loss(y_true, p)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def run_split(df: pd.DataFrame, mode: str) -> tuple[dict, np.ndarray]:
    """mode='group' 组级去泄漏; mode='text' 文本级 (现行口径对照)."""
    X = df["text"].astype(str).values
    y = df["label"].values
    oof = np.full(len(df), np.nan)

    if mode == "group":
        splitter = StratifiedGroupKFold(
            n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE
        )
        splits = splitter.split(X, df["group_label"].values, groups=df["group"].values)
    else:
        splitter = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
        splits = splitter.split(X, y)

    from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: PLC0415

    for fold, (tr, te) in enumerate(splits):
        vec = TfidfVectorizer(tokenizer=zh_bilingual_tokenize, **TFIDF_KWARGS)
        Xtr = vec.fit_transform(X[tr])
        Xte = vec.transform(X[te])
        clf = LogisticRegression(**LR_KWARGS)
        clf.fit(Xtr, y[tr])
        oof[te] = clf.predict_proba(Xte)[:, 1]
        logger.info("[%s] fold %d: train=%d eval=%d", mode, fold, len(tr), len(te))

    return evaluate_oof(y, oof), oof


def main() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))  # N1 pickle/导入契约: jieba tokenizer 所在包

    v1 = pd.read_csv(DATA_ROOT / "external" / "chinese_depression_corpus_v1.csv")
    v1 = v1[v1["text"].astype(str).str.len() >= 5].copy()
    v1["text"] = v1["text"].astype(str)
    v1["label"] = v1["phq9_binary"].astype(int)
    logger.info("v1 corpus 全量: %d 条 (阳性率 %.1f%%)", len(v1), v1["label"].mean() * 100)

    df = build_groups(v1)

    # ── 组级去泄漏 OOF ──
    logger.info("=== 组级切分 (sibling-aware, 无泄漏) ===")
    m_group, oof_group = run_split(df, "group")

    # ── 文本级切分对照 (现行防泄漏口径: 变体可跨 fold) ──
    logger.info("=== 文本级切分 (现行口径对照, 含兄弟泄漏) ===")
    m_text, oof_text = run_split(df, "text")

    delta = {
        k: (round((m_group[k] or 0) - (m_text[k] or 0), 4))
        for k in ("roc_auc", "f1", "precision", "recall", "specificity", "brier")
        if m_group[k] is not None and m_text[k] is not None
    }

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_rows": int(len(df)),
        "n_groups": int(df["group"].nunique()),
        "protocol": {
            "folds": N_FOLDS,
            "sim_threshold": SIM_THRESHOLD,
            "tfidf": TFIDF_KWARGS,
            "lr": LR_KWARGS,
        },
        "groupwise_leakage_free": m_group,
        "textwise_current_protocol": m_text,
        "inflation_delta_text_minus_group": delta,
        "verdict": (
            f"文本级口径 AUC={m_text['roc_auc']} vs 组级口径 AUC={m_group['roc_auc']}; "
            f"差值 {delta.get('roc_auc')} 即兄弟泄漏虚高幅度。"
            f"双语模型中文域真实判别力以组级口径为准。"
        ),
    }
    logger.info("判定: %s", results["verdict"])

    out_json = SCRIPT_DIR / "groupwise_eval_results.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    oof_df = pd.DataFrame(
        {"label": df["label"].values, "group": df["group"].values,
         "p_groupwise": oof_group, "p_textwise": oof_text}
    )
    oof_df.to_csv(SCRIPT_DIR / "groupwise_oof_predictions.csv", index=False)

    lines = [
        "# v1.27 组级去泄漏中文域评估 (双语模型真实判别力)",
        "",
        f"- 生成时间: {results['generated_at']}",
        f"- 数据: v1 corpus 全量 {len(df)} 条, {results['n_groups']} 组"
        " (original+全部增强变体同组, StratifiedGroupKFold×5)",
        f"- 流程: 与生产 train_bilingual_text.py 同规格"
        " (TfidfVectorizer[zh_bilingual_tokenize]+LR(C=1,balanced))",
        "",
        "## 对比结果",
        "",
        "| 口径 | AUC | F1 | Precision | Recall | Specificity | Brier |",
        "|------|-----|----|-----------|--------|-------------|-------|",
        f"| 文本级 (现行口径, 含兄弟泄漏) | {m_text['roc_auc']} | {m_text['f1']} | "
        f"{m_text['precision']} | {m_text['recall']} | {m_text['specificity']} | {m_text['brier']} |",
        f"| 组级 (sibling-aware, 无泄漏) | {m_group['roc_auc']} | {m_group['f1']} | "
        f"{m_group['precision']} | {m_group['recall']} | {m_group['specificity']} | {m_group['brier']} |",
        f"| **虚高幅度 (text−group)** | **{delta.get('roc_auc')}** | {delta.get('f1')} | "
        f"{delta.get('precision')} | {delta.get('recall')} | {delta.get('specificity')} | "
        f"{delta.get('brier')} |",
        "",
        "## 混淆矩阵 (组级, threshold=0.5)",
        "",
        f"TN={m_group['confusion_matrix']['tn']} FP={m_group['confusion_matrix']['fp']} "
        f"FN={m_group['confusion_matrix']['fn']} TP={m_group['confusion_matrix']['tp']}",
        "",
        "## 结论",
        "",
        results["verdict"],
        "",
        "注: 组级口径衡量『同分布、无泄漏』的判别力; 真跨域 (新采集学生、不同平台)",
        "需未来真实流量数据回归验证 (MODEL_OPTIMIZATION_PLAN D3)。",
        "OOF 逐行概率见 groupwise_oof_predictions.csv (可复用于校准与阈值分析)。",
    ]
    (SCRIPT_DIR / "groupwise_eval_report.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("产物: %s / groupwise_eval_report.md", out_json)


if __name__ == "__main__":
    main()
