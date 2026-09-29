"""Model evaluation visualizations for the trained depression tabular model.

Loads the existing trained CatBoost model and generates thesis-ready evaluation plots:
- Confusion matrix (annotated heatmap)
- ROC curve
- Precision-Recall curve
- Feature importance
- Model comparison (CV results)
- Threshold optimization curve

Output: reports/eda/student_depression/eval/
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (confusion_matrix, precision_recall_curve,
                             roc_curve, classification_report)

# Font setup — after seaborn style
sns.set_style("whitegrid")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

DATASET_PATH = Path("datasets/Student Depression Dataset.csv")
MODEL_PATH = Path("models/artifacts/depression_tabular/best_model.pkl")
METRICS_PATH = Path("models/artifacts/depression_tabular/metrics.json")
OUTPUT_DIR = Path("reports/eda/student_depression/eval")
RANDOM_STATE = 42

# Import data utilities from the training script
import sys
sys.path.insert(0, str(Path("scripts/ml_training").resolve()))
from data_utils import clean_tabular_dataframe, find_target_column, load_csv, split_train_val_test


def load_and_clean_data(csv_path: Path, target_col: str) -> pd.DataFrame:
    """Same preprocessing as train_tabular.py"""
    df = load_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    df = clean_tabular_dataframe(df)

    if target_col not in df.columns:
        raise ValueError(f"目标列 `{target_col}` 不存在")

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "nan": pd.NA, "None": pd.NA, "N/A": pd.NA, "NA": pd.NA})

    if "Sleep Duration" in df.columns:
        sleep_map = {"less than 5 hours": 0, "5-6 hours": 1, "7-8 hours": 2, "more than 8 hours": 3}
        df["SleepDurationOrdinal"] = df["Sleep Duration"].astype(str).str.lower().str.strip().map(sleep_map)

    if "Dietary Habits" in df.columns:
        diet_map = {"unhealthy": 0, "moderate": 1, "healthy": 2}
        df["DietaryHabitsOrdinal"] = df["Dietary Habits"].astype(str).str.lower().str.strip().map(diet_map)

    if "Age" in df.columns:
        df["Age"] = pd.to_numeric(df["Age"], errors="coerce")
        df["AgeGroup"] = pd.cut(
            df["Age"], bins=[0, 18, 25, 35, 45, 60, 120],
            labels=["<=18", "19-25", "26-35", "36-45", "46-60", "60+"],
            include_lowest=True)

    numeric_candidates = ["Academic Pressure", "Work Pressure", "CGPA",
                          "Study Satisfaction", "Job Satisfaction",
                          "Work/Study Hours", "Financial Stress"]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def plot_confusion_matrix(y_true, y_pred, title: str, filename: str):
    cm = confusion_matrix(y_true, y_pred)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax,
                xticklabels=["无抑郁 (0)", "抑郁 (1)"],
                yticklabels=["无抑郁 (0)", "抑郁 (1)"])
    ax.set_xlabel("预测值")
    ax.set_ylabel("真实值")
    ax.set_title(title, fontsize=13)

    # Add percentages
    total = cm.sum()
    for i in range(2):
        for j in range(2):
            pct = cm[i][j] / total * 100
            ax.text(j + 0.5, i + 0.65, f"{pct:.1f}%", ha="center", va="center",
                    fontsize=10, color="gray")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close()


def plot_roc_curves(model, X_test, y_test, X_val, y_val):
    """ROC curve for val and test sets"""
    fig, ax = plt.subplots(figsize=(7, 6))

    for X, y, label, color in [(X_val, y_val, "验证集", "#2196F3"),
                                (X_test, y_test, "测试集", "#F44336")]:
        y_prob = model.predict_proba(X)[:, 1]
        fpr, tpr, _ = roc_curve(y, y_prob)
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y, y_prob)
        ax.plot(fpr, tpr, label=f"{label} (AUC = {auc:.3f})", color=color, linewidth=2)

    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="随机分类器")
    ax.set_xlabel("假阳性率 (FPR)")
    ax.set_ylabel("真阳性率 (TPR)")
    ax.set_title("ROC 曲线", fontsize=13)
    ax.legend(loc="lower right")
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "02_roc_curve.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_pr_curve(model, X_test, y_test):
    """Precision-Recall curve"""
    y_prob = model.predict_proba(X_test)[:, 1]
    precision, recall, thresholds = precision_recall_curve(y_test, y_prob)

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(recall, precision, color="#7B1FA2", linewidth=2)
    ax.fill_between(recall, precision, alpha=0.1, color="#7B1FA2")
    ax.set_xlabel("召回率 (Recall)")
    ax.set_ylabel("精确率 (Precision)")
    ax.set_title("精确率-召回率曲线 (测试集)", fontsize=13)
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)

    # Mark the chosen threshold
    best_threshold = 0.46
    idx = np.argmin(np.abs(thresholds - best_threshold))
    ax.scatter([recall[idx]], [precision[idx]], color="red", s=100, zorder=5,
               label=f"选定阈值 = {best_threshold}\n(P={precision[idx]:.3f}, R={recall[idx]:.3f})")
    ax.legend(loc="lower left")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "03_pr_curve.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_threshold_optimization(model, X_val, y_val):
    """F1 score vs threshold"""
    y_prob = model.predict_proba(X_val)[:, 1]
    from sklearn.metrics import f1_score, precision_score, recall_score

    thresholds = np.arange(0.05, 0.95, 0.01)
    f1s, precisions, recalls = [], [], []
    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        f1s.append(f1_score(y_val, y_pred, zero_division=0))
        precisions.append(precision_score(y_val, y_pred, zero_division=0))
        recalls.append(recall_score(y_val, y_pred, zero_division=0))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(thresholds, f1s, color="#F44336", linewidth=2, label="F1")
    ax.plot(thresholds, precisions, color="#2196F3", linewidth=1.5, label="Precision")
    ax.plot(thresholds, recalls, color="#4CAF50", linewidth=1.5, label="Recall")

    best_idx = np.argmax(f1s)
    best_t = thresholds[best_idx]
    ax.axvline(x=best_t, color="gray", linestyle="--", alpha=0.7)
    ax.scatter([best_t], [f1s[best_idx]], color="red", s=100, zorder=5)
    ax.annotate(f"最优阈值 = {best_t:.2f}\nF1 = {f1s[best_idx]:.3f}",
                xy=(best_t, f1s[best_idx]),
                xytext=(best_t + 0.1, f1s[best_idx] - 0.05),
                fontsize=10, arrowprops=dict(arrowstyle="->", color="gray"))

    ax.set_xlabel("决策阈值")
    ax.set_ylabel("分数")
    ax.set_title("阈值优化曲线 (验证集)", fontsize=13)
    ax.legend(loc="lower left")
    ax.set_xlim(0, 1)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "04_threshold_optimization.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_feature_importance(model, X: pd.DataFrame):
    """Feature importance from the CatBoost model inside the pipeline"""
    # Extract the actual model from the pipeline
    catboost_model = model.named_steps.get("model") or model.best_estimator_.named_steps.get("model")
    if catboost_model is None:
        # Try to get from RandomizedSearchCV
        if hasattr(model, "best_estimator_"):
            catboost_model = model.best_estimator_.named_steps["model"]

    if not hasattr(catboost_model, "feature_importances_"):
        print("  模型不支持特征重要性，跳过")
        return

    # Get feature names after preprocessing
    preprocessor = model.named_steps.get("preprocessor") or model.best_estimator_.named_steps.get("preprocessor")
    if preprocessor and hasattr(preprocessor, "get_feature_names_out"):
        try:
            feature_names = preprocessor.get_feature_names_out()
        except Exception:
            feature_names = X.columns.tolist()
    else:
        feature_names = X.columns.tolist()

    importances = catboost_model.feature_importances_
    # Clean up feature names (remove prefix like "num__" or "cat__")
    clean_names = [n.replace("num__", "").replace("cat__", "") for n in feature_names]

    importance_df = pd.DataFrame({"feature": clean_names, "importance": importances})
    importance_df = importance_df.sort_values("importance", ascending=True).tail(15)

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(importance_df["feature"], importance_df["importance"], color="#5C6BC0")
    ax.set_xlabel("特征重要性")
    ax.set_title("CatBoost 特征重要性 Top 15", fontsize=13)
    for i, (name, val) in enumerate(zip(importance_df["feature"], importance_df["importance"])):
        ax.text(val + 0.1, i, f"{val:.2f}", va="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "05_feature_importance.png", dpi=150, bbox_inches="tight")
    plt.close()


def plot_model_comparison(metrics: dict):
    """CV F1 scores comparison across models"""
    cv = metrics.get("cv_results", {})
    if not cv:
        return

    models = list(cv.keys())
    scores = [cv[m]["best_cv_score_f1"] for m in models]
    model_labels = {"logistic_regression": "逻辑回归", "random_forest": "随机森林", "catboost": "CatBoost"}
    labels = [model_labels.get(m, m) for m in models]

    fig, ax = plt.subplots(figsize=(7, 5))
    colors = ["#FF9800", "#4CAF50", "#2196F3"]
    bars = ax.bar(labels, scores, color=colors[:len(models)])
    ax.set_ylabel("交叉验证 F1 分数")
    ax.set_title("模型对比 (5-fold CV F1)", fontsize=13)
    ax.set_ylim(0, 1)

    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width() / 2, score + 0.01,
                f"{score:.4f}", ha="center", fontsize=11, fontweight="bold")

    # Highlight the best model
    best_idx = np.argmax(scores)
    bars[best_idx].set_edgecolor("red")
    bars[best_idx].set_linewidth(2)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "06_model_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("加载数据...")
    df_raw = load_csv(DATASET_PATH)
    target_col = find_target_column(df_raw)
    df = load_and_clean_data(DATASET_PATH, target_col)

    X = df.drop(columns=[target_col])
    y = df[target_col]

    print("划分数据集 (70/15/15)...")
    X_train, X_val, X_test, y_train, y_val, y_test = split_train_val_test(
        X, y, test_size=0.15, val_size=0.15, random_state=RANDOM_STATE)

    print("加载模型...")
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    # If it's a RandomizedSearchCV, get the best estimator
    if hasattr(model, "best_estimator_"):
        best_model = model.best_estimator_
    else:
        best_model = model

    print("加载指标...")
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    threshold = metrics.get("best_threshold_info", {}).get("threshold", 0.5)

    print(f"使用阈值: {threshold}")
    print("生成评估可视化...")

    # 1. Confusion matrices
    y_test_pred = (best_model.predict_proba(X_test)[:, 1] >= threshold).astype(int)
    y_val_pred = (best_model.predict_proba(X_val)[:, 1] >= threshold).astype(int)
    plot_confusion_matrix(y_test, y_test_pred, "测试集混淆矩阵", "01_confusion_matrix_test.png")
    plot_confusion_matrix(y_val, y_val_pred, "验证集混淆矩阵", "01b_confusion_matrix_val.png")

    # 2. ROC curve
    plot_roc_curves(best_model, X_test, y_test, X_val, y_val)

    # 3. PR curve
    plot_pr_curve(best_model, X_test, y_test)

    # 4. Threshold optimization
    plot_threshold_optimization(best_model, X_val, y_val)

    # 5. Feature importance
    plot_feature_importance(best_model, X_train)

    # 6. Model comparison
    plot_model_comparison(metrics)

    # Print summary
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
    print("\n=== 测试集指标 ===")
    print(f"  Accuracy:  {accuracy_score(y_test, y_test_pred):.4f}")
    print(f"  Precision: {precision_score(y_test, y_test_pred):.4f}")
    print(f"  Recall:    {recall_score(y_test, y_test_pred):.4f}")
    print(f"  F1:        {f1_score(y_test, y_test_pred):.4f}")
    print(f"  ROC AUC:   {roc_auc_score(y_test, best_model.predict_proba(X_test)[:, 1]):.4f}")

    print(f"\n完成! 输出目录: {OUTPUT_DIR}")
    print(f"可视化: {len(list(OUTPUT_DIR.glob('*.png')))} 张图")


if __name__ == "__main__":
    main()
