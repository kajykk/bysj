"""ROUND_16 (P1-2)：多模态融合增量消融能力.

缺口实证：融合 vs 单模态的**临床增量未量化**——`MODEL_REGISTRY.md` §3 把融合
标为"实验"。本模块提供**同队列**（common-cohort）口径的消融：

- 每个受试臂给出 AUROC 点估计 + bootstrap 置信区间；
- 融合 − 单模态的**配对** ΔAUROC（同一批样本上计算）点估计 + 95% CI；
- 连续型 NRI / IDI（category-free，无需选阈值即有定义）；
- 可选工作点对比：按**用户/被试分组**的交叉验证选阈值（训练折内选、
  测试折内评），落实"阈值只在训练折选"纪律；
- ``AblationResult.provenance`` 强制记录数据来源、样本量、分组方式、
  是否 in-sample——防"挑子集救正"。

设计红线（纪律）：
1. **ΔAUROC 只在同一队列上有意义**。不同数据集上的各模态读数不可相减；
   本项目三模态生产评估集互不相交（详见 P2_R16 报告的实证），因此
   ``run_ablation`` 从不自行拼接不同来源的分数，只消费调用方给定的同队列分数。
2. **CI 覆盖 0 必须如实报"无显著增量"**——``ci_covers_zero`` 字段由模块计算，
   报告方不得事后挑选子集救正。
3. 本模块**不接入任何生产预测路径**，只做离线评估。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def bootstrap_auc_ci(
    y_true: np.ndarray,
    scores: np.ndarray,
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> tuple[float, list[float], int]:
    """AUROC 点估计 + 分层 bootstrap 置信区间.

    Returns:
        ``(auc, [lower, upper], degenerate_samples)``——degenerate_samples 为重采样
        退化（单类）被剔除的次数，不静默丢弃。
    """
    from sklearn.metrics import roc_auc_score

    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    n = len(y_true)
    if n < 2 or len(np.unique(y_true)) < 2:
        return 0.5, [0.0, 0.0], 0
    auc = float(roc_auc_score(y_true, scores))

    rng = np.random.RandomState(random_state)
    boots: list[float] = []
    degenerate = 0
    pos_idx = np.where(y_true == 1)[0]
    neg_idx = np.where(y_true == 0)[0]
    for _ in range(n_bootstrap):
        # 分层重采样：保持正负比例，减少小样本退化
        p = rng.choice(pos_idx, size=len(pos_idx), replace=True)
        q = rng.choice(neg_idx, size=len(neg_idx), replace=True)
        idx = np.concatenate([p, q])
        if len(np.unique(y_true[idx])) < 2:
            degenerate += 1
            continue
        try:
            boots.append(roc_auc_score(y_true[idx], scores[idx]))
        except Exception:
            degenerate += 1
    if len(boots) < 10:
        return auc, [0.0, 0.0], degenerate
    alpha = (1 - confidence) / 2
    lo = float(np.percentile(boots, alpha * 100))
    hi = float(np.percentile(boots, (1 - alpha) * 100))
    return auc, [lo, hi], degenerate


def paired_delta_auc_ci(
    y_true: np.ndarray,
    scores_new: np.ndarray,
    scores_base: np.ndarray,
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> dict[str, Any]:
    """配对 ΔAUROC = AUC(new) − AUC(base) 的点估计 + CI（同一批样本上配对）.

    CI 覆盖 0 ⇒ ``ci_covers_zero=True``，调用方须如实报"无显著增量"。
    """
    from sklearn.metrics import roc_auc_score

    y_true = np.asarray(y_true).astype(int)
    scores_new = np.asarray(scores_new, dtype=float)
    scores_base = np.asarray(scores_base, dtype=float)
    if len(y_true) < 2 or len(np.unique(y_true)) < 2:
        return {
            "delta": 0.0,
            "ci": [0.0, 0.0],
            "ci_covers_zero": True,
            "n_bootstrap_valid": 0,
        }

    auc_new = float(roc_auc_score(y_true, scores_new))
    auc_base = float(roc_auc_score(y_true, scores_base))
    delta = auc_new - auc_base

    rng = np.random.RandomState(random_state)
    boots: list[float] = []
    pos_idx = np.where(y_true == 1)[0]
    neg_idx = np.where(y_true == 0)[0]
    n = len(y_true)
    for _ in range(n_bootstrap):
        # 成对重采样：两臂用同一套索引，保证配对结构
        idx = rng.choice(n, size=n, replace=True)
        if len(np.unique(y_true[idx])) < 2:
            continue
        # 不用 try/except 吞 roc_auc_score 失败：NaN/inf 输入会在上面
        # 106/107 行（同参数、未包裹）先行抛出；真走到这里才失败的输入不存在。
        # 且静默跳过 bootstrap 样本会腐蚀 CI（n_bootstrap_valid 降权），
        # 对离线科学分析工具，响亮失败才是正确语义。
        boots.append(
            float(roc_auc_score(y_true[idx], scores_new[idx]))
            - float(roc_auc_score(y_true[idx], scores_base[idx]))
        )
    if len(boots) < 10:
        return {
            "delta": round(delta, 4),
            "ci": [0.0, 0.0],
            "ci_covers_zero": True,
            "n_bootstrap_valid": len(boots),
        }
    alpha = (1 - confidence) / 2
    lo = float(np.percentile(boots, alpha * 100))
    hi = float(np.percentile(boots, (1 - alpha) * 100))
    return {
        "delta": round(delta, 4),
        "ci": [round(lo, 4), round(hi, 4)],
        "ci_covers_zero": bool(lo <= 0.0 <= hi),
        "n_bootstrap_valid": len(boots),
    }


def nri_continuous(y_true: np.ndarray, scores_new: np.ndarray, scores_base: np.ndarray) -> float:
    """连续型 NRI（无类别划分，Pencina 2008 口径）.

    NRI = E[Δp | y=1] − E[Δp | y=0]，Δp = p_new − p_base。
    """
    y_true = np.asarray(y_true).astype(int)
    diff = np.asarray(scores_new, dtype=float) - np.asarray(scores_base, dtype=float)
    if len(y_true) == 0:
        return 0.0
    if not np.any(y_true == 1) or not np.any(y_true == 0):
        return 0.0
    return float(np.mean(diff[y_true == 1]) - np.mean(diff[y_true == 0]))


def idi_continuous(y_true: np.ndarray, scores_new: np.ndarray, scores_base: np.ndarray) -> float:
    """连续型 IDI（Pencina 2008 口径）.

    IDI = (E[p_new|y=1] − E[p_base|y=1]) − (E[p_new|y=0] − E[p_base|y=0])，
    即新模型在"病例上提分、非病例上扣分"两个方向的改善净和。
    """
    y_true = np.asarray(y_true).astype(int)
    p_new = np.asarray(scores_new, dtype=float)
    p_base = np.asarray(scores_base, dtype=float)
    if not np.any(y_true == 1) or not np.any(y_true == 0):
        return 0.0
    improve_event = float(np.mean(p_new[y_true == 1]) - np.mean(p_base[y_true == 1]))
    improve_nonevent = float(np.mean(p_new[y_true == 0]) - np.mean(p_base[y_true == 0]))
    return float(improve_event - improve_nonevent)


def groupwise_kfold_indices(
    y_true: np.ndarray,
    groups: np.ndarray,
    n_splits: int = 5,
    random_state: int = 42,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """按用户/被试分组的分层 K 折（StratifiedGroupKFold 包装）.

    泄漏防线：同一 group 的所有样本必须同折（不得跨折）。本函数在返回前
    **实测校验**该性质，违反即抛错（宁可红，不可静默泄漏）。
    """
    from sklearn.model_selection import StratifiedGroupKFold

    y_true = np.asarray(y_true).astype(int)
    groups = np.asarray(groups)
    if len(np.unique(groups)) < n_splits:
        raise ValueError(f"分组数 {len(np.unique(groups))} < n_splits={n_splits}，无法按组分折")

    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    seen_groups: set[Any] = set()
    for tr, te in splitter.split(np.zeros(len(y_true)), y_true, groups=groups):
        train_groups = set(groups[tr].tolist())
        test_groups = set(groups[te].tolist())
        overlap = train_groups & test_groups
        if overlap:
            raise ValueError(
                f"分组泄漏：{len(overlap)} 个组同时出现在训练折与测试折（如 "
                f"{sorted(overlap, key=str)[:3]}）——StratifiedGroupKFold 不应产生此情况，"
                "请检查 groups 输入"
            )
        folds.append((tr, te))
    return folds


def _select_threshold_train_fold_only(
    y_train: np.ndarray,
    p_train: np.ndarray,
    grid: np.ndarray,
) -> float:
    """在训练折内按 F1 选阈值（绝不可接触测试折）."""
    from sklearn.metrics import f1_score

    best_t, best_f1 = float(grid[0]), -1.0
    for t in grid:
        f1 = float(f1_score(y_train, (p_train >= t).astype(int), zero_division=0))
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return best_t


def groupwise_oof_operating_metrics(
    y_true: np.ndarray,
    scores_by_arm: dict[str, np.ndarray],
    groups: np.ndarray,
    n_splits: int = 5,
    random_state: int = 42,
    grid: np.ndarray | None = None,
) -> dict[str, Any]:
    """分组 OOF 工作点对比：每个臂的阈值只在训练折选，OOF 指标在测试折汇.

    这是"阈值只在训练折选"纪律的可执行形态：对每一折，用**训练折**分数
    为该臂选一个 F1 最优阈值，再在测试折上累积预测，最后汇总 OOF
    accuracy / precision / recall / F1 / confusion_matrix。

    Args:
        y_true: 标签
        scores_by_arm: 臂名 → 分数（已按同队列对齐）
        groups: 用户/被试分组
        n_splits / random_state / grid: 折数 / 种子 / 阈值网格（默认 0.05~0.95）

    Returns:
        ``{"per_arm": {arm: {oof metrics + selected_thresholds + confusion_matrix}},
        "n_splits": ..., "grouping": "groupwise_kfold"}``
    """
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    y_true = np.asarray(y_true).astype(int)
    if grid is None:
        grid = np.round(np.arange(0.05, 1.0, 0.05), 4)
    grid = np.asarray(grid, dtype=float)

    folds = groupwise_kfold_indices(y_true, groups, n_splits=n_splits, random_state=random_state)

    per_arm: dict[str, Any] = {}
    for arm, scores in scores_by_arm.items():
        scores = np.asarray(scores, dtype=float)
        oof_pred = np.zeros(len(y_true), dtype=int)
        chosen: list[float] = []
        for tr, te in folds:
            t = _select_threshold_train_fold_only(y_true[tr], scores[tr], grid)
            chosen.append(t)
            oof_pred[te] = (scores[te] >= t).astype(int)
        cm = confusion_matrix(y_true, oof_pred)
        tn = fp = fn = tp = 0
        if cm.size == 4:
            tn, fp, fn, tp = cm.ravel()
        per_arm[arm] = {
            "accuracy": round(float(accuracy_score(y_true, oof_pred)), 4),
            "precision": round(float(precision_score(y_true, oof_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, oof_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_true, oof_pred, zero_division=0)), 4),
            "selected_thresholds": [round(t, 4) for t in chosen],
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        }
    return {"per_arm": per_arm, "n_splits": len(folds), "grouping": "groupwise_kfold"}


@dataclass
class AblationResult:
    """一次消融run的结构化结果（含 provenance 防挑救）."""

    arms: dict[str, dict[str, Any]] = field(default_factory=dict)
    delta_vs_base: dict[str, dict[str, Any]] = field(default_factory=dict)
    nri: float = 0.0
    idi: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arms": self.arms,
            "delta_vs_base": self.delta_vs_base,
            "nri": round(self.nri, 4),
            "idi": round(self.idi, 4),
            "provenance": self.provenance,
        }


def run_ablation(
    y_true: np.ndarray,
    arm_scores: dict[str, np.ndarray],
    *,
    base_arm: str = "structured",
    groups: np.ndarray | None = None,
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    random_state: int = 42,
    source: str = "unknown",
    in_sample: bool = True,
) -> AblationResult:
    """同队列消融主入口.

    Args:
        y_true: 标签
        arm_scores: 臂名 → 分数（必须同队列等长）
        base_arm: 参照臂（Δ = 其他臂 − base）
        groups: 用户/被试分组（None 时仅记录 "ungrouped"，并在 provenance 标注）
        n_bootstrap / confidence / random_state: bootstrap 参数
        source: 数据来源描述（必填意识：provenance 强制落档）
        in_sample: 分数是否为 in-sample（如在同一批场景上挑过权重）

    Returns:
        AblationResult（``delta_vs_base[*].ci_covers_zero`` 为 True 即"无显著增量"）
    """
    y_true = np.asarray(y_true).astype(int)
    if base_arm not in arm_scores:
        raise ValueError(f"base_arm={base_arm!r} 不在 arm_scores 中（可用：{sorted(arm_scores)}）")

    n = len(y_true)
    for arm, s in arm_scores.items():
        if len(s) != n:
            raise ValueError(f"臂 {arm!r} 长度 {len(s)} != y_true 长度 {n}")

    result = AblationResult()
    for arm, scores in arm_scores.items():
        auc, ci, degen = bootstrap_auc_ci(
            y_true, scores, n_bootstrap=n_bootstrap, confidence=confidence, random_state=random_state
        )
        result.arms[arm] = {
            "auc": round(auc, 4),
            "auc_ci": [round(ci[0], 4), round(ci[1], 4)],
            "n": n,
            "degenerate_samples": degen,
        }

    for arm, scores in arm_scores.items():
        if arm == base_arm:
            continue
        result.delta_vs_base[arm] = paired_delta_auc_ci(
            y_true,
            scores,
            arm_scores[base_arm],
            n_bootstrap=n_bootstrap,
            confidence=confidence,
            random_state=random_state,
        )

    # NRI/IDI 以"最像融合的那个臂"为新模型：多臂时取融合臂，否则取第一个非 base 臂
    fusion_like = "fusion" if "fusion" in arm_scores else next(
        (a for a in arm_scores if a != base_arm), None
    )
    if fusion_like is not None:
        result.nri = nri_continuous(y_true, arm_scores[fusion_like], arm_scores[base_arm])
        result.idi = idi_continuous(y_true, arm_scores[fusion_like], arm_scores[base_arm])

    result.provenance = {
        "source": source,
        "n": n,
        "positive_rate": round(float(np.mean(y_true)), 4),
        "base_arm": base_arm,
        "in_sample": bool(in_sample),
        "grouping": "by_user_group_kfold" if groups is not None else "ungrouped",
        "n_groups": int(len(np.unique(groups))) if groups is not None else None,
        "n_bootstrap": n_bootstrap,
        "confidence": confidence,
        "random_state": random_state,
    }
    return result
