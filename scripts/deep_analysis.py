"""深度模型分析 — 用于论文实验章节。

生成内容：
  1. SHAP 分析：summary(beeswarm)、bar、dependence(top3)、waterfall(正/负样本)
  2. 学习曲线：训练样本量 vs 训练/验证 F1 & AUC（5 折 CV）
  3. 5 折交叉验证详细结果：每折 P/R/F1/AUC 箱线图
  4. 阈值敏感性 + 业务代价分析（FN 代价 = 5×FP）
  5. 误差分析：TP/TN/FP/FN 四组在关键特征上的分布对比

输出目录: reports/eda/student_depression/deep/
"""
from __future__ import annotations

import json
import warnings
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
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                              recall_score, roc_auc_score)
from sklearn.model_selection import (StratifiedKFold, cross_validate,
                                      learning_curve, train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sns.set_style("whitegrid")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

DATASET_PATH = Path("datasets/Student Depression Dataset.csv")
OUTPUT_DIR = Path("reports/eda/student_depression/deep")
RANDOM_STATE = 42
YES_NO_MAP = {"yes": 1, "no": 0, "Yes": 1, "No": 0, "YES": 1, "NO": 0}

# 业务代价假设（用于代价曲线）：漏诊抑郁(FN)的代价 ≈ 5× 误报(FP)
FN_COST_MULTIPLIER = 5.0


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


def make_model() -> Pipeline:
    # 注意：不设置 class_weights — CatBoost 会把 dict 形式内部转为 list，
    # 导致 sklearn 的 clone() 报 "Cannot clone" 错误，使 cross_validate / learning_curve 失败。
    # {0:1,1:1} 本就是默认均衡权重，移除后行为等价且 clone 友好。
    return Pipeline([
        ("preprocessor", build_preprocessor(X_train)),
        ("model", CatBoostClassifier(
            iterations=800, depth=6, learning_rate=0.05,
            loss_function="Logloss", eval_metric="AUC",
            random_seed=RANDOM_STATE, verbose=0,
        )),
    ])


def clean_feature_names(names):
    out = []
    for n in names:
        n = n.replace("num__", "").replace("cat__", "")
        out.append(n)
    return out


# ============================================================
# 1. SHAP 分析
# ============================================================
def run_shap(model: Pipeline, X_test: pd.DataFrame, y_test: pd.Series, feature_names_clean):
    print("  [SHAP] 计算解释器与 SHAP 值...")
    catboost_model = model.named_steps["model"]
    preprocessor = model.named_steps["preprocessor"]

    try:
        X_test_transformed = preprocessor.transform(X_test)
    except Exception as e:
        print(f"  [SHAP] 预处理失败: {e}")
        return

    if hasattr(X_test_transformed, "toarray"):
        X_test_transformed = X_test_transformed.toarray()

    try:
        explainer = shap.TreeExplainer(catboost_model)
        # 采样以加速 beeswarm
        sample_n = min(2000, X_test_transformed.shape[0])
        rng = np.random.RandomState(RANDOM_STATE)
        idx = rng.choice(X_test_transformed.shape[0], sample_n, replace=False)
        X_sample = X_test_transformed[idx]
        shap_values = explainer.shap_values(X_sample)
        expected_value = explainer.expected_value
    except Exception as e:
        print(f"  [SHAP] 解释器失败: {e}")
        return

    # 1a. SHAP summary (beeswarm)
    try:
        plt.figure(figsize=(9, 7))
        shap.summary_plot(shap_values, X_sample,
                          feature_names=feature_names_clean,
                          show=False, max_display=12)
        plt.title("SHAP Summary — 特征对抑郁预测的影响", fontsize=12)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "01_shap_summary.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  [SHAP] 01_shap_summary.png")
    except Exception as e:
        print(f"  [SHAP] summary 失败: {e}")

    # 1b. SHAP bar (全局重要性)
    try:
        plt.figure(figsize=(8, 6))
        shap.summary_plot(shap_values, X_sample,
                          feature_names=feature_names_clean,
                          plot_type="bar", show=False, max_display=12)
        plt.title("SHAP 全局特征重要性 (mean |SHAP value|)", fontsize=12)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "02_shap_bar.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  [SHAP] 02_shap_bar.png")
    except Exception as e:
        print(f"  [SHAP] bar 失败: {e}")

    # 1c. Dependence plot for top-3 features
    try:
        mean_abs = np.abs(shap_values).mean(axis=0)
        top_idx = np.argsort(mean_abs)[::-1][:3]
        for rank, fi in enumerate(top_idx, 1):
            fname = feature_names_clean[fi]
            plt.figure(figsize=(7, 5))
            shap.dependence_plot(fi, shap_values, X_sample,
                                 feature_names=feature_names_clean,
                                 show=False)
            plt.title(f"SHAP Dependence — Top{rank}: {fname}", fontsize=12)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"03_shap_dependence_{rank}_{fname[:20]}.png",
                        dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  [SHAP] 03_shap_dependence_{rank}_{fname[:20]}.png")
    except Exception as e:
        print(f"  [SHAP] dependence 失败: {e}")

    # 1d. Waterfall — 一个高风险正样本 + 一个低风险负样本
    try:
        proba = catboost_model.predict_proba(X_test_transformed)[:, 1]
        pos_global = np.where(y_test.values == 1)[0]
        neg_global = np.where(y_test.values == 0)[0]
        # 在采样索引之外取原始索引对应位置（这里直接用全量 transform 后的）
        full_shap = explainer.shap_values(X_test_transformed[:500])  # 限制数量加速
        # 选择正样本中预测概率最高的
        proba_head = proba[:500]
        pos_local = np.where(y_test.values[:500] == 1)[0]
        neg_local = np.where(y_test.values[:500] == 0)[0]
        if len(pos_local) > 0:
            pick_pos = pos_local[np.argmax(proba_head[pos_local])]
            expl = shap.Explanation(
                values=full_shap[pick_pos],
                base_values=np.array([expected_value] if np.isscalar(expected_value) else expected_value)[0]
                            if not isinstance(expected_value, (list, tuple, np.ndarray)) else np.array(expected_value).ravel()[0],
                data=X_test_transformed[pick_pos],
                feature_names=feature_names_clean,
            )
            plt.figure(figsize=(9, 6))
            shap.plots.waterfall(expl, max_display=12, show=False)
            plt.title(f"SHAP Waterfall — 高风险正样本 (P={proba_head[pick_pos]:.3f})", fontsize=12)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / "04_shap_waterfall_positive.png", dpi=150, bbox_inches="tight")
            plt.close()
            print("  [SHAP] 04_shap_waterfall_positive.png")
        if len(neg_local) > 0:
            pick_neg = neg_local[np.argmin(proba_head[neg_local])]
            expl = shap.Explanation(
                values=full_shap[pick_neg],
                base_values=np.array([expected_value] if np.isscalar(expected_value) else expected_value)[0]
                            if not isinstance(expected_value, (list, tuple, np.ndarray)) else np.array(expected_value).ravel()[0],
                data=X_test_transformed[pick_neg],
                feature_names=feature_names_clean,
            )
            plt.figure(figsize=(9, 6))
            shap.plots.waterfall(expl, max_display=12, show=False)
            plt.title(f"SHAP Waterfall — 低风险负样本 (P={proba_head[pick_neg]:.3f})", fontsize=12)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / "05_shap_waterfall_negative.png", dpi=150, bbox_inches="tight")
            plt.close()
            print("  [SHAP] 05_shap_waterfall_negative.png")
    except Exception as e:
        print(f"  [SHAP] waterfall 失败: {e}")


