"""M4 融合管线统一库 (R-F1).

将 m4_fusion 六件套 (retrain v1-v4 / stacking / save_artifacts) 的共享核心收敛:
- 数据与模态加载对齐 (lite_features.csv + BERT 缓存嵌入)
- 共享组件: delong_test / train_logreg / model_predict_proba / generate_oof
- 策略评估骨架 (5-fold × 3 seeds 嵌套 CV, 变体以 VariantConfig 参数化)
- ``--variant`` CLI 区分变体; 数值路径与原脚本逐一等价 (bit-exact 红线)

等价性约定:
- 所有随机性显式种子化; delong_test 内部 RandomState(42) 每次独立实例
- 浮点运算顺序与原脚本逐语句一致 (禁止合并/重排表达式)
- 验证方式: 同一数据下 lib 输出与原脚本实验 JSON 深度比对,
  忽略 experiment_id/timestamp/total_time_s/eval_time_s 四个非确定字段

Usage:
    python scripts/lib/fusion_pipeline.py --variant v1 --out /tmp/v1_check.json

进度:
    [x] v1 已移植 —— bit-exact 验证通过 (2026-08-27):
        基线 models/experiments/m4_fusion_retrain_20260827_182231.json,
        lib 输出忽略 {experiment_id, timestamp, total_time_s, eval_time_s, task}
        后深度相等, 含 60 条 fold_details 与全精度浮点。
        基线真实指标: structured AUC=0.9189 / stacking AUC=0.9189±0.0227 /
        DeLong p=0.3240 (v1 自述融合目标未达成, 与原脚本一致)。
    [ ] v2 (10 维结构化 + xgb 元学习器) —— 程序: 跑原脚本留基线 → 按 VariantConfig
        扩展 (struct_cols/C 值/xgb 策略闭包移植) → 同法 bit-exact 比对
    [x] v3 已移植 —— bit-exact 验证通过 (2026-08-27):
        基线 models/experiments/_baseline_v3.json (原脚本运行生成),
        lib 输出 _rf1_check/v3_via_lib.json 忽略
        {experiment_id, timestamp, total_time_s, eval_time_s, task} 后深度相等,
        含 7 策略 × 15 折 fold_details 与全精度浮点。
        基线真实指标: structured_only AUC=0.9187 / trimodal_optimized
        AUC=0.9241±0.0110 / DeLong p=0.0086 (lift +0.0054 未达 0.03, 与原脚本一致)。
    [x] v4 已移植 —— bit-exact 验证通过 (2026-08-27):
        基线 models/experiments/_baseline_v4.json (原脚本运行生成),
        lib 输出 _rf1_check/v4_via_lib.json 忽略
        {experiment_id, timestamp, total_time_s, eval_time_s, task} 后深度相等,
        含 6 策略 × 15 折 fold_details 与全精度浮点。
        基线真实指标: structured_only AUC=0.9187 / hybrid_base_lgbm_meta
        AUC=0.9204±0.0106 / DeLong p=0.3504 (lift +0.0017 未达 0.03,
        归档为数据天花板结论, 与原脚本一致)。
    [x] stacking 已移植 —— bit-exact 验证通过 (2026-08-27):
        基线 models/experiments/_baseline_stacking.json (原脚本运行生成),
        lib 输出 _rf1_check/stacking_via_lib.json 忽略同上五键后深度相等。
        基线真实指标: structured_only AUC=0.9189 / 最佳 CV 融合 stacking
        AUC=0.9238±0.0189 (CV lift +0.0049 未达 0.02); DeLong OOF 最佳策略
        stacking_gbdt lift=+0.0272 p=1.14e-06 ✓ (all_passed=True, 与原脚本一致)。
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("M4-Fusion")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "lite_features.csv"
BERT_CACHE_PATH = (
    PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "bert_embeddings_n1275.npy"
)
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"

# 阶段二目标 (全变体共用)
TARGET_AUC_LIFT = 0.03
DELONG_P_THRESHOLD = 0.05

# CV 配置 (全变体共用)
N_FOLDS = 5
SEEDS = [42, 1337, 2024]
T_VALUE_95 = 2.145  # df=14

TARGET_COL = "phq9_binary"


# ---------------------------------------------------------------------------
# 共享核心 (忠实移植自 m4_fusion_retrain.py v1, 语句顺序保持不变)
# ---------------------------------------------------------------------------


def delong_test(
    y_true: np.ndarray, y_prob_a: np.ndarray, y_prob_b: np.ndarray
) -> tuple[float, float]:
    """DeLong 检验 (bootstrap 近似)."""
    rng = np.random.RandomState(42)
    n = len(y_true)
    n_boot = 1000

    auc_a_full = roc_auc_score(y_true, y_prob_a)
    auc_b_full = roc_auc_score(y_true, y_prob_b)
    delta_full = auc_a_full - auc_b_full

    deltas = []
    for _ in range(n_boot):
        idx = rng.choice(n, n, replace=True)
        if len(np.unique(y_true[idx])) < 2:
            continue
        try:
            auc_a = roc_auc_score(y_true[idx], y_prob_a[idx])
            auc_b = roc_auc_score(y_true[idx], y_prob_b[idx])
            deltas.append(auc_a - auc_b)
        except ValueError:
            continue

    if len(deltas) < 100:
        return 0.0, 1.0
    deltas_arr = np.array(deltas)
    se = float(deltas_arr.std(ddof=1))
    if se == 0:
        return 0.0, 1.0
    z = delta_full / se
    from scipy.stats import norm

    p_value = 2 * (1 - norm.cdf(abs(z)))
    return float(z), float(p_value)


def train_logreg(
    X_tr: np.ndarray, y_tr: np.ndarray, seed: int, C: float = 1.0
) -> LogisticRegression:
    """LogReg + 标准化."""
    scaler = StandardScaler()
    X_tr_scaled = scaler.fit_transform(X_tr)
    model = LogisticRegression(
        C=C,
        class_weight="balanced",
        max_iter=2000,
        random_state=seed,
        solver="lbfgs",
    )
    model.fit(X_tr_scaled, y_tr)
    model.scaler_ = scaler
    return model


def model_predict_proba(model: Any, X: np.ndarray) -> np.ndarray:
    """统一预测接口."""
    if hasattr(model, "scaler_"):
        return model.predict_proba(model.scaler_.transform(X))[:, 1]
    return model.predict_proba(X)[:, 1]


def generate_oof(
    X: np.ndarray, y: np.ndarray, seed: int, C: float = 1.0
) -> np.ndarray:
    """内层 5-fold CV 生成 OOF 预测."""
    inner_skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    oof = np.zeros(len(y))
    for inner_tr, inner_va in inner_skf.split(X, y):
        m = train_logreg(X[inner_tr], y[inner_tr], seed, C)
        oof[inner_va] = model_predict_proba(m, X[inner_va])
    return oof


def stacking_fusion_v1(
    prob_s_oof: np.ndarray,
    prob_t_oof: np.ndarray,
    y_train: np.ndarray,
    prob_s_test: np.ndarray,
    prob_t_test: np.ndarray,
    seed: int,
) -> np.ndarray:
    """Stacking: LogReg 元学习器 on OOF 概率 + 交互特征 (v1)."""
    X_meta_train = np.column_stack(
        [
            prob_s_oof,
            prob_t_oof,
            prob_s_oof * prob_t_oof,
            np.abs(prob_s_oof - prob_t_oof),
        ]
    )
    X_meta_test = np.column_stack(
        [
            prob_s_test,
            prob_t_test,
            prob_s_test * prob_t_test,
            np.abs(prob_s_test - prob_t_test),
        ]
    )
    meta = LogisticRegression(C=10.0, max_iter=1000, random_state=seed, solver="lbfgs")
    meta.fit(X_meta_train, y_train)
    return meta.predict_proba(X_meta_test)[:, 1]


# ---------------------------------------------------------------------------
# 变体配置与模态准备
# ---------------------------------------------------------------------------


@dataclass
class VariantConfig:
    name: str
    struct_cols: list[str]
    c_structured: float = 1.0
    c_text: float = 0.5
    # --- v2 扩展 ---
    pca_components: int | None = None      # 文本嵌入 PCA 目标维 (None=不降维, v1)
    early_fusion: bool = False             # 是否构建 concat 早融合特征集
    summary_style: str = "v1"              # 摘要字段风格 ("v1" | "v2" | "v3")
    strategies_override: list[tuple[str, Path | None]] | None = None  # 预留
    # --- v3 扩展 (第三模态 lexical) ---
    lexical_cols: list[str] | None = None  # v3: 词频模态特征列
    c_lexical: float = 0.5                 # v3: 词频模态正则化强度


VARIANTS: dict[str, VariantConfig] = {
    "v1": VariantConfig(name="v1", struct_cols=["gad7_score"]),
}

# v1 策略评估顺序（与 m4_fusion_retrain.py 原脚本一致）
V1_STRATEGIES = [
    "structured_only",
    "text_only",
    "static_weighted",
    "stacking",
]

# --- v2 常量 (忠实移植自 m4_fusion_retrain_v2.py) ---
STRUCTURED_FEATURES_V2 = [
    "gad7_score",
    "age",
    "cgpa",
    "total_keywords",
    "unique_categories",
    "text_length",
    "chinese_ratio",
    "crisis_weighted",
    "coverage_density",
    "kw_low_mood",
]
PCA_N_COMPONENTS_V2 = 50

VARIANTS["v2"] = VariantConfig(
    name="v2",
    struct_cols=STRUCTURED_FEATURES_V2,
    c_structured=1.0,
    c_text=0.1,           # v2: 文本模态更强正则化 (0.5 → 0.1)
    pca_components=PCA_N_COMPONENTS_V2,
    early_fusion=True,
    summary_style="v2",
)

# --- v3 常量 (忠实移植自 m4_fusion_retrain_v3.py) ---
STRUCTURED_FEATURES_V3 = [
    "gad7_score",
    "age",
    "cgpa",
    "crisis_weighted",
]
LEXICAL_FEATURES_V3 = [
    "total_keywords",
    "unique_categories",
    "text_length",
    "chinese_ratio",
    "coverage_density",
    "kw_academic_pressure",
    "kw_sleep_problem",
    "kw_social_withdrawal",
    "kw_self_harm_crisis",
    "kw_exercise_deficit",
    "kw_low_mood",
    "kw_anxiety_somatic",
]
PCA_N_COMPONENTS_V3 = 50

VARIANTS["v3"] = VariantConfig(
    name="v3",
    struct_cols=STRUCTURED_FEATURES_V3,
    c_structured=1.0,
    c_text=0.1,           # v3 与 v2 同: 文本模态 C=0.1
    lexical_cols=LEXICAL_FEATURES_V3,
    c_lexical=0.5,        # v3: 词频模态 C=0.5
    pca_components=PCA_N_COMPONENTS_V3,
    early_fusion=True,
    summary_style="v3",
)

# --- v4 常量 (忠实移植自 m4_fusion_retrain_v4.py) ---
STRUCTURED_FEATURES_V4 = [
    "gad7_score",
    "age",
    "cgpa",
    "crisis_weighted",
]
LEXICAL_FEATURES_V4 = [
    "total_keywords",
    "unique_categories",
    "text_length",
    "chinese_ratio",
    "coverage_density",
    "kw_academic_pressure",
    "kw_sleep_problem",
    "kw_social_withdrawal",
    "kw_self_harm_crisis",
    "kw_exercise_deficit",
    "kw_low_mood",
    "kw_anxiety_somatic",
]
PCA_N_COMPONENTS_V4 = 50

VARIANTS["v4"] = VariantConfig(
    name="v4",
    struct_cols=STRUCTURED_FEATURES_V4,
    c_structured=1.0,     # 脚本内为硬编码字面量, 此处仅注册存档
    c_text=0.1,
    lexical_cols=LEXICAL_FEATURES_V4,
    c_lexical=0.5,
    pca_components=PCA_N_COMPONENTS_V4,
    summary_style="v4",
)

# --- stacking 常量 (忠实移植自 m4_fusion_stacking.py) ---
# 注意: 该脚本的验收阈值/文本特征集/基模型 max_iter 与共享常量不同,
# 不得复用 TARGET_AUC_LIFT(0.03)/train_logreg(max_iter=2000), 见下方组件区。
STACKING_TARGET_AUC_LIFT = 0.02  # m4_fusion_stacking.py 自身阈值
# 排除 phq9_score (corr=0.798, 标签泄漏); 排除 age/gender/cgpa (常量无方差)
QUESTIONNAIRE_FEATURES_STACKING = ["gad7_score"]
TEXT_FEATURES_STACKING = [
    "total_keywords", "unique_categories", "text_length", "chinese_ratio",
    "text_quality_flag", "crisis_weighted", "coverage_density",
    "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
    "kw_self_harm_crisis", "kw_exercise_deficit", "kw_low_mood", "kw_anxiety_somatic",
]
STACKING_STATIC_WEIGHTS = {"structured": 0.40, "text": 0.60}

VARIANTS["stacking"] = VariantConfig(
    name="stacking",
    struct_cols=QUESTIONNAIRE_FEATURES_STACKING,
    c_structured=1.0,     # train_structured_model 的 C (max_iter=1000 不复用共享件)
    c_text=0.5,           # train_text_model 的 C
    summary_style="stacking",
)


# --- v2 策略组件 (逐句移植) -------------------------------------------------


def stacking_fusion_v2(
    prob_s_oof: np.ndarray,
    prob_t_oof: np.ndarray,
    y_train: np.ndarray,
    prob_s_test: np.ndarray,
    prob_t_test: np.ndarray,
    seed: int,
) -> np.ndarray:
    """Stacking v2: 增强元特征 (二次项 + 交互 + 极值)."""
    X_meta_train = np.column_stack(
        [
            prob_s_oof,
            prob_t_oof,
            prob_s_oof * prob_t_oof,
            np.abs(prob_s_oof - prob_t_oof),
            prob_s_oof**2,
            prob_t_oof**2,
            np.maximum(prob_s_oof, prob_t_oof),
            np.minimum(prob_s_oof, prob_t_oof),
        ]
    )
    X_meta_test = np.column_stack(
        [
            prob_s_test,
            prob_t_test,
            prob_s_test * prob_t_test,
            np.abs(prob_s_test - prob_t_test),
            prob_s_test**2,
            prob_t_test**2,
            np.maximum(prob_s_test, prob_t_test),
            np.minimum(prob_s_test, prob_t_test),
        ]
    )
    # 元学习器: L2 正则化 LogReg, 避免过拟合 8 个元特征
    meta = LogisticRegression(C=1.0, max_iter=1000, random_state=seed, solver="lbfgs")
    meta.fit(X_meta_train, y_train)
    return meta.predict_proba(X_meta_test)[:, 1]


def xgb_meta_fusion(
    prob_s_oof: np.ndarray,
    prob_t_oof: np.ndarray,
    y_train: np.ndarray,
    prob_s_test: np.ndarray,
    prob_t_test: np.ndarray,
    seed: int,
) -> np.ndarray:
    """XGBoost 元学习器对照."""
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return stacking_fusion_v2(
            prob_s_oof, prob_t_oof, y_train, prob_s_test, prob_t_test, seed
        )

    X_meta_train = np.column_stack(
        [
            prob_s_oof,
            prob_t_oof,
            prob_s_oof * prob_t_oof,
            np.abs(prob_s_oof - prob_t_oof),
        ]
    )
    X_meta_test = np.column_stack(
        [
            prob_s_test,
            prob_t_test,
            prob_s_test * prob_t_test,
            np.abs(prob_s_test - prob_t_test),
        ]
    )
    # 浅层 XGBoost, 避免过拟合
    meta = XGBClassifier(
        n_estimators=50,
        max_depth=2,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=seed,
        eval_metric="logloss",
        use_label_encoder=False,
        n_jobs=1,
    )
    meta.fit(X_meta_train, y_train)
    return meta.predict_proba(X_meta_test)[:, 1]


# --- v3 策略组件 (逐句移植自 m4_fusion_retrain_v3.py, 第三模态构建方式照抄) ---


def trimodal_stacking(
    probs_oof: list[np.ndarray], y_train: np.ndarray,
    probs_test: list[np.ndarray], seed: int,
) -> np.ndarray:
    """三模态 stacking: 元特征 = 3 模态概率 + 两两交互 + 极值."""
    prob_s_oof, prob_t_oof, prob_l_oof = probs_oof
    prob_s_test, prob_t_test, prob_l_test = probs_test

    def build_meta(p_s, p_t, p_l):
        return np.column_stack([
            p_s, p_t, p_l,
            p_s * p_t, p_s * p_l, p_t * p_l,
            p_s * p_t * p_l,
            np.abs(p_s - p_t), np.abs(p_s - p_l), np.abs(p_t - p_l),
            np.maximum(np.maximum(p_s, p_t), p_l),
            np.minimum(np.minimum(p_s, p_t), p_l),
            p_s ** 2, p_t ** 2, p_l ** 2,
        ])

    X_meta_train = build_meta(prob_s_oof, prob_t_oof, prob_l_oof)
    X_meta_test = build_meta(prob_s_test, prob_t_test, prob_l_test)
    meta = LogisticRegression(
        C=0.5, max_iter=2000, random_state=seed, solver="lbfgs",
    )
    meta.fit(X_meta_train, y_train)
    return meta.predict_proba(X_meta_test)[:, 1]


def trimodal_optimized_weighted(
    probs_oof: list[np.ndarray], y_train: np.ndarray,
    probs_test: list[np.ndarray], seed: int,
) -> np.ndarray:
    """三模态优化权重 (3D 网格搜索)."""
    prob_s_oof, prob_t_oof, prob_l_oof = probs_oof
    prob_s_test, prob_t_test, prob_l_test = probs_test

    best_ws, best_auc = (1.0, 0.0, 0.0), 0.0
    # 粗搜索 (步长 0.1)
    for ws, wt, wl in product(np.arange(0.0, 1.01, 0.1), repeat=3):
        if abs(ws + wt + wl - 1.0) > 0.01:
            continue
        blended = ws * prob_s_oof + wt * prob_t_oof + wl * prob_l_oof
        try:
            auc = roc_auc_score(y_train, blended)
        except ValueError:
            continue
        if auc > best_auc:
            best_auc = auc
            best_ws = (ws, wt, wl)

    # 细搜索 (步长 0.02, 围绕粗搜索最优)
    ws0, wt0, wl0 = best_ws
    for ws, wt, wl in product(
        np.arange(max(0, ws0 - 0.1), min(1.01, ws0 + 0.11), 0.02),
        np.arange(max(0, wt0 - 0.1), min(1.01, wt0 + 0.11), 0.02),
        np.arange(max(0, wl0 - 0.1), min(1.01, wl0 + 0.11), 0.02),
    ):
        if abs(ws + wt + wl - 1.0) > 0.005:
            continue
        blended = ws * prob_s_oof + wt * prob_t_oof + wl * prob_l_oof
        try:
            auc = roc_auc_score(y_train, blended)
        except ValueError:
            continue
        if auc > best_auc:
            best_auc = auc
            best_ws = (ws, wt, wl)

    ws, wt, wl = best_ws
    return ws * prob_s_test + wt * prob_t_test + wl * prob_l_test


# --- v4 策略组件 (逐句移植自 m4_fusion_retrain_v4.py) -----------------------


def train_rf(X_tr: np.ndarray, y_tr: np.ndarray, seed: int) -> RandomForestClassifier:
    """Random Forest 基模型 (捕获非线性)."""
    model = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=10,
        class_weight="balanced", random_state=seed, n_jobs=1,
    )
    model.fit(X_tr, y_tr)
    return model


def generate_oof_rf(X: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    """RF OOF 预测."""
    inner_skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    oof = np.zeros(len(y))
    for inner_tr, inner_va in inner_skf.split(X, y):
        m = train_rf(X[inner_tr], y[inner_tr], seed)
        oof[inner_va] = model_predict_proba(m, X[inner_va])
    return oof


def calibrate_prob(prob_oof: np.ndarray, y: np.ndarray, prob_test: np.ndarray) -> np.ndarray:
    """Isotonic 回归校准."""
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(prob_oof, y)
    return iso.predict(prob_test)


def logreg_meta_fusion(
    probs_oof: list[np.ndarray], y_train: np.ndarray,
    probs_test: list[np.ndarray], seed: int,
) -> np.ndarray:
    """LogReg 元学习器 (fallback).

    忠实性核查: 本函数体与上方已验证的 trimodal_stacking 逐字一致
    (12 维元特征表达式顺序、LogReg(C=0.5, max_iter=2000) 构造参数完全相同),
    故委托复用同一条数值路径。
    """
    return trimodal_stacking(probs_oof, y_train, probs_test, seed)


def lgbm_meta_fusion(
    probs_oof: list[np.ndarray], y_train: np.ndarray,
    probs_test: list[np.ndarray], seed: int,
) -> np.ndarray:
    """LightGBM 元学习器 + 增强元特征."""
    try:
        from lightgbm import LGBMClassifier
    except ImportError:
        # fallback to LogReg
        return logreg_meta_fusion(probs_oof, y_train, probs_test, seed)

    prob_s_oof, prob_t_oof, prob_l_oof = probs_oof
    prob_s_test, prob_t_test, prob_l_test = probs_test

    def build_meta(p_s, p_t, p_l):
        # 防止 log(0)
        eps = 1e-6
        p_s_safe = np.clip(p_s, eps, 1 - eps)
        p_t_safe = np.clip(p_t, eps, 1 - eps)
        p_l_safe = np.clip(p_l, eps, 1 - eps)
        return np.column_stack([
            p_s, p_t, p_l,
            p_s * p_t, p_s * p_l, p_t * p_l,
            p_s * p_t * p_l,
            np.abs(p_s - p_t), np.abs(p_s - p_l), np.abs(p_t - p_l),
            np.maximum(np.maximum(p_s, p_t), p_l),
            np.minimum(np.minimum(p_s, p_t), p_l),
            # v4 新增: log-ratio
            np.log(p_s_safe / p_t_safe),
            np.log(p_s_safe / p_l_safe),
            np.log(p_t_safe / p_l_safe),
            # v4 新增: 风险等级一致性 (是否所有模态都 > 0.5)
            ((p_s > 0.5).astype(int) + (p_t > 0.5).astype(int) + (p_l > 0.5).astype(int)),
            # v4 新增: 不确定性 (熵)
            -(p_s_safe * np.log(p_s_safe) + (1 - p_s_safe) * np.log(1 - p_s_safe)),
            -(p_t_safe * np.log(p_t_safe) + (1 - p_t_safe) * np.log(1 - p_t_safe)),
            -(p_l_safe * np.log(p_l_safe) + (1 - p_l_safe) * np.log(1 - p_l_safe)),
        ])

    X_meta_train = build_meta(prob_s_oof, prob_t_oof, prob_l_oof)
    X_meta_test = build_meta(prob_s_test, prob_t_test, prob_l_test)

    meta = LGBMClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1,
        random_state=seed, n_jobs=1, verbose=-1,
    )
    meta.fit(X_meta_train, y_train)
    return meta.predict_proba(X_meta_test)[:, 1]


# --- stacking 脚本策略组件 (逐句移植自 m4_fusion_stacking.py) ---------------


def train_structured_model(X_tr: np.ndarray, y_tr: np.ndarray, seed: int) -> LogisticRegression:
    """结构化模态: LogReg + 标准化 (gad7_score 单特征, max_iter=1000 与共享件不同)."""
    scaler = StandardScaler()
    X_tr_scaled = scaler.fit_transform(X_tr)
    model = LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=1000,
        random_state=seed, solver="lbfgs",
    )
    model.fit(X_tr_scaled, y_tr)
    # 把 scaler 附在 model 上
    model.scaler_ = scaler
    return model


def train_text_model(X_tr: np.ndarray, y_tr: np.ndarray, seed: int) -> Any:
    """文本模态: LogReg + 标准化 (14 特征, C=0.5, max_iter=1000)."""
    scaler = StandardScaler()
    X_tr_scaled = scaler.fit_transform(X_tr)
    model = LogisticRegression(
        C=0.5, class_weight="balanced", max_iter=1000,
        random_state=seed, solver="lbfgs",
    )
    model.fit(X_tr_scaled, y_tr)
    model.scaler_ = scaler
    return model


def static_weighted_fusion(
    prob_s: np.ndarray, prob_t: np.ndarray,
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """静态加权融合."""
    w = weights or STACKING_STATIC_WEIGHTS
    return w["structured"] * prob_s + w["text"] * prob_t


def stacking_fusion(
    prob_s_train: np.ndarray, prob_t_train: np.ndarray, y_train: np.ndarray,
    prob_s_test: np.ndarray, prob_t_test: np.ndarray, seed: int,
) -> tuple[np.ndarray, LogisticRegression]:
    """Stacking: LogReg 元学习器在 OOF 概率 + 交互特征上训练 (返回元学习器)."""
    # 构造元特征 (含交互项)
    X_meta_train = np.column_stack([
        prob_s_train, prob_t_train,
        prob_s_train * prob_t_train,
        np.abs(prob_s_train - prob_t_train),
    ])
    X_meta_test = np.column_stack([
        prob_s_test, prob_t_test,
        prob_s_test * prob_t_test,
        np.abs(prob_s_test - prob_t_test),
    ])
    meta = LogisticRegression(
        C=10.0, max_iter=1000, random_state=seed, solver="lbfgs",
    )
    meta.fit(X_meta_train, y_train)
    prob_fusion = meta.predict_proba(X_meta_test)[:, 1]
    return prob_fusion, meta


def gated_weighted_fusion(
    prob_s_train: np.ndarray, prob_t_train: np.ndarray, y_train: np.ndarray,
    prob_s_test: np.ndarray, prob_t_test: np.ndarray, seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """门控加权: 用 |prob-0.5| 置信度比例作为每个样本的模态权重."""
    conf_s_test = np.abs(prob_s_test - 0.5)
    conf_t_test = np.abs(prob_t_test - 0.5)

    total_conf_test = conf_s_test + conf_t_test + 1e-8
    w_s_test = conf_s_test / total_conf_test
    w_t_test = conf_t_test / total_conf_test

    prob_fusion = w_s_test * prob_s_test + w_t_test * prob_t_test
    return prob_fusion, {
        "method": "confidence_gated",
        "mean_w_structured": float(w_s_test.mean()),
        "mean_w_text": float(w_t_test.mean()),
    }


def stacking_gbdt_fusion(
    prob_s_train: np.ndarray, prob_t_train: np.ndarray, y_train: np.ndarray,
    prob_s_test: np.ndarray, prob_t_test: np.ndarray, seed: int,
) -> tuple[np.ndarray, Any]:
    """Stacking with GBDT 元学习器: 浅树 + 强正则防小样本过拟合."""
    import xgboost as xgb

    X_meta_train = np.column_stack([
        prob_s_train, prob_t_train,
        prob_s_train * prob_t_train,
        np.abs(prob_s_train - prob_t_train),
    ])
    X_meta_test = np.column_stack([
        prob_s_test, prob_t_test,
        prob_s_test * prob_t_test,
        np.abs(prob_s_test - prob_t_test),
    ])
    meta = xgb.XGBClassifier(
        max_depth=3, n_estimators=100, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9,
        reg_alpha=0.5, reg_lambda=2.0,
        min_child_weight=5,
        objective="binary:logistic", eval_metric="auc",
        tree_method="hist", random_state=seed, n_jobs=-1, verbosity=0,
    )
    meta.fit(X_meta_train, y_train)
    prob_fusion = meta.predict_proba(X_meta_test)[:, 1]
    return prob_fusion, meta


def generate_oof_predictions(
    X: np.ndarray,
    y: np.ndarray,
    train_fn: Any,
    seed: int,
    n_inner_folds: int = 5,
) -> np.ndarray:
    """内层 K-fold CV 生成 OOF 预测 (基模型构造函数参数化).

    与共享 generate_oof 不能合并的原因: train_fn 泛化 (structured/text 模型
    C 值与 max_iter 不同), 且 n_inner_folds 为显式默认参 5。
    """
    inner_skf = StratifiedKFold(n_splits=n_inner_folds, shuffle=True, random_state=seed)
    oof = np.zeros(len(y))
    for inner_tr, inner_va in inner_skf.split(X, y):
        m = train_fn(X[inner_tr], y[inner_tr], seed)
        oof[inner_va] = model_predict_proba(m, X[inner_va])
    return oof


def prepare_xy_v1(
    df: pd.DataFrame, cfg: VariantConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """加载并对齐双模态与标签; NaN 以列中位数填充 (v1 语义).

    结构化特征列由 cfg.struct_cols 决定 (v1 为 gad7 单特征),
    文本模态为预计算 BERT [CLS] 嵌入。
    """
    bert_emb = np.load(BERT_CACHE_PATH)
    assert len(df) == bert_emb.shape[0], (
        f"样本数不匹配: df={len(df)}, bert={bert_emb.shape[0]}"
    )

    X_structured = df[cfg.struct_cols].values.astype(np.float32)
    X_text = bert_emb.astype(np.float32)
    y = df[TARGET_COL].astype(int).values

    for arr, name in [(X_structured, "structured"), (X_text, "text")]:
        col_medians = np.nanmedian(arr, axis=0)
        nan_mask = np.isnan(arr)
        if nan_mask.sum() > 0:
            arr[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])
            logger.info("[%s] 填充 %d 个 NaN", name, nan_mask.sum())

    return X_structured, X_text, y


def prepare_xy_v2(
    df: pd.DataFrame, cfg: VariantConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, float]:
    """v2 数据准备: 10 维结构化 + BERT PCA 降维 + 早融合 concat.

    NaN 填充顺序与原脚本一致: structured → text_pca → combined。

    Returns:
        (X_structured, X_text_pca, X_combined|None, pca_explained_variance)
    """
    assert cfg.pca_components is not None

    bert_emb = np.load(BERT_CACHE_PATH)
    assert len(df) == bert_emb.shape[0], (
        f"样本数不匹配: df={len(df)}, bert={bert_emb.shape[0]}"
    )

    X_structured = df[cfg.struct_cols].values.astype(np.float32)

    # 文本模态: BERT → PCA 降维
    pca = PCA(n_components=cfg.pca_components, random_state=42)
    X_text_pca = pca.fit_transform(bert_emb.astype(np.float32))
    explained_variance = float(pca.explained_variance_ratio_.sum())
    logger.info(
        "BERT PCA 降维: %d → %d 维, 保留方差比=%.4f",
        bert_emb.shape[1],
        cfg.pca_components,
        explained_variance,
    )

    # 早融合: concat(structured, text_pca)
    X_combined: np.ndarray | None = None
    if cfg.early_fusion:
        X_combined = np.hstack([X_structured, X_text_pca])

    for arr, name in [
        (X_structured, "structured"),
        (X_text_pca, "text_pca"),
        (X_combined, "combined"),
    ]:
        col_medians = np.nanmedian(arr, axis=0)
        nan_mask = np.isnan(arr)
        if nan_mask.sum() > 0:
            arr[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])
            logger.info("[%s] 填充 %d 个 NaN", name, nan_mask.sum())

    return X_structured, X_text_pca, X_combined, explained_variance


def prepare_xy_v3(
    df: pd.DataFrame, cfg: VariantConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, float]:
    """v3 数据准备: 4 维结构化 + BERT PCA + 12 维词频 + 三模态早融合 concat.

    构建顺序与原脚本一致: structured → text_pca(PCA fit) → lexical → combined;
    NaN 填充顺序与原脚本一致: structured → text_pca → lexical → combined。

    Returns:
        (X_structured, X_text_pca, X_lexical, X_combined|None,
         pca_explained_variance)
    """
    assert cfg.pca_components is not None
    assert cfg.lexical_cols is not None

    bert_emb = np.load(BERT_CACHE_PATH)
    assert len(df) == bert_emb.shape[0], (
        f"样本数不匹配: df={len(df)}, bert={bert_emb.shape[0]}"
    )

    # 模态 1: structured
    X_structured = df[cfg.struct_cols].values.astype(np.float32)

    # 模态 2: text_bert → PCA
    pca = PCA(n_components=cfg.pca_components, random_state=42)
    X_text_pca = pca.fit_transform(bert_emb.astype(np.float32))
    explained_variance = float(pca.explained_variance_ratio_.sum())
    logger.info(
        "文本模态 (BERT PCA): %d → %d 维, 方差保留=%.4f",
        bert_emb.shape[1],
        cfg.pca_components,
        explained_variance,
    )

    # 模态 3: lexical
    X_lexical = df[cfg.lexical_cols].values.astype(np.float32)

    # 早融合: concat(structured, text_pca, lexical)
    X_combined: np.ndarray | None = None
    if cfg.early_fusion:
        X_combined = np.hstack([X_structured, X_text_pca, X_lexical])

    for arr, name in [
        (X_structured, "structured"),
        (X_text_pca, "text_pca"),
        (X_lexical, "lexical"),
        (X_combined, "combined"),
    ]:
        col_medians = np.nanmedian(arr, axis=0)
        nan_mask = np.isnan(arr)
        if nan_mask.sum() > 0:
            arr[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])
            logger.info("[%s] 填充 %d 个 NaN", name, nan_mask.sum())

    return X_structured, X_text_pca, X_lexical, X_combined, explained_variance


def prepare_xy_v4(
    df: pd.DataFrame, cfg: VariantConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """v4 数据准备: 4 维结构化 + BERT PCA 50 + 12 维词频 (语句顺序照抄 v4 脚本).

    与 v3 的差异: 无早融合 concat; NaN 填充仅三轮 (structured/text_pca/lexical);
    y 在词频模态之后、NaN 填充之前构建 (与 run_m4_fusion_v4 内顺序一致)。

    Returns:
        (X_structured, X_text_pca, X_lexical, y, pca_explained_variance)
    """
    assert cfg.pca_components is not None
    assert cfg.lexical_cols is not None

    bert_emb = np.load(BERT_CACHE_PATH)
    assert len(df) == bert_emb.shape[0]

    # 模态 1: structured
    X_structured = df[cfg.struct_cols].values.astype(np.float32)
    logger.info("结构化模态: %d 维", X_structured.shape[1])

    # 模态 2: text_bert → PCA
    pca = PCA(n_components=cfg.pca_components, random_state=42)
    X_text_pca = pca.fit_transform(bert_emb.astype(np.float32))
    explained_variance = float(pca.explained_variance_ratio_.sum())
    logger.info(
        "文本模态 (BERT PCA): %d → %d 维, 方差保留=%.4f",
        bert_emb.shape[1],
        cfg.pca_components,
        explained_variance,
    )

    # 模态 3: lexical
    X_lexical = df[cfg.lexical_cols].values.astype(np.float32)
    logger.info("词频模态: %d 维", X_lexical.shape[1])

    y = df[TARGET_COL].astype(int).values

    # NaN 处理 (中位数填充; 原脚本 summary 处为对 explained_variance_ratio_.sum()
    # 的二次调用, 纯函数结果逐位相同, 故复用单次取值)
    for arr, name in [
        (X_structured, "structured"),
        (X_text_pca, "text_pca"),
        (X_lexical, "lexical"),
    ]:
        col_medians = np.nanmedian(arr, axis=0)
        nan_mask = np.isnan(arr)
        if nan_mask.sum() > 0:
            arr[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])
            logger.info("[%s] 填充 %d 个 NaN", name, nan_mask.sum())

    return X_structured, X_text_pca, X_lexical, y, explained_variance


# ---------------------------------------------------------------------------
# 策略评估骨架 (分派逻辑与 v1 分支逐一对应)
# ---------------------------------------------------------------------------


def apply_strategy(
    strategy_name: str,
    prob_s_test: np.ndarray,
    prob_t_test: np.ndarray,
    X_s_tr: np.ndarray,
    y_tr: np.ndarray,
    X_t_tr: np.ndarray,
    seed: int,
    cfg: VariantConfig,
    X_combined: np.ndarray | None = None,
    X_c_tr: np.ndarray | None = None,
    X_c_te: np.ndarray | None = None,
) -> np.ndarray:
    """策略分派 (v1/v2 全部策略; 分支与原脚本逐一对应)."""
    if strategy_name == "structured_only":
        return prob_s_test
    if strategy_name == "text_only":
        return prob_t_test
    if strategy_name == "static_weighted":
        # 保持 v1 表达式原序: 先 0.4*s 后 0.6*t 再相加
        return 0.4 * prob_s_test + 0.6 * prob_t_test
    if strategy_name == "stacking":
        prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=cfg.c_structured)
        prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=cfg.c_text)
        return stacking_fusion_v1(
            prob_s_oof, prob_t_oof, y_tr, prob_s_test, prob_t_test, seed
        )
    if strategy_name == "optimized_weighted":
        # v2: 训练集 OOF 上网格搜索最优加权
        prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=cfg.c_structured)
        prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=cfg.c_text)
        best_w, best_auc = 0.5, 0.0
        for w in np.arange(0.0, 1.01, 0.05):
            blended = w * prob_s_oof + (1 - w) * prob_t_oof
            try:
                auc = roc_auc_score(y_tr, blended)
            except ValueError:
                continue
            if auc > best_auc:
                best_auc = auc
                best_w = w
        return best_w * prob_s_test + (1 - best_w) * prob_t_test
    if strategy_name == "stacking_v2":
        prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=cfg.c_structured)
        prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=cfg.c_text)
        return stacking_fusion_v2(
            prob_s_oof, prob_t_oof, y_tr, prob_s_test, prob_t_test, seed
        )
    if strategy_name == "xgb_meta":
        prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=cfg.c_structured)
        prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=cfg.c_text)
        return xgb_meta_fusion(
            prob_s_oof, prob_t_oof, y_tr, prob_s_test, prob_t_test, seed
        )
    if strategy_name == "early_fusion":
        # v2 早融合: concat(structured, text_pca) → 单 LogReg
        if X_combined is None or X_c_tr is None or X_c_te is None:
            raise ValueError("early_fusion 需要 X_combined")
        m_c = train_logreg(X_c_tr, y_tr, seed, C=0.5)
        return model_predict_proba(m_c, X_c_te)
    raise ValueError(f"Unknown strategy: {strategy_name}")


V2_STRATEGIES: list[tuple[str, bool]] = [
    # (名称, 是否早融合数据集)
    ("structured_only", False),
    ("text_only", False),
    ("static_weighted", False),
    ("optimized_weighted", False),
    ("early_fusion", True),
    ("stacking_v2", False),
    ("xgb_meta", False),
]


def evaluate_strategy_v2(
    strategy_name: str,
    X_structured: np.ndarray,
    X_text: np.ndarray,
    y: np.ndarray,
    X_combined: np.ndarray | None,
    c_structured: float,
    c_text: float,
) -> dict[str, Any]:
    """5-fold × 3 seeds 嵌套 CV 评估 (骨架与 v2 脚本逐句同构)."""
    all_auc = []
    all_f1 = []
    fold_details = []
    all_prob_fusion = np.zeros(len(y))
    count_fusion = np.zeros(len(y))

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_structured, y)):
            X_s_tr, X_s_te = X_structured[tr_idx], X_structured[te_idx]
            X_t_tr, X_t_te = X_text[tr_idx], X_text[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            # 不同模态使用不同正则化强度
            m_s = train_logreg(X_s_tr, y_tr, seed, C=c_structured)
            m_t = train_logreg(X_t_tr, y_tr, seed, C=c_text)

            prob_s_test = model_predict_proba(m_s, X_s_te)
            prob_t_test = model_predict_proba(m_t, X_t_te)

            X_c_tr = X_c_te = None
            if X_combined is not None:
                X_c_tr, X_c_te = X_combined[tr_idx], X_combined[te_idx]

            prob_fusion = apply_strategy(
                strategy_name,
                prob_s_test,
                prob_t_test,
                X_s_tr,
                y_tr,
                X_t_tr,
                seed,
                VARIANTS["v2"],
                X_combined=X_combined,
                X_c_tr=X_c_tr,
                X_c_te=X_c_te,
            )

            auc = (
                float(roc_auc_score(y_te, prob_fusion))
                if len(np.unique(y_te)) > 1
                else 0.5
            )
            y_pred = (prob_fusion >= 0.5).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            all_auc.append(auc)
            all_f1.append(f1)
            fold_details.append({"seed": seed, "fold": fold_idx, "auc": auc, "f1": f1})

            all_prob_fusion[te_idx] += prob_fusion
            count_fusion[te_idx] += 1

    all_prob_fusion = all_prob_fusion / np.maximum(count_fusion, 1)

    auc_arr = np.array(all_auc)
    f1_arr = np.array(all_f1)
    auc_mean = float(auc_arr.mean())
    auc_std = float(auc_arr.std(ddof=1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))
    f1_mean = float(f1_arr.mean())
    f1_std = float(f1_arr.std(ddof=1))
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))

    return {
        "strategy": strategy_name,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "n_evaluations": len(all_auc),
        "fold_details": fold_details,
        "full_prob": all_prob_fusion,
    }


def evaluate_strategy_v3(
    strategy_name: str,
    X_structured: np.ndarray,
    X_text: np.ndarray,
    X_lexical: np.ndarray,
    y: np.ndarray,
    cfg: VariantConfig,
    X_combined: np.ndarray | None = None,
) -> dict[str, Any]:
    """5-fold × 3 seeds 嵌套 CV 评估 (骨架与 v3 脚本 evaluate_strategy 逐句同构).

    与 v2 骨架不可共享的原因 (逐字段差异论证):
    - 三模态签名: 多出 X_lexical 参数与 m_l 训练/预测路径
    - 每折固定按 m_s(C=cfg.c_structured) → m_t(C=cfg.c_text) →
      m_l(C=cfg.c_lexical) 训练, 再依次生成三个 test 概率 (v2 仅两个模态)
    - 策略集合不同: structured_only / text_only / lexical_only /
      static_weighted_3 / trimodal_optimized / early_fusion_3 /
      trimodal_stacking; 其中 static_weighted_3 权重 (0.5,0.3,0.2) 与
      early_fusion_3 的 C=0.3 均为 v3 特有常量, 无法走 v2 的 apply_strategy 分派
    """
    all_auc = []
    all_f1 = []
    fold_details = []
    all_prob_fusion = np.zeros(len(y))
    count_fusion = np.zeros(len(y))

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_structured, y)):
            X_s_tr, X_s_te = X_structured[tr_idx], X_structured[te_idx]
            X_t_tr, X_t_te = X_text[tr_idx], X_text[te_idx]
            X_l_tr, X_l_te = X_lexical[tr_idx], X_lexical[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            m_s = train_logreg(X_s_tr, y_tr, seed, C=cfg.c_structured)
            m_t = train_logreg(X_t_tr, y_tr, seed, C=cfg.c_text)
            m_l = train_logreg(X_l_tr, y_tr, seed, C=cfg.c_lexical)

            prob_s_test = model_predict_proba(m_s, X_s_te)
            prob_t_test = model_predict_proba(m_t, X_t_te)
            prob_l_test = model_predict_proba(m_l, X_l_te)

            if strategy_name == "structured_only":
                prob_fusion = prob_s_test
            elif strategy_name == "text_only":
                prob_fusion = prob_t_test
            elif strategy_name == "lexical_only":
                prob_fusion = prob_l_test
            elif strategy_name == "static_weighted_3":
                # 保持原表达式顺序: 0.5*s、0.3*t、0.2*l 从左到右相加
                prob_fusion = (
                    0.5 * prob_s_test + 0.3 * prob_t_test + 0.2 * prob_l_test
                )
            elif strategy_name == "trimodal_optimized":
                prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=cfg.c_structured)
                prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=cfg.c_text)
                prob_l_oof = generate_oof(X_l_tr, y_tr, seed, C=cfg.c_lexical)
                prob_fusion = trimodal_optimized_weighted(
                    [prob_s_oof, prob_t_oof, prob_l_oof], y_tr,
                    [prob_s_test, prob_t_test, prob_l_test], seed,
                )
            elif strategy_name == "trimodal_stacking":
                prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=cfg.c_structured)
                prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=cfg.c_text)
                prob_l_oof = generate_oof(X_l_tr, y_tr, seed, C=cfg.c_lexical)
                prob_fusion = trimodal_stacking(
                    [prob_s_oof, prob_t_oof, prob_l_oof], y_tr,
                    [prob_s_test, prob_t_test, prob_l_test], seed,
                )
            elif strategy_name == "early_fusion_3":
                if X_combined is None:
                    raise ValueError("early_fusion_3 需要 X_combined")
                X_c_tr, X_c_te = X_combined[tr_idx], X_combined[te_idx]
                m_c = train_logreg(X_c_tr, y_tr, seed, C=0.3)
                prob_fusion = model_predict_proba(m_c, X_c_te)
            else:
                raise ValueError(f"Unknown strategy: {strategy_name}")

            auc = (
                float(roc_auc_score(y_te, prob_fusion))
                if len(np.unique(y_te)) > 1
                else 0.5
            )
            y_pred = (prob_fusion >= 0.5).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            all_auc.append(auc)
            all_f1.append(f1)
            fold_details.append({"seed": seed, "fold": fold_idx, "auc": auc, "f1": f1})

            all_prob_fusion[te_idx] += prob_fusion
            count_fusion[te_idx] += 1

    all_prob_fusion = all_prob_fusion / np.maximum(count_fusion, 1)

    auc_arr = np.array(all_auc)
    f1_arr = np.array(all_f1)
    auc_mean = float(auc_arr.mean())
    auc_std = float(auc_arr.std(ddof=1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))
    f1_mean = float(f1_arr.mean())
    f1_std = float(f1_arr.std(ddof=1))
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))

    return {
        "strategy": strategy_name,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "n_evaluations": len(all_auc),
        "fold_details": fold_details,
        "full_prob": all_prob_fusion,
    }


V4_STRATEGIES: list[str] = [
    "structured_only",
    "text_only",
    "lexical_only",
    "lgbm_meta",
    "rf_base_lgbm_meta",
    "hybrid_base_lgbm_meta",
]


def evaluate_strategy_v4(
    strategy_name: str,
    X_structured: np.ndarray,
    X_text: np.ndarray,
    X_lexical: np.ndarray,
    y: np.ndarray,
) -> dict[str, Any]:
    """5-fold × 3 seeds 嵌套 CV 评估 (骨架与 v4 脚本 evaluate_strategy 逐句同构).

    与 v3 骨架不可共享的原因: 基模型 C 为硬编码字面量 (1.0/0.1/0.5, 不经 cfg);
    策略族含 isotonic 校准路径 (校准仅作用于 test 概率, OOF 保持原值进元特征)、
    RF 全基座与混合基座分支; 元学习器为 LightGBM。
    注: 脚本内 generate_oof_logreg 与共享 generate_oof 函数体逐字一致, 直接复用。
    """
    all_auc = []
    all_f1 = []
    fold_details = []
    all_prob_fusion = np.zeros(len(y))
    count_fusion = np.zeros(len(y))

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_structured, y)):
            X_s_tr, X_s_te = X_structured[tr_idx], X_structured[te_idx]
            X_t_tr, X_t_te = X_text[tr_idx], X_text[te_idx]
            X_l_tr, X_l_te = X_lexical[tr_idx], X_lexical[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            # 基模型: LogReg
            m_s = train_logreg(X_s_tr, y_tr, seed, C=1.0)
            m_t = train_logreg(X_t_tr, y_tr, seed, C=0.1)
            m_l = train_logreg(X_l_tr, y_tr, seed, C=0.5)

            prob_s_test = model_predict_proba(m_s, X_s_te)
            prob_t_test = model_predict_proba(m_t, X_t_te)
            prob_l_test = model_predict_proba(m_l, X_l_te)

            if strategy_name == "structured_only":
                prob_fusion = prob_s_test
            elif strategy_name == "text_only":
                prob_fusion = prob_t_test
            elif strategy_name == "lexical_only":
                prob_fusion = prob_l_test
            elif strategy_name == "lgbm_meta":
                # OOF + 校准 + LightGBM 元学习器
                prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=1.0)
                prob_t_oof = generate_oof(X_t_tr, y_tr, seed, C=0.1)
                prob_l_oof = generate_oof(X_l_tr, y_tr, seed, C=0.5)
                # 校准
                prob_s_test_cal = calibrate_prob(prob_s_oof, y_tr, prob_s_test)
                prob_t_test_cal = calibrate_prob(prob_t_oof, y_tr, prob_t_test)
                prob_l_test_cal = calibrate_prob(prob_l_oof, y_tr, prob_l_test)
                prob_fusion = lgbm_meta_fusion(
                    [prob_s_oof, prob_t_oof, prob_l_oof], y_tr,
                    [prob_s_test_cal, prob_t_test_cal, prob_l_test_cal], seed,
                )
            elif strategy_name == "rf_base_lgbm_meta":
                # RF 基模型 + LightGBM 元学习器
                prob_s_oof_rf = generate_oof_rf(X_s_tr, y_tr, seed)
                prob_t_oof_rf = generate_oof_rf(X_t_tr, y_tr, seed)
                prob_l_oof_rf = generate_oof_rf(X_l_tr, y_tr, seed)
                # 测试集 RF 预测 (用训练集全量训练)
                m_s_rf = train_rf(X_s_tr, y_tr, seed)
                m_t_rf = train_rf(X_t_tr, y_tr, seed)
                m_l_rf = train_rf(X_l_tr, y_tr, seed)
                prob_s_test_rf = model_predict_proba(m_s_rf, X_s_te)
                prob_t_test_rf = model_predict_proba(m_t_rf, X_t_te)
                prob_l_test_rf = model_predict_proba(m_l_rf, X_l_te)
                prob_fusion = lgbm_meta_fusion(
                    [prob_s_oof_rf, prob_t_oof_rf, prob_l_oof_rf], y_tr,
                    [prob_s_test_rf, prob_t_test_rf, prob_l_test_rf], seed,
                )
            elif strategy_name == "hybrid_base_lgbm_meta":
                # 混合基模型: structured=LogReg, text=RF, lexical=LogReg
                prob_s_oof = generate_oof(X_s_tr, y_tr, seed, C=1.0)
                prob_t_oof_rf = generate_oof_rf(X_t_tr, y_tr, seed)
                prob_l_oof = generate_oof(X_l_tr, y_tr, seed, C=0.5)
                # 测试集
                m_t_rf = train_rf(X_t_tr, y_tr, seed)
                prob_t_test_rf = model_predict_proba(m_t_rf, X_t_te)
                prob_fusion = lgbm_meta_fusion(
                    [prob_s_oof, prob_t_oof_rf, prob_l_oof], y_tr,
                    [prob_s_test, prob_t_test_rf, prob_l_test], seed,
                )
            else:
                raise ValueError(f"Unknown strategy: {strategy_name}")

            auc = (
                float(roc_auc_score(y_te, prob_fusion))
                if len(np.unique(y_te)) > 1
                else 0.5
            )
            y_pred = (prob_fusion >= 0.5).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            all_auc.append(auc)
            all_f1.append(f1)
            fold_details.append({"seed": seed, "fold": fold_idx, "auc": auc, "f1": f1})

            all_prob_fusion[te_idx] += prob_fusion
            count_fusion[te_idx] += 1

    all_prob_fusion = all_prob_fusion / np.maximum(count_fusion, 1)

    auc_arr = np.array(all_auc)
    f1_arr = np.array(all_f1)
    auc_mean = float(auc_arr.mean())
    auc_std = float(auc_arr.std(ddof=1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))
    f1_mean = float(f1_arr.mean())
    f1_std = float(f1_arr.std(ddof=1))
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))

    return {
        "strategy": strategy_name,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "n_evaluations": len(all_auc),
        "fold_details": fold_details,
        "full_prob": all_prob_fusion,
    }


def evaluate_strategy_stacking(
    strategy_name: str,
    fusion_fn: Any,
    X_structured: np.ndarray,
    X_text: np.ndarray,
    y: np.ndarray,
) -> dict[str, Any]:
    """5-fold × 3 seeds 嵌套 CV 评估 (骨架与 m4_fusion_stacking.py 逐句同构).

    与 v1/v2/v3/v4 骨架均不可共享的原因 (逐字段差异论证):
    - 无全量概率累计 (原脚本没有 all_prob_fusion/count_fusion/full_prob);
    - AUC 计算无 ``len(np.unique(y_te)) > 1`` 守卫 (原脚本直接 roc_auc_score);
    - stacking/gated/gbdt 策略通过 fusion_fn 二元组接口返回 (携带 meta 对象),
      其余策略走 if/elif 短路; OOF 由泛化的 generate_oof_predictions(train_fn) 生成;
    - 返回字典保留 fold_details 在结果内 (由 _run_stacking 的 cv_results 过滤)。
    """
    fold_details = []
    all_auc = []
    all_f1 = []

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_structured, y)):
            X_s_tr, X_s_te = X_structured[tr_idx], X_structured[te_idx]
            X_t_tr, X_t_te = X_text[tr_idx], X_text[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            # 训练基模型 (在完整 train 上)
            m_s = train_structured_model(X_s_tr, y_tr, seed)
            m_t = train_text_model(X_t_tr, y_tr, seed)

            # test 集预测 (用完整 train 训练的模型)
            prob_s_test = model_predict_proba(m_s, X_s_te)
            prob_t_test = model_predict_proba(m_t, X_t_te)

            # 融合
            if strategy_name == "structured_only":
                prob_fusion = prob_s_test
            elif strategy_name == "text_only":
                prob_fusion = prob_t_test
            elif strategy_name == "static_weighted":
                prob_fusion = static_weighted_fusion(prob_s_test, prob_t_test)
            else:
                # 用 OOF 预测训练元学习器 (而非训练集自身预测)
                prob_s_oof = generate_oof_predictions(X_s_tr, y_tr, train_structured_model, seed)
                prob_t_oof = generate_oof_predictions(X_t_tr, y_tr, train_text_model, seed)
                prob_fusion, _ = fusion_fn(
                    prob_s_oof, prob_t_oof, y_tr,
                    prob_s_test, prob_t_test, seed,
                )

            # 评估
            auc = float(roc_auc_score(y_te, prob_fusion))
            y_pred = (prob_fusion >= 0.5).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            all_auc.append(auc)
            all_f1.append(f1)
            fold_details.append({"seed": seed, "fold": fold_idx, "auc": auc, "f1": f1})

    auc_arr = np.array(all_auc)
    f1_arr = np.array(all_f1)
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1))
    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))

    return {
        "strategy": strategy_name,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "n_evaluations": len(all_auc),
        "fold_details": fold_details,
    }


def evaluate_strategy(
    strategy_name: str,
    X_structured: np.ndarray,
    X_text: np.ndarray,
    y: np.ndarray,
    cfg: VariantConfig,
) -> dict[str, Any]:
    """5-fold × 3 seeds 嵌套 CV 评估 (骨架与 v1 逐句同构)."""
    all_auc = []
    all_f1 = []
    fold_details = []
    all_prob_fusion = np.zeros(len(y))
    count_fusion = np.zeros(len(y))

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_structured, y)):
            X_s_tr, X_s_te = X_structured[tr_idx], X_structured[te_idx]
            X_t_tr, X_t_te = X_text[tr_idx], X_text[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            m_s = train_logreg(X_s_tr, y_tr, seed, C=cfg.c_structured)
            m_t = train_logreg(X_t_tr, y_tr, seed, C=cfg.c_text)

            prob_s_test = model_predict_proba(m_s, X_s_te)
            prob_t_test = model_predict_proba(m_t, X_t_te)

            prob_fusion = apply_strategy(
                strategy_name,
                prob_s_test,
                prob_t_test,
                X_s_tr,
                y_tr,
                X_t_tr,
                seed,
                cfg,
            )

            auc = (
                float(roc_auc_score(y_te, prob_fusion))
                if len(np.unique(y_te)) > 1
                else 0.5
            )
            y_pred = (prob_fusion >= 0.5).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            all_auc.append(auc)
            all_f1.append(f1)
            fold_details.append({"seed": seed, "fold": fold_idx, "auc": auc, "f1": f1})

            # 收集全量预测 (用于 DeLong 检验)
            all_prob_fusion[te_idx] += prob_fusion
            count_fusion[te_idx] += 1

    # 平均各 fold 的预测 (每样本被预测 3 次, 来自 3 seeds)
    all_prob_fusion = all_prob_fusion / np.maximum(count_fusion, 1)

    auc_arr = np.array(all_auc)
    f1_arr = np.array(all_f1)
    auc_mean = float(auc_arr.mean())
    auc_std = float(auc_arr.std(ddof=1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))
    f1_mean = float(f1_arr.mean())
    f1_std = float(f1_arr.std(ddof=1))
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))

    return {
        "strategy": strategy_name,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "n_evaluations": len(all_auc),
        "fold_details": fold_details,
        "full_prob": all_prob_fusion,
    }


def _run_v2(out_path: Path | None) -> dict[str, Any]:
    """v2 完整评估 (与 m4_fusion_retrain_v2.py 逐句同构)."""
    cfg = VARIANTS["v2"]
    start_time = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 60)
    logger.info("M4 融合重训 (v2) - 启动")
    logger.info("=" * 60)

    df = pd.read_csv(DATA_PATH)
    logger.info("数据加载: %d 样本, pos_rate=%.2f%%", len(df), df[TARGET_COL].mean() * 100)

    X_structured, X_text, X_combined, explained_variance = prepare_xy_v2(df, cfg)
    y = df[TARGET_COL].astype(int).values

    results = []
    prob_by_strategy = {}
    for name, _use_combined in V2_STRATEGIES:
        logger.info("--- 评估策略: %s ---", name)
        t0 = time.time()
        result = evaluate_strategy_v2(
            name,
            X_structured,
            X_text,
            y,
            X_combined,
            c_structured=cfg.c_structured,
            c_text=cfg.c_text,
        )
        result["eval_time_s"] = round(time.time() - t0, 1)
        results.append(result)
        prob_by_strategy[name] = result.pop("full_prob")

    single_aucs = {
        r["strategy"]: r["auc_mean"] for r in results if "only" in r["strategy"]
    }
    best_single_name = max(single_aucs, key=single_aucs.get)
    best_single_auc = single_aucs[best_single_name]

    fusion_aucs = {
        r["strategy"]: r["auc_mean"] for r in results if "only" not in r["strategy"]
    }
    best_fusion_name = max(fusion_aucs, key=fusion_aucs.get)
    best_fusion_result = next(r for r in results if r["strategy"] == best_fusion_name)
    fusion_auc = best_fusion_result["auc_mean"]
    auc_lift = fusion_auc - best_single_auc

    z_score, p_value = delong_test(
        y, prob_by_strategy[best_fusion_name], prob_by_strategy[best_single_name]
    )

    summary = {
        "experiment_id": f"m4_fusion_retrain_v2_{timestamp}",
        "task": "M4_fusion_retrain_phase2_v2",
        "version": "v2",
        "v1_failure_reason": (
            "structured only used gad7_score (1 dim), "
            "text BERT 768 dim overfitted on 1275 samples"
        ),
        "v2_improvements": [
            "structured: 1 → 10 features (gad7 + behavioral + lexical)",
            "text: BERT 768 → PCA 50 dim (avoid overfitting)",
            "new strategies: optimized_weighted, early_fusion, xgb_meta",
            "stacking meta-features: 4 → 8 (add quadratic + extrema)",
            "text modality C: 0.5 → 0.1 (stronger regularization)",
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_samples": len(df),
        "structured_features": STRUCTURED_FEATURES_V2,
        "pca_components": PCA_N_COMPONENTS_V2,
        "pca_explained_variance": explained_variance,
        "strategies": [{k: v for k, v in r.items()} for r in results],
        "best_single_modality": best_single_name,
        "best_single_auc": best_single_auc,
        "best_fusion_strategy": best_fusion_name,
        "fusion_auc": fusion_auc,
        "fusion_auc_ci95": best_fusion_result["auc_ci95"],
        "auc_lift": auc_lift,
        "delong_z": z_score,
        "delong_p": p_value,
        "meets_auc_lift_target": auc_lift >= TARGET_AUC_LIFT,
        "meets_delong_target": p_value < DELONG_P_THRESHOLD,
        "all_targets_met": auc_lift >= TARGET_AUC_LIFT and p_value < DELONG_P_THRESHOLD,
        "total_time_s": round(time.time() - start_time, 1),
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        logger.info("结果已保存: %s", out_path)

    return summary


V3_STRATEGIES: list[tuple[str, bool]] = [
    # (名称, 是否早融合数据集); 顺序与原脚本 strategies 列表逐一对应
    ("structured_only", False),
    ("text_only", False),
    ("lexical_only", False),
    ("static_weighted_3", False),
    ("trimodal_optimized", False),
    ("early_fusion_3", True),
    ("trimodal_stacking", False),
]


def _run_v3(out_path: Path | None) -> dict[str, Any]:
    """v3 完整评估 (与 m4_fusion_retrain_v3.py 逐句同构).

    与原脚本的差异仅限落盘方式: 原脚本写 EXPERIMENTS_DIR/<exp_id>.json 并在
    __main__ 里调用 register_training_job; lib 改写 --out 指定路径。
    原脚本 all_targets_met 分支会保存 pickle 产物, 但该分支不影响 summary JSON,
    且基线运行结果为 auc_lift 目标未达 (all_targets_met=False), 故不移植。
    """
    cfg = VARIANTS["v3"]
    start_time = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 60)
    logger.info("M4 融合重训 v3 (三模态融合) - 启动")
    logger.info("=" * 60)

    df = pd.read_csv(DATA_PATH)
    logger.info("数据加载: %d 样本, pos_rate=%.2f%%", len(df), df[TARGET_COL].mean() * 100)

    X_structured, X_text_pca, X_lexical, X_combined, explained_variance = (
        prepare_xy_v3(df, cfg)
    )
    y = df[TARGET_COL].astype(int).values

    results = []
    prob_by_strategy = {}
    for name, _use_combined in V3_STRATEGIES:
        logger.info("--- 评估策略: %s ---", name)
        t0 = time.time()
        result = evaluate_strategy_v3(name, X_structured, X_text_pca, X_lexical, y, cfg, X_combined)
        result["eval_time_s"] = round(time.time() - t0, 1)
        logger.info(
            "[%s] AUC=%.4f±%.4f (CI: %.4f~%.4f) F1=%.4f  [%.1fs]",
            name, result["auc_mean"], result["auc_std"],
            result["auc_ci_lower"], result["auc_ci_upper"],
            result["f1_mean"], result["eval_time_s"],
        )
        results.append(result)
        prob_by_strategy[name] = result.pop("full_prob")

    # 最优单模态
    single_aucs = {
        r["strategy"]: r["auc_mean"]
        for r in results if "only" in r["strategy"]
    }
    best_single_name = max(single_aucs, key=single_aucs.get)
    best_single_auc = single_aucs[best_single_name]

    # 最优融合策略
    fusion_aucs = {
        r["strategy"]: r["auc_mean"]
        for r in results if "only" not in r["strategy"]
    }
    best_fusion_name = max(fusion_aucs, key=fusion_aucs.get)
    best_fusion_result = next(r for r in results if r["strategy"] == best_fusion_name)
    fusion_auc = best_fusion_result["auc_mean"]
    auc_lift = fusion_auc - best_single_auc

    z_score, p_value = delong_test(
        y, prob_by_strategy[best_fusion_name], prob_by_strategy[best_single_name]
    )

    summary = {
        "experiment_id": f"m4_fusion_retrain_v3_{timestamp}",
        "task": "M4_fusion_retrain_phase2_v3",
        "version": "v3",
        "v2_failure_reason": "bimodal fusion lift +0.003, delong p=0.1171, both not met",
        "v3_improvements": [
            "trimodal: structured + text_bert + lexical (12 dim)",
            "trimodal optimized weight (3D grid search)",
            "trimodal stacking with 15 meta-features (3 probs + 6 pairwise + 1 triple + 3 abs_diff + 2 extrema)",
            "early_fusion_3: concat(structured, text_pca, lexical) → LogReg",
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_samples": len(df),
        "structured_features": STRUCTURED_FEATURES_V3,
        "lexical_features": LEXICAL_FEATURES_V3,
        "pca_components": PCA_N_COMPONENTS_V3,
        "pca_explained_variance": explained_variance,
        "strategies": [{k: v for k, v in r.items()} for r in results],
        "best_single_modality": best_single_name,
        "best_single_auc": best_single_auc,
        "best_fusion_strategy": best_fusion_name,
        "fusion_auc": fusion_auc,
        "fusion_auc_ci95": best_fusion_result["auc_ci95"],
        "auc_lift": auc_lift,
        "delong_z": z_score,
        "delong_p": p_value,
        "meets_auc_lift_target": auc_lift >= TARGET_AUC_LIFT,
        "meets_delong_target": p_value < DELONG_P_THRESHOLD,
        "all_targets_met": auc_lift >= TARGET_AUC_LIFT and p_value < DELONG_P_THRESHOLD,
        "total_time_s": round(time.time() - start_time, 1),
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        logger.info("结果已保存: %s", out_path)

    return summary


V_STACKING_FUSION_FNS: list[tuple[str, Any]] = [
    ("stacking", stacking_fusion),
    ("stacking_gbdt", stacking_gbdt_fusion),
    ("gated_weighted", gated_weighted_fusion),
]


def _run_v4(out_path: Path | None) -> dict[str, Any]:
    """v4 完整评估 (与 m4_fusion_retrain_v4.py 逐句同构).

    与原脚本的差异仅限落盘方式: 原脚本写 EXPERIMENTS_DIR/<exp_id>.json 并调用
    register_training_job; all_targets_met 为 True 时追加保存 pickle 产物——
    该分支发生在 summary 构建之后、不影响 JSON 内容, 且基线运行结果为未达标
    (False), 故均不移植。静态说明字段 version/v3_result/v4_improvements
    原样抄录 (v2 教训)。
    """
    cfg = VARIANTS["v4"]
    start_time = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 60)
    logger.info("M4 融合重训 v4 (LightGBM + 校准 + RF) - 启动")
    logger.info("=" * 60)

    df = pd.read_csv(DATA_PATH)
    logger.info("数据加载: %d 样本, pos_rate=%.2f%%", len(df), df[TARGET_COL].mean() * 100)

    X_structured, X_text_pca, X_lexical, y, explained_variance = prepare_xy_v4(df, cfg)

    results = []
    prob_by_strategy = {}
    for name in V4_STRATEGIES:
        logger.info("--- 评估策略: %s ---", name)
        t0 = time.time()
        result = evaluate_strategy_v4(name, X_structured, X_text_pca, X_lexical, y)
        result["eval_time_s"] = round(time.time() - t0, 1)
        logger.info(
            "[%s] AUC=%.4f±%.4f (CI: %.4f~%.4f) F1=%.4f  [%.1fs]",
            name, result["auc_mean"], result["auc_std"],
            result["auc_ci_lower"], result["auc_ci_upper"],
            result["f1_mean"], result["eval_time_s"],
        )
        results.append(result)
        prob_by_strategy[name] = result.pop("full_prob")

    single_aucs = {
        r["strategy"]: r["auc_mean"]
        for r in results if "only" in r["strategy"]
    }
    best_single_name = max(single_aucs, key=single_aucs.get)
    best_single_auc = single_aucs[best_single_name]

    fusion_aucs = {
        r["strategy"]: r["auc_mean"]
        for r in results if "only" not in r["strategy"]
    }
    best_fusion_name = max(fusion_aucs, key=fusion_aucs.get)
    best_fusion_result = next(r for r in results if r["strategy"] == best_fusion_name)
    fusion_auc = best_fusion_result["auc_mean"]
    auc_lift = fusion_auc - best_single_auc

    z_score, p_value = delong_test(
        y, prob_by_strategy[best_fusion_name], prob_by_strategy[best_single_name]
    )

    logger.info("=" * 60)
    logger.info("M4 融合重训 v4 最终结果:")
    logger.info("  最优单模态: %s AUC=%.4f", best_single_name, best_single_auc)
    logger.info("  最优融合策略: %s AUC=%.4f", best_fusion_name, fusion_auc)
    logger.info(
        "  AUC 增益=%+.4f target≥%.2f → %s",
        auc_lift, TARGET_AUC_LIFT,
        "✅" if auc_lift >= TARGET_AUC_LIFT else "❌",
    )
    logger.info(
        "  DeLong z=%.4f p=%.4f target<%.2f → %s",
        z_score, p_value, DELONG_P_THRESHOLD,
        "✅" if p_value < DELONG_P_THRESHOLD else "❌",
    )
    logger.info("=" * 60)

    summary = {
        "experiment_id": f"m4_fusion_retrain_v4_{timestamp}",
        "task": "M4_fusion_retrain_phase2_v4",
        "version": "v4",
        "v3_result": "trimodal_optimized AUC=0.9241, lift=+0.0054, delong_p=0.0086",
        "v4_improvements": [
            "LightGBM meta-learner (capture non-linear)",
            "isotonic calibration on base model probabilities",
            "RF base model option (capture non-linear)",
            "enhanced meta-features: 12 → 19 (add log-ratio, risk consistency, entropy)",
            "hybrid base: structured=LogReg, text=RF, lexical=LogReg",
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_samples": len(df),
        "structured_features": STRUCTURED_FEATURES_V4,
        "lexical_features": LEXICAL_FEATURES_V4,
        "pca_components": PCA_N_COMPONENTS_V4,
        "pca_explained_variance": explained_variance,
        "strategies": [{k: v for k, v in r.items()} for r in results],
        "best_single_modality": best_single_name,
        "best_single_auc": best_single_auc,
        "best_fusion_strategy": best_fusion_name,
        "fusion_auc": fusion_auc,
        "fusion_auc_ci95": best_fusion_result["auc_ci95"],
        "auc_lift": auc_lift,
        "delong_z": z_score,
        "delong_p": p_value,
        "meets_auc_lift_target": auc_lift >= TARGET_AUC_LIFT,
        "meets_delong_target": p_value < DELONG_P_THRESHOLD,
        "all_targets_met": auc_lift >= TARGET_AUC_LIFT and p_value < DELONG_P_THRESHOLD,
        "total_time_s": round(time.time() - start_time, 1),
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        logger.info("结果已保存: %s", out_path)

    return summary


def _run_stacking(out_path: Path | None) -> dict[str, Any]:
    """stacking 完整评估 (与 m4_fusion_stacking.py 逐句同构).

    与原脚本的差异仅限落盘方式 (不影响 summary JSON): 原脚本末尾训练最终模型并
    写 ARTIFACTS_DIR/fusion_model.pkl、metrics.json、m4_fusion_detail_<ts>.json、
    登记 training_jobs.json; 这些副作用与 DeLong 选优结果无关, 故不移植。
    特征完整性校验失败分支在当前数据下不可达, 以 raise 代替返回 error dict。
    静态说明字段 baseline/targets/data/acceptance 全结构原样抄录。
    """
    start_time = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 60)
    logger.info("M4 融合策略学习化 - 启动")
    logger.info("=" * 60)

    # 加载数据
    df = pd.read_csv(DATA_PATH)
    logger.info("数据加载: %d 样本, pos_rate=%.2f%%", len(df), df[TARGET_COL].mean() * 100)

    # 检查特征完整性
    missing_s = [c for c in QUESTIONNAIRE_FEATURES_STACKING if c not in df.columns]
    missing_t = [c for c in TEXT_FEATURES_STACKING if c not in df.columns]
    if missing_s or missing_t:
        raise ValueError(f"特征缺失: structured={missing_s}, text={missing_t}")

    X_structured = df[QUESTIONNAIRE_FEATURES_STACKING].values.astype(np.float32)
    X_text = df[TEXT_FEATURES_STACKING].values.astype(np.float32)
    y = df[TARGET_COL].astype(int).values

    # NaN 处理 (中位数填充)
    for arr, name in [(X_structured, "structured"), (X_text, "text")]:
        col_medians = np.nanmedian(arr, axis=0)
        nan_mask = np.isnan(arr)
        if nan_mask.sum() > 0:
            arr[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])
            logger.info("[%s] 填充 %d 个 NaN 值", name, nan_mask.sum())

    # === 评估各策略 ===
    strategies = [
        ("structured_only", None),
        ("text_only", None),
        ("static_weighted", None),
        ("stacking", stacking_fusion),
        ("stacking_gbdt", stacking_gbdt_fusion),
        ("gated_weighted", gated_weighted_fusion),
    ]

    results = []
    for name, fn in strategies:
        logger.info("--- 评估策略: %s ---", name)
        t0 = time.time()
        result = evaluate_strategy_stacking(name, fn, X_structured, X_text, y)
        result["eval_time_s"] = round(time.time() - t0, 1)
        logger.info(
            "[%s] AUC=%.4f±%.4f (CI: %.4f~%.4f) F1=%.4f±%.4f  [%.1fs]",
            name, result["auc_mean"], result["auc_std"],
            result["auc_ci_lower"], result["auc_ci_upper"],
            result["f1_mean"], result["f1_std"],
            result["eval_time_s"],
        )
        results.append(result)

    # === 找最优单模态 ===
    single_modal_results = [
        r for r in results
        if r["strategy"] in ("structured_only", "text_only")
    ]
    best_single = max(single_modal_results, key=lambda r: r["auc_mean"])
    logger.info(
        "最优单模态: %s (AUC=%.4f)",
        best_single["strategy"], best_single["auc_mean"],
    )

    # === DeLong 检验: 融合 vs 最优单模态 (OOF) ===
    logger.info("--- DeLong 检验: 融合 vs 最优单模态 (OOF) ---")
    prob_s_oof_full = generate_oof_predictions(X_structured, y, train_structured_model, 42)
    prob_t_oof_full = generate_oof_predictions(X_text, y, train_text_model, 42)

    best_single_prob = (
        prob_s_oof_full if best_single["strategy"] == "structured_only"
        else prob_t_oof_full
    )

    delong_results: dict[str, dict[str, Any]] = {}
    for fusion_name, fusion_fn in V_STACKING_FUSION_FNS:
        # 元学习器在 OOF 上训练, 也在 OOF 上预测 (用于 DeLong)
        prob_fusion, _ = fusion_fn(
            prob_s_oof_full, prob_t_oof_full, y,
            prob_s_oof_full, prob_t_oof_full, 42,
        )
        z, p = delong_test(y, prob_fusion, best_single_prob)
        auc_fusion = float(roc_auc_score(y, prob_fusion))
        auc_single = float(roc_auc_score(y, best_single_prob))
        lift = auc_fusion - auc_single
        delong_results[fusion_name] = {
            "auc_fusion": auc_fusion,
            "auc_best_single": auc_single,
            "auc_lift": lift,
            "delong_z": z,
            "delong_p_value": p,
            "meets_lift_target": lift >= STACKING_TARGET_AUC_LIFT,
            "meets_significance": p < DELONG_P_THRESHOLD,
        }
        logger.info(
            "[%s vs %s] AUC lift=%.4f, DeLong z=%.4f, p=%.4f %s",
            fusion_name, best_single["strategy"],
            lift, z, p,
            "✓" if (lift >= STACKING_TARGET_AUC_LIFT and p < DELONG_P_THRESHOLD) else "✗",
        )

    # === 选择最佳融合策略 ===
    fusion_results = [
        r for r in results
        if r["strategy"] in ("stacking", "stacking_gbdt", "gated_weighted")
    ]
    best_fusion = max(fusion_results, key=lambda r: r["auc_mean"])
    best_fusion_name = best_fusion["strategy"]
    auc_lift_vs_best_single = best_fusion["auc_mean"] - best_single["auc_mean"]

    # 基于 DeLong OOF 结果找最佳显著性达标策略
    delong_qualified = [
        (name, d) for name, d in delong_results.items()
        if d["meets_significance"] and d["meets_lift_target"]
    ]
    if delong_qualified:
        best_delong_name, best_delong = max(delong_qualified, key=lambda x: x[1]["auc_lift"])
        logger.info(
            "DeLong 达标最佳策略: %s (OOF lift=+%.4f, p=%.4f)",
            best_delong_name, best_delong["auc_lift"], best_delong["delong_p_value"],
        )
    else:
        best_delong_name = None
        best_delong = max(delong_results.values(), key=lambda x: x["auc_lift"])

    # === 汇总报告 ===
    summary = {
        "experiment_id": f"m4_fusion_{timestamp}",
        "task": "M4 融合策略学习化",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline": {
            "static_weights": STACKING_STATIC_WEIGHTS,
            "production_weights": {"structured": 0.55, "text": 0.30, "physiological": 0.15},
        },
        "targets": {
            "auc_lift": STACKING_TARGET_AUC_LIFT,
            "delong_p": DELONG_P_THRESHOLD,
        },
        "data": {
            "n_samples": len(df),
            "pos_rate": float(y.mean()),
            "structured_features": QUESTIONNAIRE_FEATURES_STACKING,
            "text_features": TEXT_FEATURES_STACKING,
        },
        "cv_results": [
            {k: v for k, v in r.items() if k != "fold_details"} for r in results
        ],
        "best_single_modality": {
            "strategy": best_single["strategy"],
            "auc_mean": best_single["auc_mean"],
        },
        "best_fusion": {
            "strategy": best_fusion_name,
            "auc_mean": best_fusion["auc_mean"],
            "auc_lift_vs_best_single": auc_lift_vs_best_single,
        },
        "delong_tests": delong_results,
        "acceptance": {
            "cv_auc_lift": auc_lift_vs_best_single,
            "cv_meets_lift_target": auc_lift_vs_best_single >= STACKING_TARGET_AUC_LIFT,
            "delong_best_strategy": best_delong_name,
            "delong_best_lift": best_delong["auc_lift"],
            "delong_best_p_value": best_delong["delong_p_value"],
            "delong_meets_lift_target": best_delong["meets_lift_target"],
            "delong_meets_significance": best_delong["meets_significance"],
            "all_passed": (
                best_delong["meets_lift_target"]
                and best_delong["meets_significance"]
            ),
        },
        "total_time_s": round(time.time() - start_time, 1),
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        logger.info("实验结果已保存: %s", out_path)

    return summary


def run_variant(variant: str, out_path: Path | None = None) -> dict[str, Any]:
    """运行指定变体完整评估并落盘摘要."""
    if variant == "v4":
        return _run_v4(out_path)
    if variant == "stacking":
        return _run_stacking(out_path)
    if variant == "v3":
        return _run_v3(out_path)
    if variant == "v2":
        return _run_v2(out_path)

    cfg = VARIANTS[variant]
    start_time = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 60)
    logger.info("M4 融合重训 (%s) - 启动", variant)
    logger.info("=" * 60)

    df = pd.read_csv(DATA_PATH)
    logger.info("数据加载: %d 样本, pos_rate=%.2f%%", len(df), df[TARGET_COL].mean() * 100)

    X_structured, X_text, y = prepare_xy_v1(df, cfg)
    logger.info("BERT embedding 加载完成")

    results = []
    prob_by_strategy = {}
    # FIX-RF1-REG1：策略清单改用模块级常量（子代理重构移除了 VariantConfig.strategies
    # 字段导致 v1 路径 AttributeError；保险重跑捕获后收敛为常量，消除对字段的隐式依赖）
    v1_strategies = V1_STRATEGIES
    for name in v1_strategies:
        logger.info("--- 评估策略: %s ---", name)
        t0 = time.time()
        result = evaluate_strategy(name, X_structured, X_text, y, cfg)
        result["eval_time_s"] = round(time.time() - t0, 1)
        logger.info(
            "[%s] AUC=%.4f±%.4f (CI: %.4f~%.4f) F1=%.4f  [%.1fs]",
            name,
            result["auc_mean"],
            result["auc_std"],
            result["auc_ci_lower"],
            result["auc_ci_upper"],
            result["f1_mean"],
            result["eval_time_s"],
        )
        results.append(result)
        prob_by_strategy[name] = result.pop("full_prob")

    single_aucs = {
        r["strategy"]: r["auc_mean"] for r in results if "only" in r["strategy"]
    }
    best_single_name = max(single_aucs, key=single_aucs.get)
    best_single_auc = single_aucs[best_single_name]

    stacking_result = next(r for r in results if r["strategy"] == "stacking")
    fusion_auc = stacking_result["auc_mean"]
    auc_lift = fusion_auc - best_single_auc

    z_score, p_value = delong_test(
        y, prob_by_strategy["stacking"], prob_by_strategy[best_single_name]
    )

    summary = {
        "experiment_id": f"m4_fusion_{variant}_{timestamp}",
        "task": f"M4_fusion_retrain_{variant}",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_samples": len(df),
        "strategies": [{k: v for k, v in r.items()} for r in results],
        "best_single_modality": best_single_name,
        "best_single_auc": best_single_auc,
        "fusion_auc": fusion_auc,
        "fusion_auc_ci95": stacking_result["auc_ci95"],
        "auc_lift": auc_lift,
        "delong_z": z_score,
        "delong_p": p_value,
        "meets_auc_lift_target": auc_lift >= TARGET_AUC_LIFT,
        "meets_delong_target": p_value < DELONG_P_THRESHOLD,
        "all_targets_met": auc_lift >= TARGET_AUC_LIFT and p_value < DELONG_P_THRESHOLD,
        "total_time_s": round(time.time() - start_time, 1),
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        logger.info("结果已保存: %s", out_path)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="M4 融合管线统一入口 (R-F1)")
    parser.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    parser.add_argument("--out", type=Path, default=None, help="结果 JSON 输出路径")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [M4-Fusion] %(message)s")

    summary = run_variant(args.variant, args.out)
    print("\n" + "=" * 60)
    if args.variant == "stacking":
        bs = summary["best_single_modality"]
        bf = summary["best_fusion"]
        acc = summary["acceptance"]
        print(
            f"[{args.variant}] 最优单模态={bs['strategy']} "
            f"AUC={bs['auc_mean']:.4f} | "
            f"Best fusion AUC={bf['auc_mean']:.4f} | "
            f"DeLong 最佳={acc['delong_best_strategy']} "
            f"(lift={acc['delong_best_lift']:+.4f}, "
            f"p={acc['delong_best_p_value']:.4f})"
        )
    else:
        print(
            f"[{args.variant}] 最优单模态={summary['best_single_modality']} "
            f"AUC={summary['best_single_auc']:.4f} | "
            f"Fusion AUC={summary['fusion_auc']:.4f} | "
            f"DeLong p={summary['delong_p']:.4f}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
