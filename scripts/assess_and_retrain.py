from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DATASETS = ROOT / "datasets"
RESULTS_DIR = ROOT / "model_assessment"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


LIGHTWEIGHT_THRESHOLD = 0.85


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_report(name: str, data: dict[str, Any]) -> None:
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# {name}", "", "```json", json.dumps(data, ensure_ascii=False, indent=2), "```"]
    (RESULTS_DIR / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def evaluate_current_models() -> dict[str, Any]:
    from ml_training.evaluate_models import evaluate_tabular_model, evaluate_text_model

    tabular_dataset = DATASETS / "student_depression_dataset.csv"
    text_dataset = DATASETS / "depression_dataset_reddit_cleaned.csv"

    results: dict[str, Any] = {"tabular": None, "text": None}
    try:
        results["tabular"] = evaluate_tabular_model(tabular_dataset)
    except Exception as exc:
        results["tabular"] = {"error": str(exc)}
    try:
        results["text"] = evaluate_text_model(text_dataset)
    except Exception as exc:
        results["text"] = {"error": str(exc)}
    return results


def decide_retrain(results: dict[str, Any]) -> bool:
    for item in results.values():
        if not isinstance(item, dict) or item.get("error"):
            return True
        metrics = item.get("metrics", {})
        score = max([float(v) for v in [metrics.get("roc_auc"), metrics.get("f1"), metrics.get("accuracy")] if isinstance(v, (int, float))] or [0.0])
        if score < LIGHTWEIGHT_THRESHOLD:
            return True
    return False


def train_lightweight_baseline(kind: str) -> dict[str, Any]:
    if kind == "tabular":
        code = r'''
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path.cwd() / "scripts"))
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score, classification_report
from ml_training.data_utils import load_csv, clean_tabular_dataframe, find_target_column
from joblib import dump
import pandas as pd
root = Path("datasets")
df = load_csv(root / "student_depression_dataset.csv")
df = clean_tabular_dataframe(df)
target = find_target_column(df)
df = df.dropna(subset=[target])
X = df.drop(columns=[target])
y = df[target].astype(int)
for col in X.columns:
    if X[col].dtype == "object":
        X[col] = X[col].astype("category").cat.codes
num_cols = list(X.columns)
pre = ColumnTransformer([("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), num_cols)], remainder="drop")
model = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", n_jobs=1))])
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]
out = {
    "accuracy": float(accuracy_score(y_test, y_pred)),
    "precision": float(precision_score(y_test, y_pred, zero_division=0)),
    "recall": float(recall_score(y_test, y_pred, zero_division=0)),
    "f1": float(f1_score(y_test, y_pred, zero_division=0)),
    "roc_auc": float(roc_auc_score(y_test, y_prob)),
    "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
}
Path("model_assessment").mkdir(exist_ok=True)
dump(model, Path("model_assessment") / "tabular_logistic_baseline.pkl")
Path("model_assessment/tabular_logistic_baseline.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
'''
        subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), check=True)
        return _load_json(RESULTS_DIR / "tabular_logistic_baseline.json")

    code = r'''
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path.cwd() / "scripts"))
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score, classification_report
from ml_training.data_utils import clean_text
import pandas as pd
import joblib
root = Path("datasets")
df = pd.read_csv(root / "depression_dataset_reddit_cleaned.csv")
text_col = "clean_text"
label_col = "is_depression"
df[text_col] = df[text_col].fillna("").astype(str).map(clean_text)
X = df[text_col]
y = df[label_col].astype(int)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
model = Pipeline([("tfidf", TfidfVectorizer(max_features=50000, ngram_range=(1, 2), min_df=2)), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])
model.fit(X_train, y_train)
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]
out = {
    "accuracy": float(accuracy_score(y_test, y_pred)),
    "precision": float(precision_score(y_test, y_pred, zero_division=0)),
    "recall": float(recall_score(y_test, y_pred, zero_division=0)),
    "f1": float(f1_score(y_test, y_pred, zero_division=0)),
    "roc_auc": float(roc_auc_score(y_test, y_prob)),
    "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
}
Path("model_assessment").mkdir(exist_ok=True)
joblib.dump(model, Path("model_assessment") / "text_tfidf_logistic_baseline.pkl")
Path("model_assessment/text_tfidf_logistic_baseline.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
'''
    subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), check=True)
    return _load_json(RESULTS_DIR / "text_tfidf_logistic_baseline.json")


def main() -> None:
    assessment = evaluate_current_models()
    retrain_needed = decide_retrain(assessment)
    report = {"current_models": assessment, "retrain_needed": retrain_needed}
    _write_report("assessment_summary", report)

    if not retrain_needed:
        return

    retrained: dict[str, Any] = {}
    try:
        retrained["tabular_logistic_baseline"] = train_lightweight_baseline("tabular")
    except Exception as exc:
        retrained["tabular_logistic_baseline"] = {"error": str(exc)}
    try:
        retrained["text_tfidf_logistic_baseline"] = train_lightweight_baseline("text")
    except Exception as exc:
        retrained["text_tfidf_logistic_baseline"] = {"error": str(exc)}

    report["retrained"] = retrained
    _write_report("assessment_summary", report)


if __name__ == "__main__":
    main()
