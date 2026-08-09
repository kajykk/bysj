"""新数据探针: 用从未参与训练/验证的外部数据验证生产文本模型.

数据源: datasets/combined/combined_data.csv (53,043 行英文语句, 7 类标签),
从未被任何训练/评估脚本引用 (2026-08 盘点确认).

评估设计:
  - 主二分类: 阳性 = Depression + Suicidal, 阴性 = Normal (42,399 样本)
  - 中间症状类 (Anxiety/Bipolar/Stress/Personality disorder) 不参与指标,
    仅观测模型对其判阳比例 (行为洞察)
  - 模型: text_depression_classifier (英文主模型) 与 text_improved_bilingual (双语),
    阈值 = model.predict() 默认 (与 verify_current_models 一致)

输出: verification_report/new_data_combined_metrics.json + NEW_DATA_PROBE_REPORT.md
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from scripts.modeling.verify_current_models import _load_model, compute_all_metrics  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("new-data-probe")

REPO_ROOT = Path(__file__).resolve().parents[3]
COMBINED_CSV = REPO_ROOT / "datasets" / "combined" / "combined_data.csv"
OUT_DIR = Path(__file__).resolve().parent / "verification_report"

POSITIVE_CLASSES = ["Depression", "Suicidal"]
NEGATIVE_CLASSES = ["Normal"]
OBSERVED_CLASSES = ["Anxiety", "Bipolar", "Stress", "Personality disorder"]


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ml_training"))
    from data_utils import clean_text  # noqa: PLC0415

    df = pd.read_csv(COMBINED_CSV)
    df = df.dropna(subset=["statement"]).copy()
    df["text"] = df["statement"].astype(str).map(clean_text)
    df = df[df["text"].str.len() >= 5]

    tfidf_dep = _load_model("text_depression_tfidf")
    model_dep = _load_model("text_depression_model")
    tfidf_bil = _load_model("text_improved_bilingual_tfidf")
    model_bil = _load_model("text_improved_bilingual_model")

    pairs = [
        ("text_depression_classifier", tfidf_dep, model_dep),
        ("text_improved_bilingual", tfidf_bil, model_bil),
    ]

    main = df[df["status"].isin(POSITIVE_CLASSES + NEGATIVE_CLASSES)].copy()
    y = main["status"].isin(POSITIVE_CLASSES).astype(int).values
    logger.info("主二分类: %d 条 (阳性 %d / 阴性 %d)", len(main), int(y.sum()), int(len(y) - y.sum()))

    results: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "models": {}}
    for key, tfidf, model in pairs:
        X_vec = tfidf.transform(main["text"].tolist())
        y_prob = model.predict_proba(X_vec)[:, 1]
        y_pred = model.predict(X_vec)
        m = compute_all_metrics(y, y_pred, y_prob)
        m["domain"] = "english_new-data-ood"
        m["dataset"] = "datasets/combined/combined_data.csv (Depression+Suicidal vs Normal)"
        m["n_texts"] = int(X_vec.shape[0])

        # 中间症状类判阳率 (行为观测, 不参与主指标)
        obs = df[df["status"].isin(OBSERVED_CLASSES)].copy()
        X_obs = tfidf.transform(obs["text"].tolist())
        obs_pred = model.predict(X_obs)
        m["observed_classes_positive_rate"] = {
            s: round(float(obs_pred[obs["status"].values == s].mean()), 4) for s in OBSERVED_CLASSES
        }
        m["observed_classes_n"] = {s: int((obs["status"].values == s).sum()) for s in OBSERVED_CLASSES}

        # 误判样例 (各取 5 条, 帮助人工核验)
        mis = main.copy()
        mis["y_true"] = y
        mis["y_pred"] = y_pred
        mis["y_prob"] = y_prob
        mis = mis[mis["y_true"] != mis["y_pred"]]
        m["misclassified_samples"] = [
            {"status": r.status, "label": int(r.y_true), "prob": round(float(r.y_prob), 4), "text": r.text[:200]}
            for r in mis.sort_values("y_prob").head(5).itertuples()
        ]
        m["n_misclassified"] = int(len(mis))
        logger.info(
            "%s: F1=%.4f AUC=%.4f (误判 %d/%d, 中间类判阳率=%s)",
            key,
            m["f1"],
            m["roc_auc"],
            len(mis),
            len(main),
            m["observed_classes_positive_rate"],
        )
        results["models"][key] = m

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "new_data_combined_metrics.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved → %s", json_path)

    lines = [
        "# 新数据探针报告 (combined_data.csv, 从未参与训练/验证)",
        "",
        f"- 生成时间: {results['generated_at']}",
        "- 数据源: `datasets/combined/combined_data.csv` (53,043 行 → 清洗后 ≥5 字符 52,625)",
        "",
        "## 主二分类 (Depression + Suicidal vs Normal)",
        "",
        "| 模型 | N | Pos率 | Acc | BalAcc | Prec | Recall | Spec | F1 | AUC | Brier | 误判数 |",
        "|------|---|-------|-----|--------|------|--------|------|-----|-----|-------|--------|",
    ]
    for key, m in results["models"].items():
        lines.append(
            f"| {key} | {m['samples']} | {m['positive_rate']:.1%} | {m['accuracy']:.4f} | "
            f"{m['balanced_accuracy']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} | "
            f"{m['specificity']:.4f} | {m['f1']:.4f} | {m['roc_auc']:.4f} | "
            f"{m['brier']:.4f} | {m['n_misclassified']} |"
        )
    lines.extend(["", "## 中间症状类判阳率 (行为观测, 不计入指标)", ""])
    lines.append("| 类 | " + " | ".join(results["models"].keys()) + " |")
    lines.append("|---|" + "---|" * len(results["models"]))
    for cls in OBSERVED_CLASSES:
        lines.append(
            f"| {cls} | "
            + " | ".join(
                f"{results['models'][k]['observed_classes_positive_rate'][cls]:.1%}" for k in results["models"]
            )
            + " |"
        )
    lines.extend(["", "## 误判样例 (各模型 Top-5 低概率错报)", ""])
    for key, m in results["models"].items():
        lines.append(f"### {key}")
        for s in m["misclassified_samples"]:
            lines.append(f"- [{s['status']} label={s['label']} prob={s['prob']}] {s['text']}")
    report_path = OUT_DIR / "NEW_DATA_PROBE_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved report → %s", report_path)


if __name__ == "__main__":
    main()
