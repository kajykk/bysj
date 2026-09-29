"""M4 融合模型 v3 产物保存脚本.

v3 trimodal_optimized 是 4 次实验中的最优结果:
  - fusion_auc=0.9241 (best)
  - delong_p=0.0086 (< 0.05, 统计显著)
  - auc_lift=+0.0054 (未达 +0.03 目标, 归档为数据天花板)

本脚本训练 v3 全量模型并保存产物到 models/artifacts/fusion_m4_retrain_v3/
用于阶段三金丝雀部署.

Usage:
    python scripts/m4_fusion_v3_save_artifacts.py
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M4-v3-Save] %(message)s")
logger = logging.getLogger("M4-v3-Save")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "lite_features.csv"
BERT_CACHE_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "bert_embeddings_n1275.npy"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "fusion_m4_retrain_v3"

# R-F1: 特征常量唯一来源收敛至统一管线库（消除与评估管线的漂移面）
import sys

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scripts.lib.fusion_pipeline import (
    LEXICAL_FEATURES_V3 as LEXICAL_FEATURES,
)
from scripts.lib.fusion_pipeline import (
    PCA_N_COMPONENTS_V3 as PCA_N_COMPONENTS,
)
from scripts.lib.fusion_pipeline import (
    STRUCTURED_FEATURES_V3 as STRUCTURED_FEATURES,
)
from scripts.lib.fusion_pipeline import (
    TARGET_COL,
)

SEED = 42


def train_logreg_final(X: np.ndarray, y: np.ndarray, C: float = 1.0) -> LogisticRegression:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = LogisticRegression(
        C=C, class_weight="balanced", max_iter=2000,
        random_state=SEED, solver="lbfgs",
    )
    model.fit(X_scaled, y)
    model.scaler_ = scaler
    return model


def main() -> None:
    logger.info("=" * 60)
    logger.info("M4 融合 v3 产物保存 (用于阶段三部署)")
    logger.info("=" * 60)

    df = pd.read_csv(DATA_PATH)
    bert_emb = np.load(BERT_CACHE_PATH)
    assert len(df) == bert_emb.shape[0]

    X_structured = df[STRUCTURED_FEATURES].values.astype(np.float32)
    X_lexical = df[LEXICAL_FEATURES].values.astype(np.float32)
    pca = PCA(n_components=PCA_N_COMPONENTS, random_state=SEED)
    X_text_pca = pca.fit_transform(bert_emb.astype(np.float32))
    y = df[TARGET_COL].astype(int).values

    # NaN 处理
    for arr in [X_structured, X_text_pca, X_lexical]:
        col_medians = np.nanmedian(arr, axis=0)
        nan_mask = np.isnan(arr)
        if nan_mask.sum() > 0:
            arr[nan_mask] = np.take(col_medians, np.where(nan_mask)[1])

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 保存 PCA
    with open(ARTIFACTS_DIR / "bert_pca.pkl", "wb") as f:
        pickle.dump(pca, f)
    logger.info("BERT PCA 已保存 (n_components=%d, variance=%.4f)",
                PCA_N_COMPONENTS, float(pca.explained_variance_ratio_.sum()))

    # 2. 训练并保存三个基模型
    m_s = train_logreg_final(X_structured, y, C=1.0)
    m_t = train_logreg_final(X_text_pca, y, C=0.1)
    m_l = train_logreg_final(X_lexical, y, C=0.5)
    with open(ARTIFACTS_DIR / "structured_clf.pkl", "wb") as f:
        pickle.dump(m_s, f)
    with open(ARTIFACTS_DIR / "text_clf.pkl", "wb") as f:
        pickle.dump(m_t, f)
    with open(ARTIFACTS_DIR / "lexical_clf.pkl", "wb") as f:
        pickle.dump(m_l, f)
    logger.info("三个基模型已保存 (structured/text/lexical)")

    # 3. 计算 OOF 概率 (用于找最优权重)
    from sklearn.model_selection import StratifiedKFold
    N_FOLDS = 5
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    prob_s_oof = np.zeros(len(y))
    prob_t_oof = np.zeros(len(y))
    prob_l_oof = np.zeros(len(y))
    for tr_idx, va_idx in skf.split(X_structured, y):
        # structured
        scaler_s = StandardScaler()
        X_tr_s = scaler_s.fit_transform(X_structured[tr_idx])
        X_va_s = scaler_s.transform(X_structured[va_idx])
        m = LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000,
                               random_state=SEED, solver="lbfgs")
        m.fit(X_tr_s, y[tr_idx])
        prob_s_oof[va_idx] = m.predict_proba(X_va_s)[:, 1]
        # text
        scaler_t = StandardScaler()
        X_tr_t = scaler_t.fit_transform(X_text_pca[tr_idx])
        X_va_t = scaler_t.transform(X_text_pca[va_idx])
        m = LogisticRegression(C=0.1, class_weight="balanced", max_iter=2000,
                               random_state=SEED, solver="lbfgs")
        m.fit(X_tr_t, y[tr_idx])
        prob_t_oof[va_idx] = m.predict_proba(X_va_t)[:, 1]
        # lexical
        scaler_l = StandardScaler()
        X_tr_l = scaler_l.fit_transform(X_lexical[tr_idx])
        X_va_l = scaler_l.transform(X_lexical[va_idx])
        m = LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000,
                               random_state=SEED, solver="lbfgs")
        m.fit(X_tr_l, y[tr_idx])
        prob_l_oof[va_idx] = m.predict_proba(X_va_l)[:, 1]

    # 4. 网格搜索最优三模态权重
    from itertools import product as iter_product

    from sklearn.metrics import roc_auc_score
    best_ws, best_auc = (1.0, 0.0, 0.0), 0.0
    for ws, wt, wl in iter_product(np.arange(0.0, 1.01, 0.05), repeat=3):
        if abs(ws + wt + wl - 1.0) > 0.005:
            continue
        blended = ws * prob_s_oof + wt * prob_t_oof + wl * prob_l_oof
        try:
            auc = roc_auc_score(y, blended)
        except ValueError:
            continue
        if auc > best_auc:
            best_auc = auc
            best_ws = (round(float(ws), 4), round(float(wt), 4), round(float(wl), 4))
    logger.info("最优权重: structured=%.4f, text=%.4f, lexical=%.4f (OOF AUC=%.4f)",
                best_ws[0], best_ws[1], best_ws[2], best_auc)

    # 5. 保存配置
    config = {
        "strategy": "trimodal_optimized",
        "version": "v3",
        "structured_features": STRUCTURED_FEATURES,
        "lexical_features": LEXICAL_FEATURES,
        "pca_components": PCA_N_COMPONENTS,
        "pca_explained_variance": float(pca.explained_variance_ratio_.sum()),
        "weights": {
            "structured": best_ws[0],
            "text": best_ws[1],
            "lexical": best_ws[2],
        },
        "threshold": 0.5,
        "training_seed": SEED,
        "training_n_samples": len(df),
        "v3_metrics": {
            "best_single_modality": "structured_only",
            "best_single_auc": 0.9187,
            "fusion_auc": 0.9241,
            "auc_lift": 0.0054,
            "delong_p": 0.0086,
        },
        "data_ceiling_conclusion": {
            "reason": "1275 samples with 20.24% positive rate (258 positives), structured GAD-7 modality already AUC=0.9187, fusion lift limited to +0.0054",
            "target": "AUC lift >= 0.03",
            "actual": "AUC lift = +0.0054",
            "delong_significant": True,
            "archived": True,
        },
    }
    with open(ARTIFACTS_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.info("配置已保存: %s", ARTIFACTS_DIR / "config.json")

    print("\n" + "=" * 60)
    print("M4 融合 v3 产物保存完成:")
    print(f"  路径: {ARTIFACTS_DIR}")
    print("  策略: trimodal_optimized")
    print(f"  权重: structured={best_ws[0]:.4f}, text={best_ws[1]:.4f}, lexical={best_ws[2]:.4f}")
    print(f"  OOF AUC: {best_auc:.4f}")
    print("  阈值: 0.5")
    print("=" * 60)


if __name__ == "__main__":
    main()
