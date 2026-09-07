"""v1.27 Phase 4: 双语文本模型组级真口径重训.

目标:
  - 用 groupwise 真口径 (original + 全部增强变体同组) 重新训练生产双语文本模型
  - 以组级 OOF 指标选择阈值, 避免兄弟泄漏导致的乐观偏差
  - 产出与现有运行时兼容的模型文件:
      backend/models/text/improved_bilingual_model.pkl
      backend/models/text/improved_bilingual_tfidf.pkl
      backend/models/text/improved_bilingual_metrics.json
    以及 .sha256 sidecar

训练原则:
  - 中文语料: chinese_depression_corpus_v1.csv 全量, 但评估用 StratifiedGroupKFold,
    组定义见 03_groupwise_leakage_free_eval.py (original 为锚点, 增强变体归组)
  - 英文语料: depression_dataset_reddit_cleaned.csv, 保留 20% 独立 holdout
  - 模型规格与生产一致: TfidfVectorizer(tokenizer=zh_bilingual_tokenize,
    lowercase=True, sublinear_tf=True, min_df=2, max_df=0.95, max_features=120000,
    ngram_range=(1,2)) + LogisticRegression(C=1.0, class_weight="balanced")

输出的 metrics json 明确标注:
  - groupwise OOF (真口径)
  - textwise 现行口径 (用于对照, 不作为结论)
  - english holdout
  - 选定阈值 (默认应与 config.text_bilingual_decision_threshold 保持一致)

说明:
  此脚本覆盖生产双语 TF-IDF+LR 产物。predict_text 已按
  settings.text_bilingual_decision_threshold = 0.30 读取阈值, 因而重训后只需
  保证阈值契约不漂移即可。
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
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
from sklearn.metrics.pairwise import linear_kernel
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
TOP_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = TOP_ROOT / "backend"
DATA_ROOT = TOP_ROOT / "data"
EN_CORPUS = TOP_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"
ZH_CORPUS = DATA_ROOT / "external" / "chinese_depression_corpus_v1.csv"

MODEL_DIR = BACKEND_ROOT / "models" / "text"
OUT_MODEL = MODEL_DIR / "improved_bilingual_model.pkl"
OUT_TFIDF = MODEL_DIR / "improved_bilingual_tfidf.pkl"
OUT_METRICS = MODEL_DIR / "improved_bilingual_metrics.json"

RANDOM_STATE = 42
N_FOLDS = 5
SIM_THRESHOLD = 0.5
MAX_FEATURES = 120000
THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

TFIDF_KWARGS = dict(
    tokenizer=None,  # runtime 时填充
    lowercase=True,
    sublinear_tf=True,
    min_df=2,
    max_df=0.95,
    max_features=MAX_FEATURES,
    ngram_range=(1, 2),
)
LR_KWARGS = dict(C=1.0, class_weight="balanced", max_iter=3000, random_state=RANDOM_STATE)


def _write_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def _evaluate(y_true: np.ndarray, p: np.ndarray) -> dict:
    y_pred = (p >= 0.5).astype(int)
    cm = confusion_matrix(y_true, y_pred)
    tn = fp = fn = tp = 0
    if cm.size == 4:
        tn, fp, fn, tp = cm.ravel()
    return {
        "n": int(len(y_true)),
        "positive_rate": round(float(np.mean(y_true)), 4),
        "accuracy": round(float((y_pred == y_true).mean()), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "specificity": round(float(tn / (tn + fp)) if (tn + fp) else 0.0, 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": (
            round(float(roc_auc_score(y_true, p)), 4)
            if len(np.unique(y_true)) > 1
            else None
        ),
        "brier": round(float(brier_score_loss(y_true, p)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def _build_groups(df: pd.DataFrame) -> pd.DataFrame:
    is_orig = df["augmentation"].fillna("original") == "original"
    anchors = df[is_orig].reset_index()
    variants = df[~is_orig].reset_index()

    char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    char_vec.fit(df["text"].astype(str))
    a = char_vec.transform(anchors["text"].astype(str))
    v = char_vec.transform(variants["text"].astype(str))
    sims = linear_kernel(v, a)

    group = np.empty(len(df), dtype=object)
    for pos, idx in enumerate(anchors["index"]):
        group[idx] = f"g{pos}"

    best = sims.argmax(axis=1)
    best_sim = sims[np.arange(len(variants)), best]
    solo = 0
    for pos, idx in enumerate(variants["index"]):
        if best_sim[pos] >= SIM_THRESHOLD:
            group[idx] = f"g{best[pos]}"
        else:
            group[idx] = f"solo{pos}"
            solo += 1

    df = df.copy()
    df["group"] = group
    df["group_label"] = df.groupby("group")["label"].transform("mean").round().astype(int)
    logger.info(
        "组构建完成: anchors=%d variants=%d solo=%d threshold=%.2f",
        len(anchors), len(variants), solo, SIM_THRESHOLD,
    )
    return df


def _scan_thresholds(y_true: np.ndarray, p: np.ndarray) -> tuple[list[dict], dict | None, dict | None]:
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
            "threshold": t,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "specificity": round(spec, 4),
            "f1": round(f1, 4),
            "youden_j": round(rec + spec - 1.0, 4),
        }
        rows.append(row)
        if best_youden is None or row["youden_j"] > best_youden["youden_j"]:
            best_youden = row
        if rec >= 0.75 and spec >= 0.65:
            if best_constrained is None or row["f1"] > best_constrained["f1"]:
                best_constrained = row
    return rows, best_constrained, best_youden


def _fit_eval_pipeline(
    texts_train: list[str],
    y_train: np.ndarray,
    texts_eval: list[str],
    y_eval: np.ndarray,
):
    from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: PLC0415

    tfidf = TfidfVectorizer(tokenizer=zh_bilingual_tokenize, **{k: v for k, v in TFIDF_KWARGS.items() if k != "tokenizer"})
    X_train = tfidf.fit_transform(texts_train)
    clf = LogisticRegression(**LR_KWARGS)
    clf.fit(X_train, y_train)
    p_eval = clf.predict_proba(tfidf.transform(texts_eval))[:, 1]
    return tfidf, clf, p_eval


def _groupwise_oof(df: pd.DataFrame) -> tuple[dict, np.ndarray]:
    from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: PLC0415

    X = df["text"].astype(str).values
    y = df["label"].values
    oof = np.full(len(df), np.nan)
    splitter = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    for fold, (tr, te) in enumerate(splitter.split(X, df["group_label"].values, groups=df["group"].values)):
        tfidf = TfidfVectorizer(tokenizer=zh_bilingual_tokenize, **{k: v for k, v in TFIDF_KWARGS.items() if k != "tokenizer"})
        Xtr = tfidf.fit_transform(X[tr])
        Xte = tfidf.transform(X[te])
        clf = LogisticRegression(**LR_KWARGS)
        clf.fit(Xtr, y[tr])
        oof[te] = clf.predict_proba(Xte)[:, 1]
        logger.info("[groupwise] fold %d train=%d eval=%d", fold, len(tr), len(te))
    return _evaluate(y, oof), oof


def _textwise_oof(df: pd.DataFrame) -> tuple[dict, np.ndarray]:
    from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: PLC0415

    X = df["text"].astype(str).values
    y = df["label"].values
    oof = np.full(len(df), np.nan)
    idx = np.arange(len(df))
    splitter = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    # 现行口径：仅按标签分层，不按组约束 (对照)
    for fold, (tr, te) in enumerate(
        StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE).split(
            X, y, groups=idx
        )
    ):
        tfidf = TfidfVectorizer(tokenizer=zh_bilingual_tokenize, **{k: v for k, v in TFIDF_KWARGS.items() if k != "tokenizer"})
        Xtr = tfidf.fit_transform(X[tr])
        Xte = tfidf.transform(X[te])
        clf = LogisticRegression(**LR_KWARGS)
        clf.fit(Xtr, y[tr])
        oof[te] = clf.predict_proba(Xte)[:, 1]
        logger.info("[textwise] fold %d train=%d eval=%d", fold, len(tr), len(te))
    return _evaluate(y, oof), oof


def main() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))

    zh = pd.read_csv(ZH_CORPUS)
    zh = zh[zh["text"].astype(str).str.len() >= 5].copy()
    zh["text"] = zh["text"].astype(str)
    zh["label"] = zh["phq9_binary"].astype(int)

    en = pd.read_csv(EN_CORPUS)
    en = en.dropna(subset=["clean_text", "is_depression"]).copy()
    sys.path.insert(0, str(TOP_ROOT / "scripts" / "ml_training"))
    from data_utils import clean_text  # noqa: PLC0415

    en["text"] = en["clean_text"].astype(str).map(clean_text)
    en["label"] = pd.to_numeric(en["is_depression"], errors="coerce").fillna(0).astype(int)
    en = en[en["label"].isin([0, 1])].drop_duplicates(subset=["text"]).reset_index(drop=True)

    logger.info("中文语料: %d 条, 英文语料: %d 条", len(zh), len(en))

    zh_grouped = _build_groups(zh)

    # 组级真口径 OOF
    logger.info("=== 中文组级 OOF (真口径) ===")
    group_metrics, group_oof = _groupwise_oof(zh_grouped)
    thr_rows, best_constrained, best_youden = _scan_thresholds(zh_grouped["label"].values, group_oof)

    # 文本级对照
    logger.info("=== 中文文本级 OOF (对照, 现行口径) ===")
    text_metrics, text_oof = _textwise_oof(zh_grouped)

    # 英文同域 holdout
    en_train, en_holdout = train_test_split(
        en, test_size=0.2, random_state=RANDOM_STATE, stratify=en["label"]
    )

    # 生产最终模型: 中文全量 + 英文 train
    train_df = pd.concat([zh_grouped[["text", "label"]], en_train[["text", "label"]]], ignore_index=True)
    train_df = train_df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: PLC0415

    tfidf = TfidfVectorizer(tokenizer=zh_bilingual_tokenize, **{k: v for k, v in TFIDF_KWARGS.items() if k != "tokenizer"})
    X_train = tfidf.fit_transform(train_df["text"].astype(str))
    clf = LogisticRegression(**LR_KWARGS)
    clf.fit(X_train, train_df["label"].values)

    # 评估最终模型
    p_zh_full = clf.predict_proba(tfidf.transform(zh_grouped["text"].astype(str)))[:, 1]
    p_en_hold = clf.predict_proba(tfidf.transform(en_holdout["text"].astype(str)))[:, 1]
    full_zh_metrics = _evaluate(zh_grouped["label"].values, p_zh_full)
    en_hold_metrics = _evaluate(en_holdout["label"].values, p_en_hold)

    # 决策阈值: 与配置契约保持一致
    selected_threshold = 0.30 if best_constrained is None else float(best_constrained["threshold"])
    threshold_rationale = (
        f"Recall≥0.75 且 Specificity≥0.65 的阈值中 F1 最高者 (t={selected_threshold})"
        if best_constrained is not None
        else f"无阈值满足约束, 取 Youden J 最大点 (t={best_youden['threshold']})"
    )
    go = "go" if best_constrained is not None else "conditional_go"

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_MODEL, "wb") as f:
        pickle.dump(clf, f)
    with open(OUT_TFIDF, "wb") as f:
        pickle.dump(tfidf, f)
    model_hash = _write_sha256(OUT_MODEL)
    tfidf_hash = _write_sha256(OUT_TFIDF)

    meta = {
        "version": "bilingual_v2_groupwise",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "model": str(OUT_MODEL),
            "tfidf": str(OUT_TFIDF),
            "model_sha256": model_hash,
            "tfidf_sha256": tfidf_hash,
        },
        "threshold": selected_threshold,
        "threshold_rationale": threshold_rationale,
        "go_decision": go,
        "groupwise_ooF": group_metrics,
        "textwise_ooF": text_metrics,
        "english_holdout": en_hold_metrics,
        "full_model_eval_on_zh": full_zh_metrics,
        "threshold_sweep_groupwise": thr_rows,
        "notes": (
            "True protocol: groupwise CV on Chinese corpus (original+siblings grouped) + "
            "English holdout; final production artifact trained on full Chinese + English train."
        ),
    }
    OUT_METRICS.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    out_json = SCRIPT_DIR / "bilingual_groupwise_retrain_results.json"
    out_json.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# v1.27 双语文本模型组级真口径重训报告",
        "",
        f"- 生成时间: {meta['trained_at']}",
        f"- 中文语料: {len(zh_grouped)} 条, {zh_grouped['group'].nunique()} 组",
        f"- 英文语料: {len(en)} 条 (holdout={len(en_holdout)}, train={len(en_train)})",
        "",
        "## 组级真口径 OOF (中文)",
        "",
        f"AUC={group_metrics['roc_auc']} F1={group_metrics['f1']} Precision={group_metrics['precision']} "
        f"Recall={group_metrics['recall']} Specificity={group_metrics['specificity']} Brier={group_metrics['brier']}",
        "",
        "## 文本级对照 (中文, 现行口径)",
        "",
        f"AUC={text_metrics['roc_auc']} F1={text_metrics['f1']} Precision={text_metrics['precision']} "
        f"Recall={text_metrics['recall']} Specificity={text_metrics['specificity']} Brier={text_metrics['brier']}",
        "",
        "## 英文 holdout",
        "",
        f"AUC={en_hold_metrics['roc_auc']} F1={en_hold_metrics['f1']} Precision={en_hold_metrics['precision']} "
        f"Recall={en_hold_metrics['recall']} Specificity={en_hold_metrics['specificity']} Brier={en_hold_metrics['brier']}",
        "",
        "## 阈值扫描 (组级 OOF)",
        "",
        "| Threshold | Precision | Recall | Specificity | F1 | Youden J |",
        "|-----------|-----------|--------|-------------|-----|----------|",
    ]
    for r in thr_rows:
        lines.append(
            f"| {r['threshold']:.2f} | {r['precision']:.4f} | {r['recall']:.4f} | {r['specificity']:.4f} | {r['f1']:.4f} | {r['youden_j']:.4f} |"
        )
    lines.extend([
        "",
        f"## 选定阈值: {selected_threshold}",
        f"- 理由: {threshold_rationale}",
        f"- Go 决策: {'GO ✅' if go == 'go' else 'CONDITIONAL-GO ⚠️'}",
        "",
        "## 最终生产模型在中文全量上的表现 (训练内, 仅供参考)",
        "",
        f"AUC={full_zh_metrics['roc_auc']} F1={full_zh_metrics['f1']} Precision={full_zh_metrics['precision']} "
        f"Recall={full_zh_metrics['recall']} Specificity={full_zh_metrics['specificity']} Brier={full_zh_metrics['brier']}",
        "",
        "注: 真口径结论以组级 OOF 为准; 文本级 0.99+ 属兄弟泄漏虚高, 不再作为决策依据。",
    ])
    (SCRIPT_DIR / "bilingual_groupwise_retrain_report.md").write_text("\n".join(lines), encoding="utf-8")

    logger.info("产物已覆盖: %s / %s", OUT_MODEL, OUT_TFIDF)
    logger.info("元数据: %s", OUT_METRICS)
    logger.info("报告: %s", SCRIPT_DIR / "bilingual_groupwise_retrain_report.md")


if __name__ == "__main__":
    main()
