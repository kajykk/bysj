"""Fast model training + evaluation visualizations for thesis.

Trains a CatBoost model (no hyperparameter search) and generates:
- Confusion matrix
- ROC curve
- Precision-Recall curve
- Feature importance
- Threshold optimization

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
from catboost import CatBoostClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                              f1_score, precision_score, precision_recall_curve,
                              recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sns.set_style("whitegrid")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

DATASET_PATH = Path("datasets/Student Depression Dataset.csv")
OUTPUT_DIR = Path("reports/eda/student_depression/eval")
MODEL_DIR = Path("models/artifacts/depression_tabular")
RANDOM_STATE = 42

YES_NO_MAP = {"yes": 1, "no": 0, "Yes": 1, "No": 0, "YES": 1, "NO": 0}


def load_and_clean():
    df = pd.read_csv(DATASET_PATH)
    df.columns = [c.strip() for c in df.columns]

    # Drop id
    df = df.drop(columns=["id"], errors="ignore")

    # Map Yes/No columns
    for col in ["Have you ever had suicidal thoughts ?", "Family History of Mental Illness"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().map(YES_NO_MAP)

    # Sleep Duration ordinal
    sleep_map = {"less than 5 hours": 0, "5-6 hours": 1, "7-8 hours": 2, "more than 8 hours": 3}
    df["SleepDurationOrdinal"] = df["Sleep Duration"].astype(str).str.lower().str.strip().map(sleep_map)

    # Dietary Habits ordinal
    diet_map = {"unhealthy": 0, "moderate": 1, "healthy": 2}
    df["DietaryHabitsOrdinal"] = df["Dietary Habits"].astype(str).str.lower().str.strip().map(diet_map)

    # Numeric conversion
    for col in ["Age", "Academic Pressure", "Work Pressure", "CGPA",
                "Study Satisfaction", "Job Satisfaction", "Work/Study Hours", "Financial Stress"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Gender binary
    df["Gender"] = df["Gender"].str.strip().map({"Male": 0, "Female": 1})

    # Drop high-cardinality categoricals that aren't useful
    df = df.drop(columns=["City", "Profession", "Degree", "Sleep Duration", "Dietary Habits"], errors="ignore")

    # Drop rows with missing target
    df = df.dropna(subset=["Depression"])
    df["Depression"] = df["Depression"].astype(int)

    return df


def build_preprocessor(X):
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

    return ColumnTransformer([
        ("num", numeric_transformer, numeric_features),
        ("cat", categorical_transformer, categorical_features) if categorical_features else ("cat", "passthrough", []),
    ])


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("加载数据...")
    df = load_and_clean()
    print(f"数据: {df.shape[0]} 行 × {df.shape[1]} 列")
    print(f"数值列: {df.select_dtypes(include=['number']).columns.tolist()}")
    print(f"分类列: {[c for c in df.columns if c not in df.select_dtypes(include=['number']).columns]}")

    X = df.drop(columns=["Depression"])
    y = df["Depression"]

    # Split 70/15/15
    X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.3, random_state=RANDOM_STATE, stratify=y)
    X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, random_state=RANDOM_STATE, stratify=y_temp)
    print(f"训练集: {len(X_train)}, 验证集: {len(X_val)}, 测试集: {len(X_test)}")

    print("构建预处理管道...")
    preprocessor = build_preprocessor(X_train)

    print("训练 CatBoost 模型...")
    model = Pipeline([
        ("preprocessor", preprocessor),
        ("model", CatBoostClassifier(
            iterations=800, depth=6, learning_rate=0.05,
            loss_function="Logloss", eval_metric="AUC",
            random_seed=RANDOM_STATE, verbose=0,
            class_weights={0: 1, 1: 1},
        )),
    ])
    model.fit(X_train, y_train)

    # Save model
    with open(MODEL_DIR / "best_model.pkl", "wb") as f:
        pickle.dump(model, f)
    print(f"模型已保存: {MODEL_DIR / 'best_model.pkl'}")

    # Predictions
    y_test_prob = model.predict_proba(X_test)[:, 1]
    y_val_prob = model.predict_proba(X_val)[:, 1]

    # Find best threshold on val
    thresholds = np.arange(0.05, 0.95, 0.01)
    best_f1, best_t = 0, 0.5
    for t in thresholds:
        f1 = f1_score(y_val, (y_val_prob >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    print(f"最优阈值: {best_t:.2f} (F1={best_f1:.4f})")

    y_test_pred = (y_test_prob >= best_t).astype(int)
    y_val_pred = (y_val_prob >= best_t).astype(int)

    # Metrics
    test_acc = accuracy_score(y_test, y_test_pred)
    test_f1 = f1_score(y_test, y_test_pred)
    test_prec = precision_score(y_test, y_test_pred)
    test_rec = recall_score(y_test, y_test_pred)
    test_auc = roc_auc_score(y_test, y_test_prob)

    print(f"\n=== 测试集指标 ===")
    print(f"  Accuracy:  {test_acc:.4f}")
    print(f"  Precision: {test_prec:.4f}")
    print(f"  Recall:    {test_rec:.4f}")
    print(f"  F1:        {test_f1:.4f}")
    print(f"  ROC AUC:   {test_auc:.4f}")

    # Save metrics
    metrics = {
        "best_model": "catboost",
        "best_threshold": float(best_t),
        "test_metrics": {
            "accuracy": float(test_acc), "precision": float(test_prec),
            "recall": float(test_rec), "f1": float(test_f1), "roc_auc": float(test_auc),
        },
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # ===== Visualizations =====
    print("\n生成评估可视化...")

    # 1. Confusion matrix
    for y_true, y_pred, title, fname in [
        (y_test, y_test_pred, "测试集混淆矩阵", "01_confusion_matrix.png"),
        (y_val, y_val_pred, "验证集混淆矩阵", "01b_confusion_matrix_val.png"),
    ]:
        cm = confusion_matrix(y_true, y_pred)
        fig, ax = plt.subplots(figsize=(6, 5))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax,
                    xticklabels=["无抑郁 (0)", "抑郁 (1)"],
                    yticklabels=["无抑郁 (0)", "抑郁 (1)"])
        ax.set_xlabel("预测值"); ax.set_ylabel("真实值")
        ax.set_title(title, fontsize=13)
        for i in range(2):
            for j in range(2):
                ax.text(j + 0.5, i + 0.65, f"{cm[i][j]/cm.sum()*100:.1f}%",
                        ha="center", va="center", fontsize=10, color="gray")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / fname, dpi=150, bbox_inches="tight")
        plt.close()

    # 2. ROC curve
    fig, ax = plt.subplots(figsize=(7, 6))
    for X, y, label, color in [(X_val, y_val, "验证集", "#2196F3"),
                                (X_test, y_test, "测试集", "#F44336")]:
        prob = model.predict_proba(X)[:, 1]
        fpr, tpr, _ = roc_curve(y, prob)
        auc = roc_auc_score(y, prob)
        ax.plot(fpr, tpr, label=f"{label} (AUC = {auc:.3f})", color=color, linewidth=2)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="随机分类器")
    ax.set_xlabel("假阳性率 (FPR)"); ax.set_ylabel("真阳性率 (TPR)")
    ax.set_title("ROC 曲线", fontsize=13); ax.legend(loc="lower right")
    ax.set_xlim(-0.01, 1.01); ax.set_ylim(-0.01, 1.01)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "02_roc_curve.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 3. PR curve
    precision, recall, pr_thresholds = precision_recall_curve(y_test, y_test_prob)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(recall, precision, color="#7B1FA2", linewidth=2)
    ax.fill_between(recall, precision, alpha=0.1, color="#7B1FA2")
    ax.set_xlabel("召回率 (Recall)"); ax.set_ylabel("精确率 (Precision)")
    ax.set_title("精确率-召回率曲线 (测试集)", fontsize=13)
    idx = np.argmin(np.abs(pr_thresholds - best_t))
    ax.scatter([recall[idx]], [precision[idx]], color="red", s=100, zorder=5,
               label=f"选定阈值 = {best_t:.2f}\n(P={precision[idx]:.3f}, R={recall[idx]:.3f})")
    ax.legend(loc="lower left")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "03_pr_curve.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 4. Threshold optimization
    fig, ax = plt.subplots(figsize=(8, 5))
    f1s, precs, recs = [], [], []
    for t in thresholds:
        yp = (y_val_prob >= t).astype(int)
        f1s.append(f1_score(y_val, yp, zero_division=0))
        precs.append(precision_score(y_val, yp, zero_division=0))
        recs.append(recall_score(y_val, yp, zero_division=0))
    ax.plot(thresholds, f1s, color="#F44336", linewidth=2, label="F1")
    ax.plot(thresholds, precs, color="#2196F3", linewidth=1.5, label="Precision")
    ax.plot(thresholds, recs, color="#4CAF50", linewidth=1.5, label="Recall")
    ax.axvline(x=best_t, color="gray", linestyle="--", alpha=0.7)
    ax.scatter([best_t], [best_f1], color="red", s=100, zorder=5)
    ax.annotate(f"最优阈值 = {best_t:.2f}\nF1 = {best_f1:.3f}",
                xy=(best_t, best_f1), xytext=(best_t + 0.1, best_f1 - 0.05),
                fontsize=10, arrowprops=dict(arrowstyle="->", color="gray"))
    ax.set_xlabel("决策阈值"); ax.set_ylabel("分数")
    ax.set_title("阈值优化曲线 (验证集)", fontsize=13); ax.legend(loc="lower left")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "04_threshold_optimization.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 5. Feature importance
    catboost_model = model.named_steps["model"]
    preprocessor = model.named_steps["preprocessor"]
    try:
        feature_names = preprocessor.get_feature_names_out()
        clean_names = [n.replace("num__", "").replace("cat__", "") for n in feature_names]
    except Exception:
        clean_names = X.columns.tolist()

    if hasattr(catboost_model, "feature_importances_"):
        imp_df = pd.DataFrame({"feature": clean_names, "importance": catboost_model.feature_importances_})
        imp_df = imp_df.sort_values("importance", ascending=True).tail(15)
        fig, ax = plt.subplots(figsize=(9, 7))
        ax.barh(imp_df["feature"], imp_df["importance"], color="#5C6BC0")
        ax.set_xlabel("特征重要性"); ax.set_title("CatBoost 特征重要性 Top 15", fontsize=13)
        for i, (name, val) in enumerate(zip(imp_df["feature"], imp_df["importance"])):
            ax.text(val + 0.1, i, f"{val:.2f}", va="center", fontsize=9)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "05_feature_importance.png", dpi=150, bbox_inches="tight")
        plt.close()

    print(f"\n完成! 输出目录: {OUTPUT_DIR}")
    print(f"可视化: {len(list(OUTPUT_DIR.glob('*.png')))} 张图")


if __name__ == "__main__":
    main()
