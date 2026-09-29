"""多模型对比实验 — 论文实验章节·模型选型。

7 个模型在同一数据划分(70/15/15 分层)与统一预处理下对比：
  Logistic Regression / Decision Tree / Random Forest / Gradient Boosting /
  CatBoost / XGBoost / LightGBM

输出 (reports/eda/student_depression/compare/):
  - model_comparison.csv / model_comparison.md  对比表
  - 01_metrics_bar.png        多指标分组柱状图
  - 02_roc_overlay.png        ROC 曲线叠加
  - 03_pr_overlay.png         PR 曲线叠加
  - 04_train_time.png         训练时间对比
  - 05_radar.png              雷达图(5指标)
  - comparison_summary.json   原始指标
"""
from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (GradientBoostingClassifier,
                               RandomForestClassifier)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                              precision_recall_curve, recall_score, roc_auc_score,
                              roc_curve)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import seaborn as sns
sns.set_style("whitegrid")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

DATASET_PATH = Path("datasets/Student Depression Dataset.csv")
OUTPUT_DIR = Path("reports/eda/student_depression/compare")
RANDOM_STATE = 42
YES_NO_MAP = {"yes": 1, "no": 0, "Yes": 1, "No": 0, "YES": 1, "NO": 0}


def load_and_clean() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH)
    df.columns = [c.strip() for c in df.columns]
    df = df.drop(columns=["id"], errors="ignore")
    for col in ["Have you ever had suicidal thoughts ?", "Family History of Mental Illness"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().map(YES_NO_MAP)
    sleep_map = {"less than 5 hours": 0, "5-6 hours": 1, "7-8 hours": 2, "more than 8 hours": 3}
    df["SleepDurationOrdinal"] = df["Sleep Duration"].astype(str).str.lower().str.strip().map(sleep_map)
    diet_map = {"unhealthy": 0, "moderate": 1, "healthy": 2}
    df["DietaryHabitsOrdinal"] = df["Dietary Habits"].astype(str).str.lower().str.strip().map(diet_map)
    for col in ["Age", "Academic Pressure", "Work Pressure", "CGPA",
                "Study Satisfaction", "Job Satisfaction", "Work/Study Hours", "Financial Stress"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Gender"] = df["Gender"].str.strip().map({"Male": 0, "Female": 1})
    df = df.drop(columns=["City", "Profession", "Degree", "Sleep Duration", "Dietary Habits"], errors="ignore")
    df = df.dropna(subset=["Depression"])
    df["Depression"] = df["Depression"].astype(int)
    return df


def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    numeric_features = X.select_dtypes(include=["number"]).columns.tolist()
    categorical_features = [c for c in X.columns if c not in numeric_features]
    numeric_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    transformers = [("num", numeric_transformer, numeric_features)]
    if categorical_features:
        transformers.append(("cat", categorical_transformer, categorical_features))
    return ColumnTransformer(transformers)


def get_models() -> dict:
    """7 个模型，参数统一为合理默认（不调参，公平对比基线）。"""
    return {
        "Logistic Regression": LogisticRegression(max_iter=3000, random_state=RANDOM_STATE, n_jobs=-1),
        "Decision Tree": DecisionTreeClassifier(max_depth=8, random_state=RANDOM_STATE),
        "Random Forest": RandomForestClassifier(n_estimators=300, max_depth=12,
                                                 random_state=RANDOM_STATE, n_jobs=-1),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=300, max_depth=4,
                                                         learning_rate=0.05, random_state=RANDOM_STATE),
        "CatBoost": CatBoostClassifier(iterations=800, depth=6, learning_rate=0.05,
                                        loss_function="Logloss", eval_metric="AUC",
                                        random_seed=RANDOM_STATE, verbose=0),
        "XGBoost": XGBClassifier(n_estimators=800, max_depth=6, learning_rate=0.05,
                                  eval_metric="logloss", random_state=RANDOM_STATE, n_jobs=-1,
                                  tree_method="hist"),
        "LightGBM": LGBMClassifier(n_estimators=800, max_depth=6, learning_rate=0.05,
                                    random_state=RANDOM_STATE, n_jobs=-1, verbose=-1),
    }


def find_best_threshold(y_true, y_prob) -> float:
    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.05, 0.95, 0.01):
        f1 = f1_score(y_true, (y_prob >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return float(best_t)


def evaluate(model, X_test, y_test, threshold) -> dict:
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "threshold": float(threshold),
    }


# 模型显示颜色（与图表一致）
MODEL_COLORS = {
    "Logistic Regression": "#9E9E9E",
    "Decision Tree": "#8D6E63",
    "Random Forest": "#4CAF50",
    "Gradient Boosting": "#FF9800",
    "CatBoost": "#2196F3",
    "XGBoost": "#F44336",
    "LightGBM": "#9C27B0",
}


def plot_metrics_bar(df_metrics: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(13, 6.5))
    metrics = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    labels = ["Accuracy", "Precision", "Recall", "F1", "ROC AUC"]
    x = np.arange(len(df_metrics))
    width = 0.15
    for i, (m, lab) in enumerate(zip(metrics, labels)):
        offset = (i - 2) * width
        bars = ax.bar(x + offset, df_metrics[m], width, label=lab, alpha=0.9)
        # 在 F1 柱上标数值
        if m == "f1":
            for b, v in zip(bars, df_metrics[m]):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.005, f"{v:.3f}",
                        ha="center", va="bottom", fontsize=7, rotation=0)
    ax.set_xticks(x)
    ax.set_xticklabels(df_metrics["model"], rotation=15, ha="right")
    ax.set_ylabel("分数")
    ax.set_title("多模型性能对比 — 5 项指标 (测试集)", fontsize=13)
    ax.set_ylim(0.5, 1.02)
    ax.legend(loc="lower right", ncol=5)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "01_metrics_bar.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_roc_overlay(results: dict, y_test):
    fig, ax = plt.subplots(figsize=(9, 7))
    for name, r in results.items():
        fpr, tpr, _ = roc_curve(y_test, r["y_prob"])
        ax.plot(fpr, tpr, color=MODEL_COLORS.get(name, None),
                linewidth=2, label=f"{name} (AUC={r['metrics']['roc_auc']:.4f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4, label="随机 (AUC=0.5)")
    ax.set_xlabel("假正率 (FPR)")
    ax.set_ylabel("真正率 (TPR)")
    ax.set_title("ROC 曲线对比 — 多模型", fontsize=13)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "02_roc_overlay.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_pr_overlay(results: dict, y_test):
    fig, ax = plt.subplots(figsize=(9, 7))
    # 基线：正类比例
    pos_ratio = y_test.mean()
    ax.axhline(y=pos_ratio, color="k", linestyle="--", alpha=0.4,
               label=f"随机基线 (={pos_ratio:.3f})")
    for name, r in results.items():
        precision, recall, _ = precision_recall_curve(y_test, r["y_prob"])
        ax.plot(recall, precision, color=MODEL_COLORS.get(name, None),
                linewidth=2, label=f"{name} (F1={r['metrics']['f1']:.4f})")
    ax.set_xlabel("召回率 (Recall)")
    ax.set_ylabel("精确率 (Precision)")
    ax.set_title("PR 曲线对比 — 多模型", fontsize=13)
    ax.legend(loc="lower left", fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "03_pr_overlay.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_train_time(df_metrics: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = [MODEL_COLORS.get(m, "#999") for m in df_metrics["model"]]
    bars = ax.bar(df_metrics["model"], df_metrics["train_time_sec"], color=colors, alpha=0.85)
    ax.set_ylabel("训练时间 (秒)")
    ax.set_title("各模型训练时间对比 (对数刻度)", fontsize=13)
    ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.3, which="both")
    for b, v in zip(bars, df_metrics["train_time_sec"]):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.1, f"{v:.2f}s",
                ha="center", va="bottom", fontsize=9)
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "04_train_time.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_radar(df_metrics: pd.DataFrame):
    metrics = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    labels = ["Accuracy", "Precision", "Recall", "F1", "ROC AUC"]
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
    for _, row in df_metrics.iterrows():
        vals = [row[m] for m in metrics]
        vals += vals[:1]
        ax.plot(angles, vals, linewidth=2,
                color=MODEL_COLORS.get(row["model"], None), label=row["model"])
        ax.fill(angles, vals, alpha=0.05,
                color=MODEL_COLORS.get(row["model"], None))
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_ylim(0.5, 1.0)
    ax.set_yticks([0.6, 0.7, 0.8, 0.9, 1.0])
    ax.set_yticklabels(["0.6", "0.7", "0.8", "0.9", "1.0"], fontsize=8)
    ax.set_title("多模型雷达图 — 5 指标", fontsize=13, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "05_radar.png", dpi=150, bbox_inches="tight")
    plt.close()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("多模型对比实验")
    df = load_and_clean()
    print(f"数据: {df.shape[0]} 行 × {df.shape[1]} 列")

    X = df.drop(columns=["Depression"])
    y = df["Depression"]
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.3, random_state=RANDOM_STATE, stratify=y)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=RANDOM_STATE, stratify=y_temp)
    print(f"训练 {len(X_train)} / 验证 {len(X_val)} / 测试 {len(X_test)}")

    preprocessor = build_preprocessor(X_train)
    models = get_models()

    results = {}
    rows = []
    for name, estimator in models.items():
        print(f"\n训练: {name} ...", flush=True)
        pipe = Pipeline([("preprocessor", preprocessor), ("model", estimator)])
        t0 = time.time()
        try:
            pipe.fit(X_train, y_train)
        except Exception as e:
            print(f"  [失败] {name}: {e}")
            continue
        train_time = time.time() - t0

        # 预测时间
        t0 = time.time()
        y_prob = pipe.predict_proba(X_test)[:, 1]
        pred_time = time.time() - t0

        # 验证集找最优阈值
        y_val_prob = pipe.predict_proba(X_val)[:, 1]
        best_t = find_best_threshold(y_val, y_val_prob)
        m = evaluate(pipe, X_test, y_test, best_t)
        m["train_time_sec"] = float(train_time)
        m["pred_time_sec"] = float(pred_time)
        print(f"  F1={m['f1']:.4f}  AUC={m['roc_auc']:.4f}  "
              f"训练 {train_time:.2f}s  阈值={best_t:.2f}")
        results[name] = {"metrics": m, "y_prob": y_prob}
        rows.append({"model": name, **m})

    df_metrics = pd.DataFrame(rows).sort_values("f1", ascending=False).reset_index(drop=True)

    # 保存对比表
    df_metrics.to_csv(OUTPUT_DIR / "model_comparison.csv", index=False, encoding="utf-8-sig")

    # Markdown 表
    md_cols = ["model", "accuracy", "precision", "recall", "f1", "roc_auc",
               "threshold", "train_time_sec", "pred_time_sec"]
    md = df_metrics[md_cols].copy()
    for c in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
        md[c] = md[c].map(lambda v: f"{v:.4f}")
    md["threshold"] = md["threshold"].map(lambda v: f"{v:.2f}")
    md["train_time_sec"] = md["train_time_sec"].map(lambda v: f"{v:.2f}")
    md["pred_time_sec"] = md["pred_time_sec"].map(lambda v: f"{v:.4f}")
    md.columns = ["模型", "Accuracy", "Precision", "Recall", "F1", "ROC AUC",
                  "阈值", "训练时间(s)", "预测时间(s)"]
    md.to_markdown(OUTPUT_DIR / "model_comparison.md", index=False)

    # 绘图
    print("\n绘图 ...")
    plot_metrics_bar(df_metrics)
    plot_roc_overlay(results, y_test)
    plot_pr_overlay(results, y_test)
    plot_train_time(df_metrics)
    plot_radar(df_metrics)

    # 汇总 JSON
    summary = {
        "n_models": len(results),
        "best_f1_model": df_metrics.iloc[0]["model"],
        "best_auc_model": df_metrics.sort_values("roc_auc", ascending=False).iloc[0]["model"],
        "fastest_model": df_metrics.sort_values("train_time_sec").iloc[0]["model"],
        "metrics": df_metrics.to_dict(orient="records"),
    }
    (OUTPUT_DIR / "comparison_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"F1 最优: {summary['best_f1_model']}  (F1={df_metrics.iloc[0]['f1']:.4f})")
    best_auc = df_metrics.sort_values("roc_auc", ascending=False).iloc[0]
    print(f"AUC 最优: {summary['best_auc_model']}  (AUC={best_auc['roc_auc']:.4f})")
    fastest = df_metrics.sort_values("train_time_sec").iloc[0]
    print(f"训练最快: {summary['fastest_model']}  ({fastest['train_time_sec']:.2f}s)")
    print(f"\n输出目录: {OUTPUT_DIR}  ({len(list(OUTPUT_DIR.glob('*.png')))} 图)")


if __name__ == "__main__":
    main()
