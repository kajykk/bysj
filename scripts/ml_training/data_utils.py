from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


YES_NO_MAP = {
    "yes": 1,
    "no": 0,
    "YES": 1,
    "NO": 0,
    "Yes": 1,
    "No": 0,
    "y": 1,
    "n": 0,
    "true": 1,
    "false": 0,
    "True": 1,
    "False": 0,
}


def load_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def clean_text(text: str) -> str:
    text = "" if text is None else str(text)
    text = text.lower()
    text = re.sub(r"http\S+|www\S+|https\S+", " ", text)
    text = re.sub(r"@\w+", " ", text)
    text = re.sub(r"#", " ", text)
    text = re.sub(r"<.*?>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def standardize_text_dataset(df: pd.DataFrame, text_col: str, label_col: str) -> pd.DataFrame:
    df = df.copy()

    if text_col not in df.columns:
        raise ValueError(f"Text column '{text_col}' not found. Available columns: {list(df.columns)}")
    if label_col not in df.columns:
        raise ValueError(f"Label column '{label_col}' not found. Available columns: {list(df.columns)}")

    df = df[[text_col, label_col]].dropna()
    df[text_col] = df[text_col].astype(str).map(clean_text)

    if df[label_col].dtype == "object":
        df[label_col] = df[label_col].astype(str).str.strip().str.lower()
        mapping = {
            "depression": 1,
            "depressed": 1,
            "yes": 1,
            "true": 1,
            "1": 1,
            "non-depression": 0,
            "nondepression": 0,
            "no": 0,
            "false": 0,
            "0": 0,
            "negative": 0,
            "positive": 1,
        }
        df[label_col] = df[label_col].map(mapping)

    df = df.dropna(subset=[label_col])
    df[label_col] = df[label_col].astype(int)
    return df


def find_target_column(df: pd.DataFrame, preferred: Optional[str] = None) -> str:
    if preferred and preferred in df.columns:
        return preferred

    candidates = ["label", "target", "Depression", "depression", "is_depression", "depressed", "status", "outcome"]
    for col in candidates:
        if col in df.columns:
            return col

    for col in df.columns:
        if df[col].nunique(dropna=True) == 2:
            return col

    raise ValueError("No target column found. Please pass target_col manually.")


def clean_tabular_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    drop_cols = []
    for col in df.columns:
        low = col.lower()
        if low.startswith("unnamed"):
            drop_cols.append(col)
        if low in {"id", "name", "timestamp", "user_id", "index"}:
            drop_cols.append(col)

    df = df.drop(columns=list(set(drop_cols)), errors="ignore")
    df = df.drop_duplicates()

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()

    for col in df.columns:
        if df[col].dtype == "object":
            vals = set(df[col].dropna().astype(str).unique().tolist())
            if vals.issubset(set(YES_NO_MAP.keys())):
                df[col] = df[col].map(YES_NO_MAP)

    return df


def split_train_val_test(X, y, test_size: float = 0.15, val_size: float = 0.15, random_state: int = 42):
    from sklearn.model_selection import train_test_split

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=test_size + val_size, random_state=random_state, stratify=y
    )

    rel_test_size = test_size / (test_size + val_size)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=rel_test_size, random_state=random_state, stratify=y_temp
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


def save_dataframe(df: pd.DataFrame, path: str | Path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
