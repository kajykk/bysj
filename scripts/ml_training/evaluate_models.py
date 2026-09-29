from __future__ import annotations

from pathlib import Path
import json
import pickle
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

try:
    from .data_utils import clean_tabular_dataframe, clean_text, find_target_column, load_csv, standardize_text_dataset
except ImportError:  # 直接以脚本方式运行（python scripts/ml_training/evaluate_models.py）时无父包
    import sys

    sys.path.append(str(Path(__file__).resolve().parent))
    from data_utils import clean_tabular_dataframe, clean_text, find_target_column, load_csv, standardize_text_dataset


RANDOM_STATE = 42
DEFAULT_REPORT_DIR = Path("models") / "artifacts" / "evaluation_reports"
DEFAULT_TABULAR_MODEL = Path("models") / "artifacts" / "depression_tabular" / "best_model.pkl"
DEFAULT_TEXT_MODEL = Path("models") / "artifacts" / "text_depression_classifier" / "text_model.pkl"
DEFAULT_TEXT_TFIDF = Path("models") / "artifacts" / "text_depression_classifier" / "text_tfidf.pkl"
DEFAULT_TEXT_SPLIT = Path("models") / "artifacts" / "text_depression_classifier" / "split_indices.json"


def _load_split_indices(split_path: Path) -> dict[str, Any] | None:
    """加载训练时保存的划分索引，用于消除评估时的数据泄露。

    Returns:
        包含 train_idx/test_idx/split_hash/dataset_fingerprint 的字典，文件不存在则返回 None。
    """
    if not split_path.exists():
        return None
    with open(split_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_text_model(
    dataset_path: str | Path,
    model_path: str | Path = DEFAULT_TEXT_MODEL,
    tfidf_path: str | Path = DEFAULT_TEXT_TFIDF,
    split_path: str | Path = DEFAULT_TEXT_SPLIT,
    text_col: str = "clean_text",
    label_col: str = "is_depression",
    report_dir: str | Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    """评估文本模型。

    v1.4 修正: 强制使用与训练时相同的不相交测试集 (held-out)。
    - 优先读取训练时保存的 split_indices.json (无泄露，最可信)
    - 若缺失则报错并提示先运行 train_text.py (不再回退到"整集评估"这个已知会导致数据泄露的错误路径)
    """
    dataset_path = Path(dataset_path)
    model_path = Path(model_path)
    tfidf_path = Path(tfidf_path)
    split_path = Path(split_path)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(dataset_path)
    df = standardize_text_dataset(df, text_col=text_col, label_col=label_col)
    df[text_col] = df[text_col].fillna("").astype(str).map(clean_text)

    split_info = _load_split_indices(split_path)
    if split_info is None:
        raise FileNotFoundError(
            f"未找到训练时的划分索引文件: {split_path}\n"
            f"v1.4 起评估必须使用训练时保存的 held-out 划分以消除数据泄露。\n"
            f"请先运行: python scripts/ml_training/train_text.py\n"
            f"(旧版 evaluate_models.py 把整个数据集当测试集导致 F1 虚高到 0.97，已废弃该路径)"
        )

    test_idx = split_info["test_idx"]
    # 校验索引范围
    max_idx = len(df) - 1
    if max(test_idx) > max_idx:
        raise ValueError(
            f"划分索引越界: max(test_idx)={max(test_idx)} > len(df)-1={max_idx}。"
            f"数据集 {dataset_path} 与训练时不一致 (训练时 {split_info.get('total_samples')} 行)。"
        )

    X_test = df.iloc[test_idx][text_col]
    y_test = df.iloc[test_idx][label_col].astype(int)

    with open(tfidf_path, "rb") as f:
        tfidf = pickle.load(f)
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    X_vec = tfidf.transform(X_test)
    y_pred = model.predict(X_vec)
    y_prob = model.predict_proba(X_vec)[:, 1]

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
    }

    payload = {
        "dataset": str(dataset_path),
        "model_path": str(model_path),
        "tfidf_path": str(tfidf_path),
        "text_col": text_col,
        "label_col": label_col,
        "metrics": metrics,
        # v1.4 新增: 评估口径元数据 (防泄露)
        "eval_protocol": {
            "mode": "held_out_test_from_train_split",
            "eval_split_hash": split_info.get("split_hash"),
            "dataset_fingerprint_at_train": split_info.get("dataset_fingerprint"),
            "test_samples": len(test_idx),
            "test_size_ratio": split_info.get("test_size_ratio", 0.2),
            "random_state": split_info.get("random_state", RANDOM_STATE),
            "stratified": split_info.get("stratified", True),
            "note": "使用训练时保存的相同 held-out 测试集，无数据泄露",
        },
    }

    (report_dir / "text_test_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "text_test_report.md").write_text(
        f"# 文本模型测试报告 (v1.4 held-out 评估)\n\n"
        f"- 数据集: `{dataset_path}`\n"
        f"- 测试样本: {len(test_idx)} (训练时保存的不相交 held-out 集)\n"
        f"- 评估划分哈希: `{split_info.get('split_hash', 'N/A')[:16]}...`\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```",
        encoding="utf-8",
    )
    return payload


def evaluate_tabular_model(dataset_path: str | Path, model_path: str | Path = DEFAULT_TABULAR_MODEL, target_col: str | None = None, report_dir: str | Path = DEFAULT_REPORT_DIR) -> dict[str, Any]:
    dataset_path = Path(dataset_path)
    model_path = Path(model_path)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    df = load_csv(dataset_path)
    if target_col is None:
        target_col = find_target_column(df)

    # 复用训练时的特征工程（clean_tabular_dataframe + 派生列），否则推理时
    # ColumnTransformer 会因缺少 SleepDurationOrdinal/AgeGroup/DietaryHabitsOrdinal 而报错。
    # 注：派生列由 load_and_clean_data 内部生成，在此统一调用以避免两处实现漂移。
    from train_tabular import load_and_clean_data

    try:
        df = load_and_clean_data(dataset_path, target_col)
    except ValueError:
        # 目标列名与 find_target_column 判定不一致时回退到基础清洗
        df = clean_tabular_dataframe(load_csv(dataset_path))

    df = df.dropna(subset=[target_col])
    X = df.drop(columns=[target_col])
    y = df[target_col].astype(int)

    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
    }
    if y_prob is not None:
        metrics["roc_auc"] = float(roc_auc_score(y_test, y_prob))

    payload = {
        "dataset": str(dataset_path),
        "model_path": str(model_path),
        "target_col": target_col,
        "metrics": metrics,
    }

    (report_dir / "tabular_test_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "tabular_test_report.md").write_text(
        f"# 结构化模型测试报告\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```",
        encoding="utf-8",
    )
    return payload


