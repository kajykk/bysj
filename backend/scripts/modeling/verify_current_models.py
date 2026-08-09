#!/usr/bin/env python3
"""验证当前推理链模型性能 (全部静态生效模型).

对当前推理链路中各模型使用可得的带标签数据重新评测,
输出 JSON 指标与 Markdown 报告.

覆盖模型:
  - structured_v1.20            (默认结构化 LR + scaler, aligned_features 全量)
  - structured_v1.23_external   (v1.23 Pipeline, v1_23 test 集 4319 样本)
  - text_depression_classifier  (英文主文本 TF-IDF+LR, 中文域跨域回归)
  - text_improved_bilingual     (双语 TF-IDF+LR, bilingual_v1 jieba 分词,
                                 2026-08-09 重训替换旧英文副本)
  - text_m2_bert                (中文 BERT feature extraction, 生产影子同款)
  - mmpsy_lite_lr / mmpsy_gbdt  (Lite 17 特征, 与 v1.26 相同切分)
  - physiological_v2_dl         (生理 MLP 13 特征, Depresjon 全量回归验证)
  - V2 注册表 PRODUCTION 训练产物 (若存在)

用法:
    python scripts/modeling/verify_current_models.py [--out-dir ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split  # noqa: E402

from app.core.model_registry import resolve_model_path  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"

LITE_FEATURES = [
    "gad7_score", "total_keywords", "unique_categories",
    "age", "gender", "cgpa",
    "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
    "kw_self_harm_crisis", "kw_exercise_deficit",
    "kw_low_mood", "kw_anxiety_somatic",
    "text_length", "chinese_ratio", "text_quality_flag", "coverage_density",
]

STRUCTURED_V120_FEATURES = [
    "age", "gender", "study_year", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
    "treatment_seeking",
]

V123_FEATURES = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]

DEPRESJON_RAW_FEATURES = [
    "steps", "heart_rate", "sleep_hours", "sleep_quality",
    "exercise_minutes", "systolic_bp", "diastolic_bp",
]

DATA_SOURCES = {
    "structured_v1.20": "data/external/aligned_features.csv (label_binary 全量)",
    "structured_v1.23_external": "data/processed/v1_23_external/test.csv",
    "text_depression_classifier": "chinese_depression_corpus_v2_clean.csv (仅 original)",
    "text_improved_bilingual": "chinese_depression_corpus_v2_clean.csv (仅 original)",
    "mmpsy_lite_lr": "data/processed/lite_features.csv (test 15%, seed 42)",
    "mmpsy_lite_gbdt": "data/processed/lite_features.csv (test 15%, seed 42)",
    "physiological_v2_dl": "depresjon_physiological.csv (n=1029 全量)",
}


def compute_all_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict:
    """完整二分类指标集 (与 v1.23 评估脚本一致)."""
    n = len(y_true)
    cm = confusion_matrix(y_true, y_pred)
    if cm.size == 4:
        tn, fp, fn, tp = cm.ravel()
    else:
        tn, fp, fn, tp = 0, 0, 0, 0

    valid_auc = len(np.unique(y_true)) > 1
    metrics = {
        "samples": n,
        "positive_rate": round(float(np.mean(y_true)), 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "specificity": round(float(tn / (tn + fp)) if (tn + fp) else 0.0, 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_proba)), 4) if valid_auc else None,
        "brier": round(float(brier_score_loss(y_true, y_proba)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    return metrics


def _load_model(model_id: str):
    """通过注册表解析路径后加载模型对象."""
    path = resolve_model_path(model_id)
    obj = joblib.load(path)
    logger.info("loaded %s from %s", model_id, path)
    return obj


def _patch_simple_imputer(model) -> None:
    """旧版 sklearn SimpleImputer 在新版 (>=1.3) 下的兼容补丁 (与 model_engine 一致)."""
    from sklearn.impute import SimpleImputer

    if hasattr(model, "named_steps") and "preprocessor" in model.named_steps:
        preprocessor = model.named_steps["preprocessor"]
        if hasattr(preprocessor, "transformers_"):
            for _, transformer, _ in preprocessor.transformers_:
                if transformer == "drop" or transformer == "passthrough":
                    continue
                if hasattr(transformer, "named_steps"):
                    for step in transformer.named_steps.values():
                        if isinstance(step, SimpleImputer):
                            if not hasattr(step, "_fill_dtype") and hasattr(step, "_fit_dtype"):
                                step._fill_dtype = step._fit_dtype


def evaluate_structured_v120() -> dict:
    """默认结构化 v1.20 (LR), 全量 aligned 数据回归验证."""
    df = pd.read_csv(DATA_ROOT / "external" / "aligned_features.csv")
    df = df.dropna(subset=STRUCTURED_V120_FEATURES + ["label_binary"]).copy()
    model = _load_model("structured_logistic_regression_quick")
    scaler = _load_model("structured_scaler_v1.20")

    X = df[STRUCTURED_V120_FEATURES].astype(float).values
    y = df["label_binary"].astype(int).values
    X_scaled = scaler.transform(X)
    y_proba = model.predict_proba(X_scaled)[:, 1]
    y_pred = model.predict(X_scaled)
    return compute_all_metrics(y, y_pred, y_proba)


def evaluate_structured_v123() -> dict:
    """v1.23 Pipeline 模型: 独立 test 集."""
    df = pd.read_csv(DATA_ROOT / "processed" / "v1_23_external" / "test.csv")
    model = _load_model("structured_v1.23_external_lr")
    _patch_simple_imputer(model)
    X = df[V123_FEATURES]
    y = df["depression_binary"].astype(int).values
    y_proba = model.predict_proba(X)[:, 1]
    y_pred = model.predict(X)
    return compute_all_metrics(y, y_pred, y_proba)


def _text_pair_eval(tfidf, model, texts: list[str], y: np.ndarray) -> dict:
    X_vec = tfidf.transform(texts)
    y_proba = model.predict_proba(X_vec)[:, 1]
    y_pred = model.predict(X_vec)
    metrics = compute_all_metrics(y, y_pred, y_proba)
    metrics["n_texts"] = X_vec.shape[0]
    return metrics


def evaluate_text_model_pair() -> dict:
    """主文本模型与双语回退.

    英文域: depression_dataset_reddit_cleaned (训练同域, 经 clean_text).
    中文域: chinese_depression_corpus_v2_clean original 样本 (跨域).
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ml_training"))
    from data_utils import clean_text  # noqa: PLC0415  (scripts/ml_training)

    tfidf_dep = _load_model("text_depression_tfidf")
    model_dep = _load_model("text_depression_model")
    tfidf_bil = _load_model("text_improved_bilingual_tfidf")
    model_bil = _load_model("text_improved_bilingual_model")

    pairs = [
        ("text_depression_classifier", tfidf_dep, model_dep),
        ("text_improved_bilingual", tfidf_bil, model_bil),
    ]

    results: dict = {}

    # --- 英文域 (同域验证) ---
    reddit = pd.read_csv(REPO_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv")
    reddit = reddit.dropna(subset=["clean_text", "is_depression"]).copy()
    reddit["text"] = reddit["clean_text"].astype(str).map(clean_text)
    reddit = reddit[reddit["text"].str.len() >= 5]
    reddit["label"] = pd.to_numeric(reddit["is_depression"], errors="coerce").fillna(0).astype(int)
    reddit = reddit[reddit["label"].isin([0, 1])].drop_duplicates(subset=["text"])
    y_en = reddit["label"].astype(int).values
    texts_en = reddit["text"].tolist()

    for key, tfidf, model in pairs:
        m = _text_pair_eval(tfidf, model, texts_en, y_en)
        m["domain"] = "english_in-domain"
        m["dataset"] = "depression_dataset_reddit_cleaned"
        results[f"{key}[en]"] = m

    # ---- 中文域: 跨域回归 (推理链真实流量为中文) ---
    zh = pd.read_csv(DATA_ROOT / "external" / "chinese_depression_corpus_v2_clean.csv")
    if "augmentation" in zh.columns:
        zh = zh[zh["augmentation"].fillna("original") == "original"]
    zh = zh.dropna(subset=["text"]).copy()
    y_zh = zh["phq9_binary"].astype(int).values
    texts_zh = zh["text"].astype(str).tolist()

    for key, tfidf, model in pairs:
        results[key] = _text_pair_eval(tfidf, model, texts_zh, y_zh)
        results[key]["domain"] = "chinese_cross-domain"
        results[key]["dataset"] = "chinese_depression_corpus_v2_clean (original)"
    return results


def _m2_eval_on_preds(texts: list[str], y: np.ndarray, predictor, threshold: float) -> dict:
    sem = asyncio.Semaphore(8)

    async def run_one(i):
        async with sem:
            r = await predictor.predict(texts[i])
            return r["probability"] if r else 0.5

    async def run_all():
        return await asyncio.gather(*(run_one(i) for i in range(len(texts))))

    probs = asyncio.run(run_all())
    y_prob = np.asarray(probs, dtype=float)
    y_pred = (y_prob >= threshold).astype(int)
    m = compute_all_metrics(y, y_pred, y_prob)
    m["threshold"] = threshold
    return m


def evaluate_m2_bert() -> dict:
    """M2 中文 BERT (feature extraction, 生产影子同款产物).

    两套评估:
      - original 1275: 与校验集同域, 但 deploy 训练语料同源, 结果偏乐观
      - ood 干净子集 (ood_test_set_v2 与训练语料文本去重): 真实域外指标
    """
    from app.core.text_m2_bert_predictor import get_m2_bert_predictor

    predictor = get_m2_bert_predictor()
    threshold = float(predictor._threshold)

    # 1) original 子集 (同源回归)
    zh = pd.read_csv(DATA_ROOT / "external" / "chinese_depression_corpus_v2_clean.csv")
    if "augmentation" in zh.columns:
        zh = zh[zh["augmentation"].fillna("original") == "original"]
    zh = zh.dropna(subset=["text"]).copy()
    m1 = _m2_eval_on_preds(
        zh["text"].astype(str).tolist(), zh["phq9_binary"].astype(int).values, predictor, threshold,
    )
    m1["domain"] = "chinese_original_full"
    m1["dataset"] = "chinese_depression_corpus_v2_clean (original)"
    m1["leakage_note"] = (
        "M2 训练语料 (chinese_depression_corpus_v2) 与 original 同源, 此值偏乐观; 真实域外见 ood 行"
    )

    # 2) 独立 OOD 干净子集 (与 M2 训练语料 v1/v2 文本去重)
    ood = pd.read_csv(DATA_ROOT / "external" / "ood_test_set_v2.csv")
    zhtexts = set(
        pd.read_csv(DATA_ROOT / "external" / "chinese_depression_corpus_v1.csv")["text"].astype(str)
    ) | set(zh["text"].astype(str))
    ood = ood[~ood["text"].astype(str).isin(zhtexts)].dropna(subset=["text"]).copy()
    m2 = _m2_eval_on_preds(
        ood["text"].astype(str).tolist(), ood["phq9_binary"].astype(int).values, predictor, threshold,
    )
    m2["domain"] = "chinese_ood_dedup"
    m2["dataset"] = "ood_test_set_v2 (去重训练语料)"
    m2["leakage_note"] = f"OOD 原文 {ood.shape[0]} 条, 与训练语料文本级去重"

    results = {"text_m2_bert": m1}
    results["text_m2_bert[ood]"] = m2
    return results


def evaluate_mmpsy_lite() -> dict:
    """Lite LR + GBDT, 与 v1.26 baseline 相同切分 (0.15, 42, stratify)."""
    df = pd.read_csv(DATA_ROOT / "processed" / "lite_features.csv")
    X = df[LITE_FEATURES].astype(float).values
    y = df["phq9_binary"].astype(int).values
    user_ids = df["user_id"].values

    _, X_test, _, y_test, _, _ = train_test_split(
        X, y, user_ids,
        test_size=0.15, random_state=42, stratify=y,
    )

    scaler = _load_model("mmpsy_lite_scaler")
    X_test_scaled = scaler.transform(X_test)

    results: dict = {}
    for model_id, key in [
        ("mmpsy_lite_model", "mmpsy_lite_lr"),
        ("mmpsy_lite_gbdt", "mmpsy_lite_gbdt"),
    ]:
        model = _load_model(model_id)
        y_proba = model.predict_proba(X_test_scaled)[:, 1]
        y_pred = model.predict(X_test_scaled)
        results[key] = compute_all_metrics(y_test, y_pred, y_proba)
    return results


def evaluate_physiological() -> dict:
    """生理 MLP (13 特征): Depresjon 全量数据."""
    from app.ml.feature_engineering import engineer_features
    from app.ml.model_loader import load_cleaner, load_model, load_scaler

    feature_names_path = (
        BACKEND_ROOT / "models" / "artifacts" / "physiological_optimized" / "feature_names.json"
    )
    feature_names = json.loads(feature_names_path.read_text(encoding="utf-8"))

    df = pd.read_csv(
        REPO_ROOT / "datasets" / "physiological" / "external" / "depresjon_processed"
        / "depresjon_physiological.csv"
    )
    keep = DEPRESJON_RAW_FEATURES + ["depression_label"]
    df = df[[c for c in keep if c in df.columns]].dropna().copy()

    cleaner = load_cleaner()
    cleaned = cleaner.transform(df)
    engineered = engineer_features(cleaned)
    X = engineered[feature_names].astype(float).values
    y = cleaned["depression_label"].astype(int).values

    scaler = load_scaler()
    model = load_model()
    X_scaled = scaler.transform(X)
    y_proba = np.asarray(model.predict_proba(X_scaled)).ravel()
    y_pred = (y_proba >= 0.5).astype(int)
    return compute_all_metrics(y, y_pred, y_proba)


def evaluate_registry_production() -> dict:
    """V2 注册表 PRODUCTION 训练产物列表."""
    from app.core.model_registry_v2 import get_registry

    records = get_registry().get_production_models()
    result = {"production_models": len(records)}
    if not records:
        result["note"] = "当前注册表无 PRODUCTION 训练产物"
    else:
        for rec in records:
            result[rec.model_id] = {"status": rec.status.value, "artifact": rec.artifact_path}
    return result


def _write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# 当前推理链模型性能验证报告",
        "",
        f"- 生成时间: {report['generated_at']}",
        "",
        "## 汇总指标",
        "",
        "| 模型 | 数据集 | N | 正例率 | Acc | BalAcc | Prec | Recall | Spec | F1 | AUC | Brier |",
        "|------|--------|---|---|-----|--------|------|--------|------|-----|-----|-------|",
    ]
    for key, m in report["models"].items():
        if not isinstance(m, dict) or "samples" not in m:
            continue
        ds = DATA_SOURCES.get(key) or m.get("dataset", "—")
        auc = f"{m['roc_auc']:.4f}" if m["roc_auc"] is not None else "—"
        lines.append(
            f"| {key} | {ds} | {m['samples']} | {m['positive_rate']:.1%} | "
            f"{m['accuracy']:.4f} | {m['balanced_accuracy']:.4f} | {m['precision']:.4f} | "
            f"{m['recall']:.4f} | {m['specificity']:.4f} | {m['f1']:.4f} | {auc} | {m['brier']:.4f} |"
        )

    lines.extend(["", "## 混淆矩阵", ""])
    for key, m in report["models"].items():
        if not isinstance(m, dict) or "confusion_matrix" not in m or not m["confusion_matrix"]:
            continue
        cm = m["confusion_matrix"]
        lines.append(f"- **{key}**: TN={cm['tn']} FP={cm['fp']} FN={cm['fn']} TP={cm['tp']}")

    lines.extend(["", "## V2 注册表 PRODUCTION 训练产物", ""])
    pa = report.get("production_artifacts", {})
    if isinstance(pa, dict) and not pa.get("production_models"):
        lines.append("(无 PRODUCTION 训练产物接入推理链, resolve_model_path 全部走静态路径)")
    else:
        lines.append(f"```{json.dumps(pa, ensure_ascii=False, indent=2)}```")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved report → %s", path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify current model performance")
    parser.add_argument("--out-dir", default=str(BACKEND_ROOT / "scripts" / "modeling" / "verification_report"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {},
    }

    try:
        report["models"]["structured_v1.20"] = evaluate_structured_v120()
        logger.info("structured_v1.20 ✓")
    except Exception as exc:
        logger.error("structured_v1.20 ✗ %s", exc)

    try:
        report["models"]["structured_v1.23_external"] = evaluate_structured_v123()
        logger.info("structured_v1.23 ✓")
    except Exception as exc:
        logger.error("structured_v1.23 ✗ %s", exc)

    try:
        report["models"].update(evaluate_text_model_pair())
        logger.info("text models ✓")
    except Exception as exc:
        logger.error("text models ✗ %s", exc)

    try:
        report["models"].update(evaluate_m2_bert())
        logger.info("text_m2_bert ✓")
    except Exception as exc:
        logger.error("text_m2_bert ✗ %s", exc)

    try:
        report["models"].update(evaluate_mmpsy_lite())
        logger.info("lite models ✓")
    except Exception as exc:
        logger.error("lite models ✗ %s", exc)

    try:
        report["models"]["physiological_v2_dl"] = evaluate_physiological()
        logger.info("physiological_v2_dl ✓")
    except Exception as exc:
        logger.error("physiological_v2_dl ✗ %s", exc)

    report["production_artifacts"] = evaluate_registry_production()

    json_path = out_dir / "current_models_metrics.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved JSON → %s", json_path)

    _write_markdown(report, out_dir / "CURRENT_MODELS_REPORT.md")


if __name__ == "__main__":
    main()
