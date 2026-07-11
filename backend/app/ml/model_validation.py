"""Phase 3 模型验证基础设施：临床指标 + 置信区间 + 公平性检查.

按 Phase 3 计划要求实现：
- 按风险层级报告 sensitivity、specificity、PPV、NPV、AUROC、校准度及置信区间
- 按性别、年级等允许且合规的群体检查偏差
- 不输出可重新识别的小样本切片（min_group_size 保护）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# 小样本保护：低于此数量的群体不输出指标，防止可重新识别
_DEFAULT_MIN_GROUP_SIZE = 30


@dataclass
class BinaryMetrics:
    """二分类模型的核心临床指标（含置信区间）."""

    sensitivity: float
    specificity: float
    ppv: float
    npv: float
    auc: float
    brier_score: float
    # 置信区间 [lower, upper]
    sensitivity_ci: list[float] = field(default_factory=list)
    specificity_ci: list[float] = field(default_factory=list)
    ppv_ci: list[float] = field(default_factory=list)
    npv_ci: list[float] = field(default_factory=list)
    auc_ci: list[float] = field(default_factory=list)
    # 混淆矩阵
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    # 标记
    auc_reliable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensitivity": round(self.sensitivity, 4),
            "specificity": round(self.specificity, 4),
            "ppv": round(self.ppv, 4),
            "npv": round(self.npv, 4),
            "auc": round(self.auc, 4),
            "brier_score": round(self.brier_score, 4),
            "sensitivity_ci": [round(v, 4) for v in self.sensitivity_ci],
            "specificity_ci": [round(v, 4) for v in self.specificity_ci],
            "ppv_ci": [round(v, 4) for v in self.ppv_ci],
            "npv_ci": [round(v, 4) for v in self.npv_ci],
            "auc_ci": [round(v, 4) for v in self.auc_ci],
            "confusion_matrix": {"tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn},
            "auc_reliable": self.auc_reliable,
        }


def _wilson_ci(successes: int, total: int, confidence: float = 0.95) -> list[float]:
    """Wilson score 置信区间（适用于比例指标）.

    比正态近似更稳健，在 sample size 较小或比例接近 0/1 时仍可靠。
    """
    if total == 0:
        return [0.0, 0.0]
    z = scipy_stats.norm.ppf((1 + confidence) / 2)
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _bootstrap_auc_ci(
    y_true: np.ndarray,
    y_score: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> tuple[float, list[float], bool]:
    """Bootstrap AUC 置信区间.

    Returns:
        (auc, [lower, upper], reliable)
    """
    from sklearn.metrics import roc_auc_score

    n = len(y_true)
    if n < 2 or len(np.unique(y_true)) < 2:
        return 0.5, [0.0, 0.0], False

    try:
        auc = roc_auc_score(y_true, y_score)
    except Exception:
        return 0.5, [0.0, 0.0], False

    rng = np.random.RandomState(random_state)
    boot_aucs: list[float] = []
    for _ in range(n_bootstrap):
        indices = rng.choice(n, size=n, replace=True)
        yt = y_true[indices]
        ys = y_score[indices]
        if len(np.unique(yt)) < 2:
            continue
        try:
            boot_aucs.append(roc_auc_score(yt, ys))
        except Exception:
            continue

    if len(boot_aucs) < 10:
        return float(auc), [0.0, 0.0], True

    alpha = (1 - confidence) / 2
    lower = float(np.percentile(boot_aucs, alpha * 100))
    upper = float(np.percentile(boot_aucs, (1 - alpha) * 100))
    return float(auc), [lower, upper], True


def compute_brier_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Brier Score：预测概率的均方误差.

    值域 [0, 1]，越小越好。0 = 完美，0.25 = 随机猜测。
    """
    if len(y_true) == 0:
        return 0.0
    return float(np.mean((y_score - y_true) ** 2))