def evaluate_text_model(dataset_path: str | Path, model_path: str | Path = DEFAULT_TEXT_MODEL, tfidf_path: str | Path = DEFAULT_TEXT_TFIDF, text_col: str = "clean_text", label_col: str = "is_depression", report_dir: str | Path = DEFAULT_REPORT_DIR) -> dict[str, Any]:
    dataset_path = Path(dataset_path)
    model_path = Path(model_path)
    tfidf_path = Path(tfidf_path)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(dataset_path)
    df = standardize_text_dataset(df, text_col=text_col, label_col=label_col)
    df[text_col] = df[text_col].fillna("").astype(str).map(clean_text)

    X = df[text_col]
    y = df[label_col].astype(int)

    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)

    with open(tfidf_path, "rb") as f:
        tfidf = pickle.load(f)
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    X_vec = tfidf.transform(X_test)
    y_pred = model.predict(X_vec)
    y_prob = model.predict_proba(X_vec)[:, 1]

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
    }

    payload = {
        "dataset": str(dataset_path),
        "model_path": str(model_path),
        "tfidf_path": str(tfidf_path),
        "text_col": text_col,
        "label_col": label_col,
        "metrics": metrics,
    }

    (report_dir / "text_test_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "text_test_report.md").write_text(
        f"# 文本模型测试报告\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```",
        encoding="utf-8",
    )
    return payload


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate trained depression models")
    parser.add_argument("--mode", choices=["tabular", "text", "both"], default="both")
    parser.add_argument("--tabular-dataset", default=str(Path("datasets") / "structured" / "student_depression_dataset.csv"))
    parser.add_argument("--text-dataset", default=str(Path("datasets") / "text" / "depression_dataset_reddit_cleaned.csv"))
    parser.add_argument("--target-col", default=None)
    parser.add_argument("--text-col", default="clean_text")
    parser.add_argument("--label-col", default="is_depression")
    args = parser.parse_args()

    results = {}
    if args.mode in {"tabular", "both"}:
        results["tabular"] = evaluate_tabular_model(args.tabular_dataset, target_col=args.target_col)
    if args.mode in {"text", "both"}:
        results["text"] = evaluate_text_model(args.text_dataset, text_col=args.text_col, label_col=args.label_col)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