# ============================================================
# 2. 学习曲线
# ============================================================
def run_learning_curve(X, y):
    print("  [LC] 计算学习曲线（5 折 CV）...")
    model = make_model()
    train_sizes = np.linspace(0.1, 1.0, 8)

    try:
        sizes, train_scores, val_scores = learning_curve(
            model, X, y,
            train_sizes=train_sizes, cv=5,
            scoring="f1", n_jobs=-1, random_state=RANDOM_STATE,
            shuffle=True,
        )
    except Exception as e:
        print(f"  [LC] 失败: {e}")
        return

    train_mean, train_std = train_scores.mean(axis=1), train_scores.std(axis=1)
    val_mean, val_std = val_scores.mean(axis=1), val_scores.std(axis=1)

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(sizes, train_mean, "o-", color="#2196F3", linewidth=2, label="训练集 F1")
    ax.fill_between(sizes, train_mean - train_std, train_mean + train_std, alpha=0.15, color="#2196F3")
    ax.plot(sizes, val_mean, "s-", color="#F44336", linewidth=2, label="交叉验证 F1")
    ax.fill_between(sizes, val_mean - val_std, val_mean + val_std, alpha=0.15, color="#F44336")
    ax.set_xlabel("训练样本数")
    ax.set_ylabel("F1 分数")
    ax.set_title("学习曲线 — CatBoost (5 折 CV, F1)", fontsize=13)
    ax.legend(loc="lower right")
    ax.set_ylim(0.5, 1.02)
    ax.grid(alpha=0.3)

    # 标注末值
    ax.annotate(f"训练 F1 = {train_mean[-1]:.3f}±{train_std[-1]:.3f}",
                xy=(sizes[-1], train_mean[-1]),
                xytext=(sizes[-1] - sizes[-1] * 0.4, train_mean[-1] - 0.05),
                fontsize=9, color="#2196F3",
                arrowprops=dict(arrowstyle="->", color="#2196F3"))
    ax.annotate(f"CV F1 = {val_mean[-1]:.3f}±{val_std[-1]:.3f}",
                xy=(sizes[-1], val_mean[-1]),
                xytext=(sizes[-1] - sizes[-1] * 0.4, val_mean[-1] - 0.08),
                fontsize=9, color="#F44336",
                arrowprops=dict(arrowstyle="->", color="#F44336"))

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "06_learning_curve.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [LC] 06_learning_curve.png")

    # 诊断结论
    gap = train_mean[-1] - val_mean[-1]
    lc_summary = {
        "final_train_f1": float(train_mean[-1]),
        "final_cv_f1": float(val_mean[-1]),
        "generalization_gap": float(gap),
        "diagnosis": "过拟合" if gap > 0.1 else ("欠拟合" if val_mean[-1] < 0.7 else "良好拟合"),
    }
    return lc_summary