def compute_binary_metrics(
    y_true: np.ndarray,
    y_pred_binary: np.ndarray,
    y_score: np.ndarray,
    confidence: float = 0.95,
    n_bootstrap: int = 1000,
) -> BinaryMetrics:
    """计算二分类模型的核心临床指标（含置信区间）.

    Args:
        y_true: 真实标签 (0/1)
        y_pred_binary: 二值化预测标签 (0/1)
        y_score: 预测概率 [0, 1]
        confidence: 置信水平
        n_bootstrap: AUC bootstrap 采样次数

    Returns:
        BinaryMetrics 对象
    """
    y_true = np.asarray(y_true).astype(int)
    y_pred_binary = np.asarray(y_pred_binary).astype(int)
    y_score = np.asarray(y_score, dtype=float)

    tp = int(np.sum((y_true == 1) & (y_pred_binary == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred_binary == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred_binary == 0)))
    fn = int(np.sum((y_true == 1) & (y_pred_binary == 0)))

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    npv = tn / (tn + fn) if (tn + fn) > 0 else 0.0

    # Wilson CI for proportions
    n_total = tp + fp + tn + fn
    sens_ci = _wilson_ci(tp, tp + fn, confidence) if (tp + fn) > 0 else [0.0, 0.0]
    spec_ci = _wilson_ci(tn, tn + fp, confidence) if (tn + fp) > 0 else [0.0, 0.0]
    ppv_ci = _wilson_ci(tp, tp + fp, confidence) if (tp + fp) > 0 else [0.0, 0.0]
    npv_ci = _wilson_ci(tn, tn + fn, confidence) if (tn + fn) > 0 else [0.0, 0.0]

    # Bootstrap CI for AUC
    auc, auc_ci, auc_reliable = _bootstrap_auc_ci(
        y_true, y_score, n_bootstrap=n_bootstrap, confidence=confidence
    )

    brier = compute_brier_score(y_true, y_score)

    return BinaryMetrics(
        sensitivity=sensitivity,
        specificity=specificity,
        ppv=ppv,
        npv=npv,
        auc=auc,
        brier_score=brier,
        sensitivity_ci=sens_ci,
        specificity_ci=spec_ci,
        ppv_ci=ppv_ci,
        npv_ci=npv_ci,
        auc_ci=auc_ci,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        auc_reliable=auc_reliable,
    )


