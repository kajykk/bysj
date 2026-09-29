from __future__ import annotations

from pathlib import Path
import json
import pickle

import pandas as pd
from catboost import CatBoostClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score, roc_auc_score, confusion_matrix
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:
    from .data_utils import clean_tabular_dataframe, find_target_column, load_csv, split_train_val_test
except ImportError:
    import sys
    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parent))
    from data_utils import clean_tabular_dataframe, find_target_column, load_csv, split_train_val_test


RANDOM_STATE = 42
DEFAULT_DATASET = Path("datasets") / "structured" / "student_depression_dataset.csv"
DEFAULT_OUTPUT_DIR = Path("models") / "artifacts" / "depression_tabular"


def load_and_clean_data(csv_path: Path, target_col: str) -> pd.DataFrame:
    df = load_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    df = clean_tabular_dataframe(df)

    if target_col not in df.columns:
        raise ValueError(f"目标列 `{target_col}` 不存在。可选列: {df.columns.tolist()}")

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "N/A": pd.NA, "NA": pd.NA})

    if "Sleep Duration" in df.columns:
        sleep_map = {
            "less than 5 hours": 0,
            "5-6 hours": 1,
            "7-8 hours": 2,
            "more than 8 hours": 3,
        }
        df["SleepDurationOrdinal"] = df["Sleep Duration"].astype(str).str.lower().str.strip().map(sleep_map)

    if "Dietary Habits" in df.columns:
        diet_map = {"unhealthy": 0, "moderate": 1, "healthy": 2}
        df["DietaryHabitsOrdinal"] = df["Dietary Habits"].astype(str).str.lower().str.strip().map(diet_map)

    if "Age" in df.columns:
        df["Age"] = pd.to_numeric(df["Age"], errors="coerce")
        df["AgeGroup"] = pd.cut(
            df["Age"],
            bins=[0, 18, 25, 35, 45, 60, 120],
            labels=["<=18", "19-25", "26-35", "36-45", "46-60", "60+"],
            include_lowest=True,
        )

    numeric_candidates = [
        "Academic Pressure",
        "Work Pressure",
        "CGPA",
        "Study Satisfaction",
        "Job Satisfaction",
        "Work/Study Hours",
        "Financial Stress",
    ]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    numeric_features = X.select_dtypes(include=["number"]).columns.tolist()
    categorical_features = [c for c in X.columns if c not in numeric_features]

    numeric_transformer = Pipeline(
        steps=[("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ]
    )


def train_and_tune(X_train, y_train, preprocessor: ColumnTransformer):
    model_spaces = {
        "logistic_regression": (
            LogisticRegression(class_weight="balanced", max_iter=3000, random_state=RANDOM_STATE),
            {
                "model__C": [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0],
                "model__solver": ["liblinear", "lbfgs"],
            },
        ),
        "random_forest": (
            __import__("sklearn.ensemble", fromlist=["RandomForestClassifier"]).RandomForestClassifier(
                class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1
            ),
            {
                "model__n_estimators": [200, 300, 500],
                "model__max_depth": [None, 8, 12, 20],
                "model__min_samples_split": [2, 5, 10],
                "model__min_samples_leaf": [1, 2, 4],
                "model__max_features": ["sqrt", "log2", None],
            },
        ),
        "catboost": (
            CatBoostClassifier(
                iterations=800,
                depth=6,
                learning_rate=0.05,
                loss_function="Logloss",
                eval_metric="AUC",
                random_seed=RANDOM_STATE,
                verbose=0,
            ),
            {
                "model__iterations": [400, 800, 1200],
                "model__depth": [4, 6, 8],
                "model__learning_rate": [0.01, 0.03, 0.05, 0.1],
            },
        ),
    }

    best_name = None
    best_search = None
    all_cv_results = {}

    for model_name, (estimator, param_dist) in model_spaces.items():
        pipeline = Pipeline(steps=[("preprocessor", preprocessor), ("model", estimator)])
        search = RandomizedSearchCV(
            estimator=pipeline,
            param_distributions=param_dist,
            n_iter=min(10, sum(len(v) for v in param_dist.values())),
            scoring="f1",
            cv=5,
            n_jobs=-1,
            random_state=RANDOM_STATE,
            verbose=1,
        )
        search.fit(X_train, y_train)
        all_cv_results[model_name] = {"best_cv_score_f1": float(search.best_score_), "best_params": search.best_params_}
        if best_search is None or search.best_score_ > best_search.best_score_:
            best_name = model_name
            best_search = search

    return best_name, best_search, all_cv_results


def evaluate_model(model, X_test, y_test, threshold: float | None = None) -> dict:
    if threshold is not None and hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= threshold).astype(int)
    else:
        y_pred = model.predict(X_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
    }
    if hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X_test)[:, 1]
        metrics["roc_auc"] = float(roc_auc_score(y_test, y_prob))
    if threshold is not None:
        metrics["threshold"] = float(threshold)
    return metrics