# ============================================================
# 3. 5 折交叉验证详细结果
# ============================================================
def run_cv_detailed(X, y):
    print("  [CV] 5 折交叉验证详细结果...")
    model = make_model()
    scoring = ["accuracy", "precision", "recall", "f1", "roc_auc"]

    try:
        cv_results = cross_validate(
            model, X, y,
            cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE),
            scoring=scoring, n_jobs=-1, return_train_score=False,
        )
    except Exception as e:
        print(f"  [CV] 失败: {e}")
        return None

    metrics_map = {
        "accuracy": "test_accuracy",
        "precision": "test_precision",
        "recall": "test_recall",
        "f1": "test_f1",
        "roc_auc": "test_roc_auc",
    }

    # 箱线图
    fig, ax = plt.subplots(figsize=(9, 6))
    data, labels = [], []
    for name, key in metrics_map.items():
        scores = cv_results[key]
        data.append(scores)
        labels.append(f"{name}\n{scores.mean():.3f}±{scores.std():.3f}")
    bp = ax.boxplot(data, labels=labels, patch_artist=True, widths=0.55,
                    showmeans=True, meanprops=dict(marker="D", markerfacecolor="red", markersize=7))
    colors = ["#90CAF9", "#A5D6A7", "#FFCC80", "#EF9A9A", "#CE93D8"]
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
    ax.set_ylabel("分数")
    ax.set_title("5 折交叉验证 — 各指标分布 (n=5)", fontsize=13)
    ax.set_ylim(0.5, 1.02)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "07_cv_boxplot.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [CV] 07_cv_boxplot.png")

    cv_summary = {}
    for name, key in metrics_map.items():
        s = cv_results[key]
        cv_summary[name] = {
            "mean": float(s.mean()),
            "std": float(s.std()),
            "folds": [float(v) for v in s],
        }
    return cv_summary


