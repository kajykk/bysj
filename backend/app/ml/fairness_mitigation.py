"""ROUND_16 (P1-3)：公平性**缓解**选项（与评估分账，均未启用）.

纪律（ROUND_16 新增铁律①「评估与缓解分账」）：

- **评估**（量化组间差距）在 ``app/ml/model_validation.py::compute_fairness_metrics``，
  已随生产报告链路输出 per-group 指标与 TPR/FPR/机会均等差；
- **缓解**（改变判定以缩小差距）只在**本模块**，且两个选项全部标记
  「建议、未启用」（``status = "recommended_not_enabled"``）——接入需单独
  评审（涉及判定语义与性能权衡），评审材料必须包含本模块返回的**代价读数**。

为什么分账：把"已评估"说成"已缓解"是用含糊表述掩盖差距；反过来，不评估
就上缓解则是没有读数的盲目调参。两条路都堵死。

两个可选项：

1. :func:`suggest_group_thresholds` —— **阈值后处理（post-processing）**：
   按组分别选工作点以缩小 TPR/FPR 差。
   代价：同分不同组 ⇒ 不同等级，需产品与合理论证；总体指标通常让位于组间公平。
2. :func:`suggest_sample_reweights` —— **重加权（reweighting）**：
   训练时按组/类频率补偿（Kamiran & Calders 口径）。
   代价：只对**重训**模型有效，且改变校准分布；当前基线模型不重训则无意义。
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: 本模块所有产出的统一状态标记：建议、未启用。
STATUS_RECOMMENDED_NOT_ENABLED = "recommended_not_enabled"


def suggest_group_thresholds(
    y_true: np.ndarray,
    y_score: np.ndarray,
    groups: np.ndarray,
    min_group_size: int = 30,
    grid: np.ndarray | None = None,
    criterion: str = "youden",
) -> dict[str, Any]:
    """阈值后处理建议：按组分别选工作点（**未启用**）.

    对每个达标组（>= min_group_size）在 grid 上按 Youden J 或 F1 选组内最优
    阈值；同时给出**统一阈值**基线（全体 Youden J 最优）以便对比代价。

    Returns:
        ``{"status": ..., "criterion": ..., "per_group_thresholds": {...},
        "uniform_threshold": float, "cost": {...}}``

        ``cost`` 汇总采用组阈值后的总体读数变化（accuracy / balanced_accuracy /
        f1 / tpr_gap / fpr_gap），与统一阈值基线对照——**不得只报改善不报代价**。
    """
    from sklearn.metrics import balanced_accuracy_score, f1_score

    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype=float)
    groups = np.asarray(groups)
    if grid is None:
        grid = np.round(np.arange(0.05, 1.0, 0.05), 4)
    grid = np.asarray(grid, dtype=float)
    if criterion not in {"youden", "f1"}:
        raise ValueError(f"criterion 只支持 'youden' / 'f1'，得到 {criterion!r}")

    def _group_metric(y: np.ndarray, p: np.ndarray, t: float) -> float:
        pred = (p >= t).astype(int)
        if criterion == "f1":
            return float(f1_score(y, pred, zero_division=0))
        # Youden J = TPR + TNR − 1
        tp = float(np.sum((y == 1) & (pred == 1)))
        fn = float(np.sum((y == 1) & (pred == 0)))
        tn = float(np.sum((y == 0) & (pred == 0)))
        fp = float(np.sum((y == 0) & (pred == 1)))
        tpr = tp / (tp + fn) if (tp + fn) else 0.0
        tnr = tn / (tn + fp) if (tn + fp) else 0.0
        return tpr + tnr - 1.0

    unique_groups = np.unique(groups)
    per_group_thresholds: dict[str, float] = {}
    suppressed: list[str] = []
    for g in unique_groups:
        mask = groups == g
        if int(np.sum(mask)) < min_group_size or len(np.unique(y_true[mask])) < 2:
            suppressed.append(str(g))
            continue
        y_g, p_g = y_true[mask], y_score[mask]
        best_t, best_v = float(grid[0]), -np.inf
        for t in grid:
            v = _group_metric(y_g, p_g, float(t))
            if v > best_v:
                best_v, best_t = v, float(t)
        per_group_thresholds[str(g)] = round(best_t, 4)

    # 统一阈值基线（全体）
    uniform_t, best_v = float(grid[0]), -np.inf
    for t in grid:
        v = _group_metric(y_true, y_score, float(t))
        if v > best_v:
            best_v, uniform_t = v, float(t)
    uniform_t = round(uniform_t, 4)

    def _overall(pred: np.ndarray) -> dict[str, Any]:
        tp = float(np.sum((y_true == 1) & (pred == 1)))
        fn = float(np.sum((y_true == 1) & (pred == 0)))
        tn = float(np.sum((y_true == 0) & (pred == 0)))
        fp = float(np.sum((y_true == 0) & (pred == 1)))
        tpr = tp / (tp + fn) if (tp + fn) else 0.0
        fpr = fp / (tn + fp) if (tn + fp) else 0.0
        return {
            "accuracy": round(float(np.mean(pred == y_true)), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y_true, pred)), 4),
            "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
            "tpr": round(tpr, 4),
            "fpr": round(fpr, 4),
        }

    pred_uniform = (y_score >= uniform_t).astype(int)
    pred_grouped = np.zeros(len(y_true), dtype=int)
    for g in unique_groups:
        mask = groups == g
        t = per_group_thresholds.get(str(g))
        if t is None:
            # 被压制组（小样本/单类）沿用统一阈值，不输出其单独读数
            pred_grouped[mask] = (y_score[mask] >= uniform_t).astype(int)
        else:
            pred_grouped[mask] = (y_score[mask] >= t).astype(int)

    uni, grp = _overall(pred_uniform), _overall(pred_grouped)
    # 组间差距（TPR/FPR）在达标题组内、按组阈值计算
    group_tprs: dict[str, float] = {}
    group_fprs: dict[str, float] = {}
    group_value_by_key = {str(u): u for u in unique_groups}
    for g_key, t in per_group_thresholds.items():
        mask = groups == group_value_by_key[g_key]
        y_g = y_true[mask]
        pred_g = (y_score[mask] >= t).astype(int)
        pos = y_g == 1
        neg = y_g == 0
        if pos.any():
            group_tprs[g_key] = round(float(np.mean(pred_g[pos])), 4)
        if neg.any():
            group_fprs[g_key] = round(float(1 - np.mean(pred_g[neg])), 4)

    cost = {
        "uniform_baseline": uni,
        "group_thresholds_applied": grp,
        "accuracy_cost": round(uni["accuracy"] - grp["accuracy"], 4),
        "f1_cost": round(uni["f1"] - grp["f1"], 4),
        "tpr_gap_grouped": (
            round(max(group_tprs.values()) - min(group_tprs.values()), 4)
            if len(group_tprs) >= 2
            else None
        ),
        "fpr_gap_grouped": (
            round(max(group_fprs.values()) - min(group_fprs.values()), 4)
            if len(group_fprs) >= 2
            else None
        ),
    }

    return {
        "status": STATUS_RECOMMENDED_NOT_ENABLED,
        "criterion": criterion,
        "per_group_thresholds": per_group_thresholds,
        "suppressed_groups": suppressed,
        "uniform_threshold": uniform_t,
        "min_group_size": min_group_size,
        "cost": cost,
        "caveats": [
            "同分不同组 ⇒ 不同等级，需产品与合理论证后方可启用",
            "小样本/单类组沿用统一阈值，且不输出其单独读数（min_group_size 保护）",
            "代价读数必须连同建议一起评审；只报改善不报代价视为无效建议",
        ],
    }


def suggest_sample_reweights(
    y: np.ndarray,
    groups: np.ndarray,
) -> dict[str, Any]:
    """重加权建议：训练时按组 × 类频率补偿（Kamiran & Calders 口径，**未启用**）.

    weight(g, c) = (N / (G · n_g)) · (N / (C · n_{g,c})) 的等价简化：
    ``w(g) = N / (G · n_g)`` 与 ``w(c) = N / (C · n_c)`` 相乘。
    仅对**重训**模型有意义；当前基线模型不重训 ⇒ 该建议不可直接套用。

    Returns:
        ``{"status": ..., "group_weights": {...}, "class_weights": {...},
        "combined_example": {(g, c): w}, "cost_note": [...]}``
    """
    y = np.asarray(y).astype(int)
    groups = np.asarray(groups)
    n = len(y)
    if n == 0:
        raise ValueError("suggest_sample_reweights 需要非空样本")

    g_unique = np.unique(groups)
    c_unique = np.unique(y)
    group_weights = {str(g): round(n / (len(g_unique) * int(np.sum(groups == g))), 6) for g in g_unique}
    class_weights = {int(c): round(n / (len(c_unique) * int(np.sum(y == c))), 6) for c in c_unique}
    combined = {
        f"{g}|{c}": round(group_weights[str(g)] * class_weights[int(c)], 6)
        for g in g_unique
        for c in c_unique
    }
    return {
        "status": STATUS_RECOMMENDED_NOT_ENABLED,
        "group_weights": group_weights,
        "class_weights": {str(k): v for k, v in class_weights.items()},
        "combined_example": combined,
        "cost_note": [
            "只对重训模型有效；不重训则无意义（当前基线模型不适用）",
            "改变训练分布 ⇒ 改变校准分布，需重估 DCA/ECE 后另行评审",
        ],
    }
