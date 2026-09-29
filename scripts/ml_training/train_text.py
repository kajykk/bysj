from __future__ import annotations

import hashlib
from pathlib import Path
import json
import pickle

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score, roc_auc_score, confusion_matrix
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.pipeline import Pipeline

from data_utils import clean_text, standardize_text_dataset


RANDOM_STATE = 42
DEFAULT_DATASET = Path("datasets") / "text" / "depression_dataset_reddit_cleaned.csv"
DEFAULT_OUTPUT_DIR = Path("models") / "artifacts" / "text_depression_classifier"


def compute_dataset_fingerprint(df: pd.DataFrame) -> str:
    """对数据集内容计算 SHA256 指纹，用于评估可追溯。

    指纹基于 (text, label) 两列的规范字符串表示，去重排序后哈希，
    确保相同数据 → 相同指纹；任何样本变动 → 指纹变化。
    """
    norm = pd.DataFrame({"text": df["text"].astype(str), "label": df["label"].astype(int)})
    # 排序保证顺序无关
    sorted_rows = norm.sort_values(["text", "label"]).reset_index(drop=True)
    content = sorted_rows.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def compute_split_hash(train_idx: list[int], test_idx: list[int]) -> str:
    """对训练/测试划分索引计算哈希，用于后续评估校验是否使用了同一划分。"""
    payload = json.dumps({"train_idx": sorted(train_idx), "test_idx": sorted(test_idx)}, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_merged_dataset(reddit_csv: Path, twitter_csv: Path) -> pd.DataFrame:
    reddit_df = pd.read_csv(reddit_csv)
    twitter_df = pd.read_csv(twitter_csv)

    reddit = reddit_df[["clean_text", "is_depression"]].copy()
    reddit.columns = ["text", "label"]

    twitter = twitter_df[["post_text", "label"]].copy()
    twitter.columns = ["text", "label"]

    merged = pd.concat([reddit, twitter], ignore_index=True)
    merged = merged.dropna(subset=["text", "label"])
    merged["text"] = merged["text"].astype(str).map(clean_text)
    merged = merged[merged["text"].str.len() >= 5]
    merged["label"] = pd.to_numeric(merged["label"], errors="coerce").fillna(0).astype(int)
    merged = merged[merged["label"].isin([0, 1])]
    merged = merged.drop_duplicates(subset=["text"]).reset_index(drop=True)
    return merged


def load_single_text_dataset(csv_path: Path, text_col: str, label_col: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = standardize_text_dataset(df, text_col=text_col, label_col=label_col)
    df = df.rename(columns={text_col: "text", label_col: "label"})
    df["text"] = df["text"].fillna("").astype(str).map(clean_text)
    return df[["text", "label"]]


def build_and_tune_model(X_train, y_train):
    pipeline = Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    strip_accents="unicode",
                    sublinear_tf=True,
                    max_features=80000,
                ),
            ),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=3000,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    param_dist = {
        "tfidf__ngram_range": [(1, 1), (1, 2)],
        "tfidf__min_df": [2, 3, 5],
        "tfidf__max_df": [0.9, 0.95, 1.0],
        "model__C": [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0],
        "model__solver": ["liblinear", "lbfgs"],
    }

    search = RandomizedSearchCV(
        estimator=pipeline,
        param_distributions=param_dist,
        n_iter=12,
        scoring="f1",
        cv=5,
        n_jobs=-1,
        random_state=RANDOM_STATE,
        verbose=1,
    )
    search.fit(X_train, y_train)
    return search


def evaluate(model, X_test, y_test) -> dict:
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train text depression classifier")
    parser.add_argument("--reddit", default=str(Path("datasets") / "text" / "depression_dataset_reddit_cleaned.csv"))
    parser.add_argument("--twitter", default=str(Path("datasets") / "Mental-Health-Twitter.csv"))
    parser.add_argument("--dataset", default=None, help="Single text dataset path")
    parser.add_argument("--text-col", default="clean_text")
    parser.add_argument("--label-col", default="is_depression")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dataset:
        df = load_single_text_dataset(Path(args.dataset), args.text_col, args.label_col)
    else:
        df = load_merged_dataset(Path(args.reddit), Path(args.twitter))

    # 计算数据集指纹 (评估可追溯防泄露)
    dataset_fingerprint = compute_dataset_fingerprint(df)

    X = df["text"]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    # 持久化划分索引，确保后续 evaluate_models.py 使用同一划分 (避免数据泄露)
    train_idx = X_train.index.tolist()
    test_idx = X_test.index.tolist()
    split_hash = compute_split_hash(train_idx, test_idx)
    split_payload = {
        "train_idx": train_idx,
        "test_idx": test_idx,
        "split_hash": split_hash,
        "dataset_fingerprint": dataset_fingerprint,
        "test_size_ratio": 0.2,
        "random_state": RANDOM_STATE,
        "stratified": True,
        "total_samples": int(df.shape[0]),
        "train_samples": len(train_idx),
        "test_samples": len(test_idx),
    }
    (output_dir / "split_indices.json").write_text(
        json.dumps(split_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    search = build_and_tune_model(X_train, y_train)
    best_pipeline = search.best_estimator_
    metrics = evaluate(best_pipeline, X_test, y_test)

    tfidf = best_pipeline.named_steps["tfidf"]
    model = best_pipeline.named_steps["model"]

    tfidf_path = output_dir / "text_tfidf.pkl"
    model_path = output_dir / "text_model.pkl"
    with open(tfidf_path, "wb") as f:
        pickle.dump(tfidf, f)
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    metrics_payload = {
        "best_params": search.best_params_,
        "best_cv_f1": float(search.best_score_),
        "test_metrics": metrics,
        "sample_count": int(df.shape[0]),
        # v1.4 新增: 评估口径防泄露字段
        "eval_protocol": {
            "mode": "held_out_test",
            "eval_split_hash": split_hash,
            "dataset_fingerprint": dataset_fingerprint,
            "test_samples": len(test_idx),
            "test_size_ratio": 0.2,
            "random_state": RANDOM_STATE,
            "stratified": True,
            "note": "评估对象 = 训练时未见过的不相交测试集，无数据泄露",
        },
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = f"""# 文本抑郁分类模型训练报告

- 样本量: {df.shape[0]}
- 数据集指纹 (SHA256): `{dataset_fingerprint[:16]}...`
- 评估划分哈希 (SHA256): `{split_hash[:16]}...`
- 评估口径: 训练时未见过的不相交测试集 (80/20, random_state={RANDOM_STATE}, stratified)

## 最优参数
```json
{json.dumps(search.best_params_, ensure_ascii=False, indent=2)}
```

## 测试集指标 (held-out, 无泄露)
```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

## 复现说明
- 训练时已保存划分索引到 `split_indices.json`
- 评估时使用相同划分，确保指标可比、可复现
- 任何 metrics.json 缺少 `eval_protocol.eval_split_hash` 字段的文本评估，应视为不可信
"""
    (output_dir / "training_report.md").write_text(report, encoding="utf-8")

    print("训练完成")
    print(f"向量器: {tfidf_path}")
    print(f"模型: {model_path}")
    print(f"指标: {output_dir / 'metrics.json'}")
    print(f"报告: {output_dir / 'training_report.md'}")


if __name__ == "__main__":
    main()