def compute_per_class_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    class_labels: list[int] | None = None,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """按风险层级计算多类指标（one-vs-rest）.

    Phase 3 要求"按风险层级报告"，此函数对每个类别做 one-vs-rest 二分类。

    Args:
        y_true: 真实多类标签
        y_pred: 预测多类标签
        y_score: 预测概率矩阵 (n_samples, n_classes) 或一维数组（二分类）
        class_labels: 类别标签列表，None 则从 y_true 推断

    Returns:
        {"per_class": {label: BinaryMetrics.to_dict()}, "macro_avg": {...}}
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    y_score = np.asarray(y_score)

    if class_labels is None:
        class_labels = sorted(np.unique(y_true).tolist())

    per_class: dict[str, Any] = {}
    all_sensitivities: list[float] = []
    all_specificities: list[float] = []
    all_ppvs: list[float] = []
    all_npvs: list[float] = []
    all_aucs: list[float] = []
    all_briers: list[float] = []

    for cls in class_labels:
        y_true_bin = (y_true == cls).astype(int)

        if y_score.ndim == 2 and len(class_labels) > 2:
            # 多类概率矩阵
            cls_idx = class_labels.index(cls)
            y_score_bin = y_score[:, cls_idx]
        else:
            # 二分类或一维分数
            y_score_bin = y_score if len(class_labels) == 2 else (y_pred == cls).astype(float)

        y_pred_bin = (y_pred == cls).astype(int)

        if len(np.unique(y_true_bin)) < 2:
            # 单类场景：跳过该类别的 AUC 计算
            logger.warning("Class %s has only one label in y_true, skipping AUC", cls)

        metrics = compute_binary_metrics(y_true_bin, y_pred_bin, y_score_bin, confidence=confidence)
        per_class[str(cls)] = metrics.to_dict()

        all_sensitivities.append(metrics.sensitivity)
        all_specificities.append(metrics.specificity)
        all_ppvs.append(metrics.ppv)
        all_npvs.append(metrics.npv)
        all_aucs.append(metrics.auc if metrics.auc_reliable else 0.5)
        all_briers.append(metrics.brier_score)

    macro_avg = {
        "sensitivity": round(float(np.mean(all_sensitivities)), 4) if all_sensitivities else 0.0,
        "specificity": round(float(np.mean(all_specificities)), 4) if all_specificities else 0.0,
        "ppv": round(float(np.mean(all_ppvs)), 4) if all_ppvs else 0.0,
        "npv": round(float(np.mean(all_npvs)), 4) if all_npvs else 0.0,
        "auc": round(float(np.mean(all_aucs)), 4) if all_aucs else 0.0,
        "brier_score": round(float(np.mean(all_briers)), 4) if all_briers else 0.0,
    }

    return {"per_class": per_class, "macro_avg": macro_avg}


def compute_fairness_metrics(
    y_true: np.ndarray,
    y_pred_binary: np.ndarray,
    y_score: np.ndarray,
    groups: np.ndarray,
    min_group_size: int = _DEFAULT_MIN_GROUP_SIZE,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """按群体检查偏差（公平性审计）.

    Phase 3 要求"按性别、年级等允许且合规的群体检查偏差，
    但不输出可重新识别的小样本切片"。

    Args:
        y_true: 真实标签 (0/1)
        y_pred_binary: 二值化预测标签
        y_score: 预测概率
        groups: 群体标签数组（如性别、年级）
        min_group_size: 最小群体大小，低于此值不输出指标
        confidence: 置信水平

    Returns:
        {"per_group": {group: metrics}, "suppressed_groups": [...], "disparities": {...}}
    """
    y_true = np.asarray(y_true).astype(int)
    y_pred_binary = np.asarray(y_pred_binary).astype(int)
    y_score = np.asarray(y_score, dtype=float)
    groups = np.asarray(groups)

    unique_groups = np.unique(groups)
    per_group: dict[str, Any] = {}
    suppressed: list[str] = []
    group_sensitivities: dict[str, float] = {}
    group_specificities: dict[str, float] = {}
    group_ppvs: dict[str, float] = {}

    for g in unique_groups:
        mask = groups == g
        group_size = int(np.sum(mask))

        if group_size < min_group_size:
            suppressed.append(str(g))
            logger.info(
                "Fairness check: group '%s' suppressed (size=%d < min=%d)",
                g,
                group_size,
                min_group_size,
            )
            continue

        yt = y_true[mask]
        yp = y_pred_binary[mask]
        ys = y_score[mask]

        if len(np.unique(yt)) < 2:
            suppressed.append(f"{g}(single_class)")
            continue

        metrics = compute_binary_metrics(yt, yp, ys, confidence=confidence)
        per_group[str(g)] = metrics.to_dict()
        group_sensitivities[str(g)] = metrics.sensitivity
        group_specificities[str(g)] = metrics.specificity
        group_ppvs[str(g)] = metrics.ppv

    # 计算群体间差异（max - min）
    disparities: dict[str, float] = {}
    if len(group_sensitivities) >= 2:
        disparities["sensitivity_gap"] = round(
            max(group_sensitivities.values()) - min(group_sensitivities.values()), 4
        )
    if len(group_specificities) >= 2:
        disparities["specificity_gap"] = round(
            max(group_specificities.values()) - min(group_specificities.values()), 4
        )
    if len(group_ppvs) >= 2:
        disparities["ppv_gap"] = round(
            max(group_ppvs.values()) - min(group_ppvs.values()), 4
        )

    return {
        "per_group": per_group,
        "suppressed_groups": suppressed,
        "disparities": disparities,
        "min_group_size": min_group_size,
    }


def generate_clinical_validation_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    groups: np.ndarray | None = None,
    group_name: str = "unknown",
    class_labels: list[int] | None = None,
    confidence: float = 0.95,
    min_group_size: int = _DEFAULT_MIN_GROUP_SIZE,
) -> dict[str, Any]:
    """生成完整的临床验证报告.

    Phase 3 受控试点所需的全量模型验证报告。

    Args:
        y_true: 真实标签
        y_pred: 预测标签
        y_score: 预测概率
        groups: 群体标签（可选，用于公平性检查）
        group_name: 群体名称（如 "gender"、"grade"）
        class_labels: 类别标签
        confidence: 置信水平
        min_group_size: 公平性检查最小群体大小

    Returns:
        完整验证报告字典
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    y_score = np.asarray(y_score, dtype=float)

    report: dict[str, Any] = {
        "sample_size": len(y_true),
        "confidence_level": confidence,
        "class_labels": class_labels,
    }

    # 二分类或多类指标
    n_classes = len(np.unique(y_true)) if class_labels is None else len(class_labels)

    if n_classes <= 2:
        # 二分类
        y_pred_bin = np.asarray(y_pred).astype(int)
        y_score_flat = y_score if y_score.ndim == 1 else y_score[:, -1]
        metrics = compute_binary_metrics(
            y_true.astype(int), y_pred_bin, y_score_flat, confidence=confidence
        )
        report["binary_metrics"] = metrics.to_dict()
    else:
        # 多类
        report["multiclass_metrics"] = compute_per_class_metrics(
            y_true, y_pred, y_score, class_labels=class_labels, confidence=confidence
        )

    # 校准度
    from app.ml.evaluation import compute_calibration_curve

    y_score_flat = y_score if y_score.ndim == 1 else y_score[:, -1]
    report["calibration"] = compute_calibration_curve(y_true.astype(int), y_score_flat)

    # 公平性检查
    if groups is not None:
        groups = np.asarray(groups)
        # 二值化预测（多类时取最大概率对应的类别）
        if y_pred.ndim == 1 and len(np.unique(y_pred)) <= 2:
            y_pred_bin = np.asarray(y_pred).astype(int)
        else:
            # 多类：取风险等级 >= 阈值作为正类
            y_pred_bin = (y_score_flat >= 0.5).astype(int)

        report["fairness"] = {
            group_name: compute_fairness_metrics(
                y_true.astype(int),
                y_pred_bin,
                y_score_flat,
                groups,
                min_group_size=min_group_size,
                confidence=confidence,
            )
        }

    logger.info(
        "Clinical validation report generated: n=%d, classes=%d, fairness=%s",
        len(y_true),
        n_classes,
        group_name if groups is not None else "none",
    )

    return report