# ============================================================
# 4. 阈值敏感性 + 业务代价分析
# ============================================================
def run_threshold_cost(model, X_val, y_val, X_test, y_test, best_t):
    print("  [TC] 阈值敏感性与业务代价分析...")
    y_test_prob = model.predict_proba(X_test)[:, 1]
    y_val_prob = model.predict_proba(X_val)[:, 1]

    thresholds = np.arange(0.05, 0.95, 0.01)
    f1s, precs, recs, costs = [], [], [], []
    for t in thresholds:
        yp = (y_test_prob >= t).astype(int)
        f1s.append(f1_score(y_test, yp, zero_division=0))
        precs.append(precision_score(y_test, yp, zero_division=0))
        recs.append(recall_score(y_test, yp, zero_division=0))
        # 代价 = FN * 5 + FP * 1
        tn_fp_fn_tp = np.bincount(y_test * 2 + yp, minlength=4)
        tn, fp, fn, tp = tn_fp_fn_tp[0], tn_fp_fn_tp[1], tn_fp_fn_tp[2], tn_fp_fn_tp[3]
        costs.append(fn * FN_COST_MULTIPLIER + fp * 1.0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # 左：P/R/F1
    ax1.plot(thresholds, f1s, color="#F44336", linewidth=2, label="F1")
    ax1.plot(thresholds, precs, color="#2196F3", linewidth=1.5, label="Precision")
    ax1.plot(thresholds, recs, color="#4CAF50", linewidth=1.5, label="Recall")
    ax1.axvline(x=best_t, color="gray", linestyle="--", alpha=0.7)
    ax1.scatter([best_t], [max(f1s)], color="red", s=80, zorder=5)
    ax1.annotate(f"选定阈值={best_t:.2f}", xy=(best_t, max(f1s)),
                 xytext=(best_t + 0.05, max(f1s) - 0.08), fontsize=9,
                 arrowprops=dict(arrowstyle="->", color="gray"))
    ax1.set_xlabel("决策阈值")
    ax1.set_ylabel("分数")
    ax1.set_title("阈值敏感性 — P/R/F1 (测试集)", fontsize=12)
    ax1.legend(loc="lower left")
    ax1.set_xlim(0, 1)

    # 右：业务代价
    ax2.plot(thresholds, costs, color="#FF9800", linewidth=2)
    ax2.fill_between(thresholds, costs, alpha=0.15, color="#FF9800")
    min_cost_idx = int(np.argmin(costs))
    min_cost_t = thresholds[min_cost_idx]
    ax2.axvline(x=best_t, color="gray", linestyle="--", alpha=0.7, label=f"F1 最优阈值={best_t:.2f}")
    ax2.axvline(x=min_cost_t, color="#E91E63", linestyle=":", alpha=0.8, label=f"代价最优阈值={min_cost_t:.2f}")
    ax2.scatter([min_cost_t], [costs[min_cost_idx]], color="#E91E63", s=100, zorder=5)
    ax2.annotate(f"最小代价={costs[min_cost_idx]:.0f}\n(FN×5 + FP×1)",
                 xy=(min_cost_t, costs[min_cost_idx]),
                 xytext=(min_cost_t + 0.08, costs[min_cost_idx] + max(costs) * 0.15),
                 fontsize=9, arrowprops=dict(arrowstyle="->", color="#E91E63"))
    ax2.set_xlabel("决策阈值")
    ax2.set_ylabel("总代价 (FN×5 + FP×1)")
    ax2.set_title(f"业务代价曲线 (FN 代价 = {int(FN_COST_MULTIPLIER)}×FP)", fontsize=12)
    ax2.legend(loc="upper right")
    ax2.set_xlim(0, 1)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "08_threshold_cost.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [TC] 08_threshold_cost.png")

    return {
        "f1_optimal_threshold": float(best_t),
        "cost_optimal_threshold": float(min_cost_t),
        "min_cost": float(costs[min_cost_idx]),
        "cost_at_f1_threshold": float(costs[np.argmin(np.abs(thresholds - best_t))]),
        "fn_cost_multiplier": FN_COST_MULTIPLIER,
    }


