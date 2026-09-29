from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml_training.data_utils import clean_tabular_dataframe, find_target_column, load_csv

DATASET = ROOT / "datasets" / "student_depression_dataset.csv"
OUT = ROOT / "model_assessment" / "structured_run"
OUT.mkdir(parents=True, exist_ok=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Sleep Duration" in df.columns:
        sleep_map = {"less than 5 hours": 0, "5-6 hours": 1, "7-8 hours": 2, "more than 8 hours": 3}
        df["SleepDurationOrdinal"] = (
            df["Sleep Duration"].astype(str).str.lower().str.strip().map(sleep_map).fillna(2).astype(int)
        )
    if "Dietary Habits" in df.columns:
        diet_map = {"unhealthy": 0, "moderate": 1, "healthy": 2}
        df["DietaryHabitsOrdinal"] = (
            df["Dietary Habits"].astype(str).str.lower().str.strip().map(diet_map).fillna(1).astype(int)
        )
    if "Age" in df.columns:
        df["Age"] = pd.to_numeric(df["Age"], errors="coerce")
        df["AgeGroup"] = pd.cut(
            df["Age"],
            bins=[0, 18, 25, 35, 45, 60, 120],
            labels=["<=18", "19-25", "26-35", "36-45", "46-60", "60+"],
            include_lowest=True,
        ).astype(str).replace({"nan": "19-25"})
    return df


def evaluate(model, X_test, y_test):
    pred = model.predict(X_test)
    prob = model.predict_proba(X_test)[:, 1]
    return {
        "accuracy": float(accuracy_score(y_test, pred)),
        "precision": float(precision_score(y_test, pred, zero_division=0)),
        "recall": float(recall_score(y_test, pred, zero_division=0)),
        "f1": float(f1_score(y_test, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, prob)),
    }


def main() -> None:
    df = load_csv(DATASET)
    df = clean_tabular_dataframe(df)
    target = find_target_column(df)
    df = build_features(df)
    X = df.drop(columns=[target])
    y = df[target].astype(int)

    num_cols = X.select_dtypes(include=["number"]).columns.tolist()
    cat_cols = [c for c in X.columns if c not in num_cols]
    preprocessor = ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), num_cols),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")), ("ohe", OneHotEncoder(handle_unknown="ignore"))]), cat_cols),
        ]
    )

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    candidates = {
        "logistic_regression": Pipeline([("pre", preprocessor), ("clf", LogisticRegression(max_iter=3000, class_weight="balanced"))]),
        "random_forest": Pipeline([("pre", preprocessor), ("clf", RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1, class_weight="balanced"))]),
    }

    results: dict[str, dict[str, float]] = {}
    best_name = None
    best_model = None
    best_metrics = None
    best_score = -1.0

    for name, model in candidates.items():
        model.fit(X_train, y_train)
        metrics = evaluate(model, X_test, y_test)
        results[name] = metrics
        if metrics["f1"] > best_score:
            best_score = metrics["f1"]
            best_name = name
            best_model = model
            best_metrics = metrics

    assert best_name is not None and best_model is not None and best_metrics is not None
    joblib.dump(best_model, OUT / "best_model.pkl")
    payload = {"dataset": str(DATASET), "target": target, "results": results, "best": best_name, "best_metrics": best_metrics}
    (OUT / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "training_report.md").write_text("# Structured fallback training\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
