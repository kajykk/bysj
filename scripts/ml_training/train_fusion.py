from __future__ import annotations

from pathlib import Path
import json
import pickle

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split


DEFAULT_OUTPUT_DIR = Path("models") / "artifacts" / "fusion_classifier"
DEFAULT_TABULAR_MODEL = Path("models") / "artifacts" / "depression_tabular" / "best_model.pkl"
DEFAULT_TEXT_MODEL = Path("models") / "artifacts" / "text_depression_classifier" / "text_model.pkl"


def train_probability_fusion(tabular_csv: str, text_csv: str, target_col: str, text_col: str, label_col: str, output_dir: str | Path = DEFAULT_OUTPUT_DIR):
    """
    简化版融合：要求两份数据对齐到同一批样本。
    如果你没有同一批样本的 ID 对齐，请先不要使用该脚本。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tab_df = pd.read_csv(tabular_csv)
    txt_df = pd.read_csv(text_csv)

    if len(tab_df) != len(txt_df):
        raise ValueError("tabular 与 text 数据行数不一致，当前融合脚本要求样本严格对齐。")

    if target_col not in tab_df.columns:
        raise ValueError(f"Tabular target column '{target_col}' not found.")
    if text_col not in txt_df.columns:
        raise ValueError(f"Text column '{text_col}' not found.")
    if label_col not in txt_df.columns:
        raise ValueError(f"Label column '{label_col}' not found.")

    y = tab_df[target_col].astype(int)

    # 这里给出“接口模板”：真实使用时应从已训练模型里拿概率特征
    # 先用占位特征确保框架可运行
    tab_feat = pd.get_dummies(tab_df.drop(columns=[target_col]), dummy_na=True).fillna(0)
    txt_feat = pd.get_dummies(txt_df[[text_col]], dummy_na=True).fillna(0)

    X = pd.concat([tab_feat, txt_feat], axis=1)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = LogisticRegression(max_iter=3000, class_weight="balanced")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
    }

    joblib.dump(model, out_dir / "fusion_model.pkl")
    (out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "training_report.md").write_text(
        f"# 融合模型训练报告\n\n```json\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n```",
        encoding="utf-8",
    )

    print("训练完成")
    print(f"模型: {out_dir / 'fusion_model.pkl'}")
    print(f"指标: {out_dir / 'metrics.json'}")


if __name__ == "__main__":
    train_probability_fusion(
        tabular_csv=str(Path("datasets") / "structured" / "student_depression_dataset.csv"),
        text_csv=str(Path("datasets") / "text" / "depression_dataset_reddit_cleaned.csv"),
        target_col="Depression",
        text_col="clean_text",
        label_col="is_depression",
    )
