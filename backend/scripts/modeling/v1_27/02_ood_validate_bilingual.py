"""v1.27 Phase 2: 双语文本模型真 OOD 验证 (兄弟泄漏剥离).

背景与动机:
  verify_current_models 报告 text_improved_bilingual 在 corpus_v2 original 上
  AUC=0.9960 / Precision=1.0000 —— 异常偏高, 疑似污染。经查
  scripts/ml_training/train_bilingual_text.py 的防泄漏策略是「训练排除
  augmentation=="original" 的精确文本」但保留其增强变体 (eda/mmpsy 同义改写),
  形成**兄弟泄漏** (sibling leakage): 验证文本与训练文本互为近重复。

本脚本在 ood_test_set_v2 (5000 条) 上按污染结构分层评估:

  S0 full            全量 (含训练近重复)
  S1 ood_original    original 1275 条 (verify 口径, 兄弟在训练集)
  S2 ood_strict      与训练语料 (v1 增强子集 ∪ reddit) 精确去重后的子集
  S3 ood_mmpsy       mmpsy_augmented 子集 (独立来源, 泄漏最少的候选真 OOD)
  S4 ood_eda         eda 子集 (original 的 EDA 改写, 兄弟泄漏最重)

模型:
  - text_improved_bilingual (双语 TF-IDF+LR, 生产 Level 2 回退)
  - text_depression_classifier (英文主模型, 阴性对照: 中文域应≈随机)
  - text_improved_bilingual[en] (同域对照, 应保持高位)

输出:
  scripts/modeling/v1_27/ood_validation_results.json
  scripts/modeling/v1_27/ood_validation_report.md

判定:
  S3/S2 AUC 相对 S1 的降幅 = 兄弟泄漏贡献; S3 AUC 即真实域外泛化的最保守估计。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
TOP_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = TOP_ROOT / "backend"
DATA_ROOT = TOP_ROOT / "data"
REPO_ROOT = TOP_ROOT

# 双语 TF-IDF 的 tokenizer 以 pickle by-reference 引用 app.core.text_tokenizer
# (N1 pickle 契约), 反序列化前必须保证 backend 在 sys.path 上
sys.path.insert(0, str(BACKEND_ROOT))

OOD_PATH = DATA_ROOT / "external" / "ood_test_set_v2.csv"
ZH_V1_PATH = DATA_ROOT / "external" / "chinese_depression_corpus_v1.csv"
ZH_V2_PATH = DATA_ROOT / "external" / "chinese_depression_corpus_v2_clean.csv"
EN_PATH = REPO_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"


def evaluate(y_true: np.ndarray, p: np.ndarray, threshold: float = 0.5) -> dict:
    y_pred = (p >= threshold).astype(int)
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


def main() -> None:
    # ── 1. 数据加载 ────────────────────────────────────────────────────────
    ood = pd.read_csv(OOD_PATH)
    ood = ood[ood["text"].astype(str).str.len() >= 5].copy()
    ood["label"] = ood["phq9_binary"].astype(int)
    ood["text"] = ood["text"].astype(str)
    logger.info("OOD 全量: %d 条 (阳性率 %.1f%%)", len(ood), ood["label"].mean() * 100)

    v1 = pd.read_csv(ZH_V1_PATH)
    v1 = v1[v1["text"].astype(str).str.len() >= 5].copy()
    v1["text"] = v1["text"].astype(str)
    v1_groups = {
        str(k): set(v1[v1["augmentation"].fillna("original") == k]["text"])
        for k in v1["augmentation"].fillna("original").unique()
    }
    logger.info("v1 corpus 分组: %s", {k: len(v) for k, v in v1_groups.items()})

    v2 = pd.read_csv(ZH_V2_PATH)
    v2 = v2[v2.get("augmentation", pd.Series(dtype=str)).fillna("original") == "original"]
    v2_texts = set(v2["text"].astype(str))

    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ml_training"))
    from data_utils import clean_text  # noqa: PLC0415

    en = pd.read_csv(EN_PATH)
    en = en.dropna(subset=["clean_text", "is_depression"]).copy()
    en_texts = set(en["clean_text"].astype(str).map(clean_text))

    # 训练文本集合: train_bilingual_text.py 的 load_zh 排除 original →
    # 训练 = v1 非original 增强子集 ∪ reddit train (此处保守取全量 reddit)
    train_texts: set[str] = set()
    for k, texts in v1_groups.items():
        if k != "original":
            train_texts |= texts
    train_texts |= en_texts

    # ── 2. 污染结构分析 ────────────────────────────────────────────────────
    ood["in_v1_original"] = ood["text"].isin(v1_groups.get("original", set()))
    ood["in_v2_original"] = ood["text"].isin(v2_texts)
    ood["in_train_augmented"] = ood["text"].isin(train_texts)
    ood["is_strict_ood"] = ~(ood["in_v1_original"] | ood["in_v2_original"] | ood["in_train_augmented"])

    overlap = (
        ood.groupby("augmentation")
        .agg(
            n=("text", "size"),
            in_v1_original=("in_v1_original", "sum"),
            in_train_augmented=("in_train_augmented", "sum"),
            strict_ood=("is_strict_ood", "sum"),
        )
        .reset_index()
    )
    logger.info("污染结构:\n%s", overlap.to_string(index=False))

    # ── 3. 模型加载 ────────────────────────────────────────────────────────
    tfidf_bil = joblib.load(BACKEND_ROOT / "models" / "text" / "improved_bilingual_tfidf.pkl")
    model_bil = joblib.load(BACKEND_ROOT / "models" / "text" / "improved_bilingual_model.pkl")
    tfidf_dep = joblib.load(BACKEND_ROOT / "models" / "artifacts" / "text_depression_classifier" / "text_tfidf.pkl")
    model_dep = joblib.load(BACKEND_ROOT / "models" / "artifacts" / "text_depression_classifier" / "text_model.pkl")

    def predict_bil(texts: list[str]) -> np.ndarray:
        return model_bil.predict_proba(tfidf_bil.transform(texts))[:, 1]

    def predict_dep(texts: list[str]) -> np.ndarray:
        return model_dep.predict_proba(tfidf_dep.transform(texts))[:, 1]

    # ── 4. 分层评估 ────────────────────────────────────────────────────────
    subsets = {
        "S0_full": ood,
        "S1_ood_original": ood[ood["augmentation"] == "original"],
        "S2_ood_strict": ood[ood["is_strict_ood"]],
        "S3_ood_mmpsy": ood[(ood["augmentation"] == "mmpsy_augmented") & ood["is_strict_ood"]],
        "S4_ood_eda": ood[(ood["augmentation"] == "eda") & ood["is_strict_ood"]],
    }

    results: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contamination_overlap": overlap.to_dict(orient="records"),
        "models": {},
    }
    for name, sub in subsets.items():
        if len(sub) == 0:
            logger.warning("%s: 0 条, 跳过", name)
            continue
        texts = sub["text"].tolist()
        y = sub["label"].values
        results["models"][name] = {
            "bilingual": evaluate(y, predict_bil(texts)),
            "english_main_cn_control": evaluate(y, predict_dep(texts)),
            "dataset": sub["augmentation"].value_counts().to_dict(),
        }
        b = results["models"][name]["bilingual"]
        logger.info(
            "%s (n=%d): bilingual AUC=%.4f F1=%.4f P=%.4f R=%.4f | en-ctrl AUC=%s",
            name, len(sub), b["roc_auc"], b["f1"], b["precision"], b["recall"],
            results["models"][name]["english_main_cn_control"]["roc_auc"],
        )

    # ── 5. 英文同域对照 (双语模型应保持高位) ───────────────────────────────
    en_eval = en[en["clean_text"].astype(str).map(clean_text).str.len() >= 5].copy()
    en_eval["label"] = pd.to_numeric(en_eval["is_depression"], errors="coerce").fillna(0).astype(int)
    en_eval = en_eval[en_eval["label"].isin([0, 1])].drop_duplicates(subset=["clean_text"])
    en_texts_eval = en_eval["clean_text"].astype(str).map(clean_text).tolist()
    results["models"]["en_in_domain_control"] = {
        "bilingual": evaluate(en_eval["label"].values, predict_bil(en_texts_eval)),
        "english_main": evaluate(en_eval["label"].values, predict_dep(en_texts_eval)),
        "dataset": {"reddit_cleaned": len(en_eval)},
    }

    # ── 6. 判定 ────────────────────────────────────────────────────────────
    s1 = results["models"].get("S1_ood_original", {}).get("bilingual", {}).get("roc_auc")
    s3 = results["models"].get("S3_ood_mmpsy", {}).get("bilingual", {}).get("roc_auc")
    s2 = results["models"].get("S2_ood_strict", {}).get("bilingual", {}).get("roc_auc")
    if s1 is not None and s3 is not None:
        drop = round(s1 - s3, 4)
        verdict = (
            f"兄弟泄漏确认: S1(verify口径) AUC={s1} vs S3(mmpsy真OOD) AUC={s3}, "
            f"降幅 {drop}。verify_current_models 的 'chinese_cross-domain' 口径被"
            f"增强近重复污染, 真实域外泛化以 S3/S2 为准。"
            if drop > 0.05
            else f"S1 AUC={s1} 与 S3 AUC={s3} 基本一致 (降幅 {drop}), "
            f"双语模型中文域泛化可信, 兄弟泄漏影响有限。"
        )
    else:
        verdict = "S3 子集为空, 无法给出真 OOD 结论, 需人工核查 OOD 构造。"
    results["verdict"] = verdict
    logger.info("判定: %s", verdict)

    out_json = SCRIPT_DIR / "ood_validation_results.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── 7. Markdown 报告 ───────────────────────────────────────────────────
    lines = [
        "# v1.27 双语文本模型真 OOD 验证报告",
        "",
        f"- 生成时间: {results['generated_at']}",
        "- 动机: verify_current_models 双语中文域 AUC=0.9960/Precision=1.0 异常偏高;",
        "  训练脚本 (train_bilingual_text.py) 仅精确排除 original 文本, 增强变体",
        "  (eda/mmpsy 同义改写) 仍留在训练集 → 兄弟泄漏 (sibling leakage)。",
        "",
        "## 污染结构 (ood_test_set_v2 与训练语料精确重叠)",
        "",
        "| OOD 分组 | n | ∈v1_original | ∈训练增强子集 | strict OOD |",
        "|----------|---|--------------|---------------|-----------|",
    ]
    for r in results["contamination_overlap"]:
        lines.append(
            f"| {r['augmentation']} | {r['n']} | {int(r['in_v1_original'])} | "
            f"{int(r['in_train_augmented'])} | {int(r['strict_ood'])} |"
        )
    lines.extend([
        "",
        "## 分层评估 (phq9_binary, threshold=0.5)",
        "",
        "| 子集 | 模型 | n | AUC | F1 | Precision | Recall | Specificity | Brier |",
        "|------|------|---|-----|----|-----------|--------|-------------|-------|",
    ])
    label_map = {
        "bilingual": "双语 (生产回退)",
        "english_main_cn_control": "英文主模型 (阴性对照)",
        "english_main": "英文主模型",
    }
    for name, m in results["models"].items():
        for mk, mv in m.items():
            if "roc_auc" not in mv:
                continue
            lines.append(
                f"| {name} | {label_map.get(mk, mk)} | {mv['n']} | {mv['roc_auc']} | "
                f"{mv['f1']} | {mv['precision']} | {mv['recall']} | "
                f"{mv['specificity']} | {mv['brier']} |"
            )
    lines.extend(["", "## 判定", "", verdict])
    (SCRIPT_DIR / "ood_validation_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    logger.info("产物: %s / ood_validation_report.md", out_json)


if __name__ == "__main__":
    main()