def find_best_threshold(model, X_val, y_val) -> dict:
    if not hasattr(model, "predict_proba"):
        return {"threshold": 0.5, "f1": 0.0, "precision": 0.0, "recall": 0.0}
    y_prob = model.predict_proba(X_val)[:, 1]
    best = {"threshold": 0.5, "f1": -1.0, "precision": 0.0, "recall": 0.0}
    for threshold in [round(x / 100, 2) for x in range(10, 91)]:
        y_pred = (y_prob >= threshold).astype(int)
        f1 = float(f1_score(y_val, y_pred, zero_division=0))
        if f1 > best["f1"]:
            best = {
                "threshold": float(threshold),
                "f1": f1,
                "precision": float(precision_score(y_val, y_pred, zero_division=0)),
                "recall": float(recall_score(y_val, y_pred, zero_division=0)),
            }
    return best


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train depression tabular classifier")
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET))
    parser.add_argument("--target", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_and_clean_data(dataset_path, args.target or find_target_column(load_csv(dataset_path)))
    target_col = args.target or find_target_column(df)

    X = df.drop(columns=[target_col])
    y = df[target_col]

    X_train, X_val, X_test, y_train, y_val, y_test = split_train_val_test(X, y, test_size=0.15, val_size=0.15, random_state=RANDOM_STATE)

    preprocessor = build_preprocessor(X_train)
    best_model_name, best_search, cv_results = train_and_tune(X_train, y_train, preprocessor)
    best_model = best_search.best_estimator_
    best_threshold_info = find_best_threshold(best_model, X_val, y_val)
    test_metrics = evaluate_model(best_model, X_test, y_test, threshold=best_threshold_info["threshold"])
    val_metrics = evaluate_model(best_model, X_val, y_val, threshold=best_threshold_info["threshold"])

    model_path = output_dir / "best_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(best_model, f)

    metrics_payload = {
        "dataset": str(dataset_path),
        "target_col": target_col,
        "best_model": best_model_name,
        "best_params": best_search.best_params_,
        "best_threshold_info": best_threshold_info,
        "cv_results": cv_results,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = f"""# 结构化抑郁模型训练报告

- 数据集: `{dataset_path}`
- 目标列: `{target_col}`
- 最优模型: `{best_model_name}`
- 最优阈值: `{best_threshold_info['threshold']}`

## 阈值搜索结果
```json
{json.dumps(best_threshold_info, ensure_ascii=False, indent=2)}
```

## 验证集
```json
{json.dumps(val_metrics, ensure_ascii=False, indent=2)}
```

## 测试集
```json
{json.dumps(test_metrics, ensure_ascii=False, indent=2)}
```
"""
    (output_dir / "training_report.md").write_text(report, encoding="utf-8")

    print("训练完成")
    print(f"模型文件: {model_path}")
    print(f"指标文件: {output_dir / 'metrics.json'}")
    print(f"报告文件: {output_dir / 'training_report.md'}")


if __name__ == "__main__":
    main()