# ============================================================
# 5. 误差分析
# ============================================================
def run_error_analysis(model, X_test, y_test, best_t):
    print("  [EA] 误差分析（TP/TN/FP/FN 分组对比）...")
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= best_t).astype(int)
    y_true = y_test.values

    group = np.where((y_true == 1) & (y_pred == 1), "TP",
            np.where((y_true == 0) & (y_pred == 0), "TN",
            np.where((y_true == 0) & (y_pred == 1), "FP", "FN")))

    counts = pd.Series(group).value_counts().to_dict()
    print(f"  [EA] 分组: {counts}")

    # 关键特征对比
    key_features = [
        "Have you ever had suicidal thoughts ?",
        "Academic Pressure",
        "Financial Stress",
        "Age",
        "Work/Study Hours",
        "CGPA",
        "SleepDurationOrdinal",
        "DietaryHabitsOrdinal",
    ]
    key_features = [f for f in key_features if f in X_test.columns]

    df_eval = X_test.copy()
    df_eval["_group"] = group
    df_eval["_prob"] = y_prob

    n = len(key_features)
    ncol = 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(6 * ncol, 4.5 * nrow))
    axes = np.array(axes).ravel()
    order = ["TN", "FN", "FP", "TP"]
    palette = {"TN": "#4CAF50", "FN": "#F44336", "FP": "#FF9800", "TP": "#2196F3"}

    for i, feat in enumerate(key_features):
        ax = axes[i]
        sns.boxplot(data=df_eval, x="_group", y=feat, order=order,
                    palette=palette, ax=ax, showfliers=False)
        ax.set_title(feat, fontsize=11)
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.grid(axis="y", alpha=0.3)

    # 隐藏多余子图
    for j in range(n, len(axes)):
        axes[j].axis("off")

    fig.suptitle(f"误差分析 — 四组样本特征分布 (阈值={best_t:.2f})\n"
                 f"TN={counts.get('TN',0)}  FP={counts.get('FP',0)}  FN={counts.get('FN',0)}  TP={counts.get('TP',0)}",
                 fontsize=13, y=1.00)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "09_error_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [EA] 09_error_analysis.png")

    # FN 的预测概率分布（高置信度的漏诊最危险）
    fn_df = df_eval[df_eval["_group"] == "FN"]
    if len(fn_df) > 0:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(fn_df["_prob"], bins=30, color="#F44336", alpha=0.7, edgecolor="white")
        ax.axvline(x=best_t, color="gray", linestyle="--", label=f"阈值={best_t:.2f}")
        ax.set_xlabel("预测为正类的概率")
        ax.set_ylabel("漏诊样本数")
        ax.set_title(f"FN（漏诊）样本的预测概率分布 (n={len(fn_df)})", fontsize=12)
        ax.legend()
        # 高风险漏诊：概率接近阈值
        high_risk_fn = (fn_df["_prob"] > best_t - 0.1).sum()
        ax.text(0.95, 0.95, f"接近阈值的漏诊: {high_risk_fn} 例",
                transform=ax.transAxes, ha="right", va="top",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "10_fn_probability.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  [EA] 10_fn_probability.png")

    return {
        "counts": counts,
        "fn_high_risk_count": int((fn_df["_prob"] > best_t - 0.1).sum()) if len(fn_df) > 0 else 0,
        "fn_mean_prob": float(fn_df["_prob"].mean()) if len(fn_df) > 0 else None,
    }


# ============================================================
# 主流程
# ============================================================
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    global X_train

    print("=" * 60)
    print("加载数据...")
    df = load_and_clean()
    print(f"数据: {df.shape[0]} 行 × {df.shape[1]} 列")

    X = df.drop(columns=["Depression"])
    y = df["Depression"]

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.3, random_state=RANDOM_STATE, stratify=y)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=RANDOM_STATE, stratify=y_temp)
    print(f"训练集: {len(X_train)}, 验证集: {len(X_val)}, 测试集: {len(X_test)}")

    print("\n训练 CatBoost 模型...")
    model = make_model()
    model.fit(X_train, y_train)

    # 特征名
    try:
        feature_names = model.named_steps["preprocessor"].get_feature_names_out()
        feature_names_clean = clean_feature_names(feature_names)
    except Exception:
        feature_names_clean = X.columns.tolist()

    # 最优阈值（复用 train_and_eval 的逻辑）
    y_val_prob = model.predict_proba(X_val)[:, 1]
    thresholds = np.arange(0.05, 0.95, 0.01)
    best_f1, best_t = 0, 0.5
    for t in thresholds:
        f1 = f1_score(y_val, (y_val_prob >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    print(f"最优阈值: {best_t:.2f} (验证集 F1={best_f1:.4f})")

    summary = {"best_threshold": float(best_t)}

    # 导入 shap（延迟导入，避免初始化开销）
    global shap
    try:
        import shap
        shap_ok = True
    except Exception as e:
        print(f"[WARN] shap 导入失败: {e}")
        shap_ok = False

    print("\n[1/5] SHAP 分析...")
    if shap_ok:
        run_shap(model, X_test, y_test, feature_names_clean)
    else:
        print("  跳过（shap 不可用）")

    print("\n[2/5] 学习曲线...")
    lc = run_learning_curve(X, y)
    if lc:
        summary["learning_curve"] = lc

    print("\n[3/5] 5 折交叉验证...")
    cv = run_cv_detailed(X, y)
    if cv:
        summary["cv_5fold"] = cv

    print("\n[4/5] 阈值敏感性与代价分析...")
    tc = run_threshold_cost(model, X_val, y_val, X_test, y_test, best_t)
    summary["threshold_cost"] = tc

    print("\n[5/5] 误差分析...")
    ea = run_error_analysis(model, X_test, y_test, best_t)
    summary["error_analysis"] = ea

    # 写入汇总 JSON
    (OUTPUT_DIR / "deep_analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总: {OUTPUT_DIR / 'deep_analysis_summary.json'}")

    n_png = len(list(OUTPUT_DIR.glob("*.png")))
    print(f"\n完成! 共生成 {n_png} 张图，输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
