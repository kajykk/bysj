from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.safe_pickle import safe_joblib_load

from data_utils import clean_tabular_dataframe, clean_text, find_target_column, load_csv, standardize_text_dataset


# 受控模型目录：待加载工件必须位于其下（L-08）。
MODELS_ROOT = PROJECT_ROOT / "models"

TABULAR_MODEL_PATH = MODELS_ROOT / "artifacts" / "depression_tabular" / "best_model.pkl"
TEXT_TFIDF_PATH = MODELS_ROOT / "artifacts" / "text_depression_classifier" / "text_tfidf.pkl"
TEXT_MODEL_PATH = MODELS_ROOT / "artifacts" / "text_depression_classifier" / "text_model.pkl"


def predict_tabular(input_json: str, model_path: str | Path = TABULAR_MODEL_PATH) -> dict:
    model_path = Path(model_path)
    # 白名单加载（路径 + 大小 + .sha256 侧车 + 反序列化类白名单），替代裸 pickle.load。
    model = safe_joblib_load(model_path, trusted_root=MODELS_ROOT, model_id="tabular")

    data = json.loads(input_json)
    X = pd.DataFrame([data])
    pred = int(model.predict(X)[0])
    proba = float(model.predict_proba(X)[:, 1][0]) if hasattr(model, "predict_proba") else None
    return {"prediction": pred, "probability": proba, "model_path": str(model_path)}


def predict_text(text: str, tfidf_path: str | Path = TEXT_TFIDF_PATH, model_path: str | Path = TEXT_MODEL_PATH) -> dict:
    tfidf_path = Path(tfidf_path)
    model_path = Path(model_path)
    tfidf = safe_joblib_load(tfidf_path, trusted_root=MODELS_ROOT, model_id="text:tfidf")
    model = safe_joblib_load(model_path, trusted_root=MODELS_ROOT, model_id="text:model")

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
