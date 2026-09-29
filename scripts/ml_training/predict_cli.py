from __future__ import annotations

from pathlib import Path
import argparse
import json
import pickle

import pandas as pd

from data_utils import clean_tabular_dataframe, clean_text, find_target_column, load_csv, standardize_text_dataset


TABULAR_MODEL_PATH = Path("models") / "artifacts" / "depression_tabular" / "best_model.pkl"
TEXT_TFIDF_PATH = Path("models") / "artifacts" / "text_depression_classifier" / "text_tfidf.pkl"
TEXT_MODEL_PATH = Path("models") / "artifacts" / "text_depression_classifier" / "text_model.pkl"


def predict_tabular(input_json: str, model_path: str | Path = TABULAR_MODEL_PATH) -> dict:
    model_path = Path(model_path)
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    data = json.loads(input_json)
    X = pd.DataFrame([data])
    pred = int(model.predict(X)[0])
    proba = float(model.predict_proba(X)[:, 1][0]) if hasattr(model, "predict_proba") else None
    return {"prediction": pred, "probability": proba, "model_path": str(model_path)}


def predict_text(text: str, tfidf_path: str | Path = TEXT_TFIDF_PATH, model_path: str | Path = TEXT_MODEL_PATH) -> dict:
    tfidf_path = Path(tfidf_path)
    model_path = Path(model_path)
    with open(tfidf_path, "rb") as f:
        tfidf = pickle.load(f)
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    cleaned = clean_text(text)
    vec = tfidf.transform([cleaned])
    pred = int(model.predict(vec)[0])
    proba = float(model.predict_proba(vec)[:, 1][0])
    return {"prediction": pred, "probability": proba, "model_path": str(model_path), "tfidf_path": str(tfidf_path)}


def main():
    parser = argparse.ArgumentParser(description="CLI prediction for trained models")
    parser.add_argument("--mode", choices=["tabular", "text"], required=True)
    parser.add_argument("--input", required=True, help="JSON for tabular or raw text for text mode")
    args = parser.parse_args()

    if args.mode == "tabular":
        result = predict_tabular(args.input)
    else:
        result = predict_text(args.input)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
