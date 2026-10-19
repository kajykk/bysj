"""Phase 3 模型验证基础设施：临床指标 + 置信区间 + 公平性检查 + 决策效用.

按 Phase 3 计划要求实现：
- 按风险层级报告 sensitivity、specificity、PPV、NPV、AUROC、校准度及置信区间
- 按性别、年级等允许且合规的群体检查偏差
- 不输出可重新识别的小样本切片（min_group_size 保护）

ROUND_16（P1-1 补齐）：新增**决策曲线分析（DCA）/净获益**与 **ECE / 可靠性** 指标。
此前校准证据只有 calibration curve + 自设 Brier≤0.20，无法回答临床效用问题
「在这个阈值上干预，比『全治』与『全不治』哪个更好」。DCA 直接给出净获益对比，
ECE 给校准误差的单一汇总数，二者共同构成比自设目标更强的临床效用证据。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats as scipy_stats

from app.core.ml_decision_thresholds import DCA_CLINICAL_RANGE

logger = logging.getLogger(__name__)

# 小样本保护：低于此数量的群体不输出指标，防止可重新识别
_DEFAULT_MIN_GROUP_SIZE = 30

# ROUND_16 (P1-1)：DCA 临床合理阈值区间（筛查式预警：不漏报优先，取中低阈值段）。
# 该区间只用于**汇总判定**（净获益是否压过极端线），不改变逐阈值曲线本身。
# SSOT：app/core/ml_decision_thresholds.py::DCA_CLINICAL_RANGE（单一事实源，
# 不由调用方随意搬区间凑门槛）。
_DEFAULT_CLINICAL_RANGE = DCA_CLINICAL_RANGE


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
    # P0-T1-2: bootstrap 中因单类/异常被剔除的退化样本数
    degenerate_samples: int = 0

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
            "degenerate_samples": self.degenerate_samples,
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


def _bootstrap_auc_ci_with_count(
    y_true: np.ndarray,
    y_score: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> tuple[float, list[float], bool, int]:
    """Bootstrap AUC 置信区间.

    P0-T1-2: 返回第 4 个元素 degenerate_samples —— bootstrap 迭代中因重采样样本
    退化（单类标签或 roc_auc_score 抛异常）而被剔除的次数，不再静默丢弃。

    Returns:
        (auc, [lower, upper], reliable, degenerate_samples)
    """
    from sklearn.metrics import roc_auc_score

    n = len(y_true)
    if n < 2 or len(np.unique(y_true)) < 2:
        return 0.5, [0.0, 0.0], False, 0

    try:
        auc = roc_auc_score(y_true, y_score)
    except Exception:
        return 0.5, [0.0, 0.0], False, 0

    rng = np.random.RandomState(random_state)
    boot_aucs: list[float] = []
    degenerate_samples = 0
    for _ in range(n_bootstrap):
        indices = rng.choice(n, size=n, replace=True)
        yt = y_true[indices]
        ys = y_score[indices]
        if len(np.unique(yt)) < 2:
            degenerate_samples += 1
            continue
        try:
            boot_aucs.append(roc_auc_score(yt, ys))
        except Exception:
            degenerate_samples += 1
            continue

    if degenerate_samples:
        logger.warning(
            "Bootstrap AUC: %d/%d degenerate samples dropped (single-class bootstrap)",
            degenerate_samples,
            n_bootstrap,
        )

    if len(boot_aucs) < 10:
        return float(auc), [0.0, 0.0], True, degenerate_samples

    alpha = (1 - confidence) / 2
    lower = float(np.percentile(boot_aucs, alpha * 100))
    upper = float(np.percentile(boot_aucs, (1 - alpha) * 100))
    return float(auc), [lower, upper], True, degenerate_samples


def _bootstrap_auc_ci(
    y_true: np.ndarray,
    y_score: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> tuple[float, list[float], bool]:
    """Bootstrap AUC 置信区间的兼容包装，保留历史三元组返回值."""
    auc, ci, reliable, _ = _bootstrap_auc_ci_with_count(
        y_true,
        y_score,
        n_bootstrap=n_bootstrap,
        confidence=confidence,
        random_state=random_state,
    )
    return auc, ci, reliable


def compute_brier_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Brier Score：预测概率的均方误差.

    值域 [0, 1]，越小越好。0 = 完美，0.25 = 随机猜测。
    """
    if len(y_true) == 0:
        return 0.0
    return float(np.mean((y_score - y_true) ** 2))


def compute_ece(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error（等宽分箱）.

    ECE = Σ_b (n_b / n) · |acc_b − conf_b|，其中 acc_b 为箱 b 内正例比例、
    conf_b 为箱 b 内平均预测概率。值域 [0, 1]，0 = 完美校准。

    与 calibration curve 互补：curve 给逐箱细节，ECE 给可比较的单一汇总数。
    ROUND_16 (P1-1)：替换「只有曲线、没有汇总误差」的证据缺口。
    """
    y_true = np.asarray(y_true).astype(float)
    y_score = np.asarray(y_score, dtype=float)
    if len(y_true) == 0 or n_bins <= 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # 预测恰为 1.0 的样本归入最后一箱（np.digitize 右开区间会漏掉）
    bin_idx = np.clip(np.digitize(y_score, edges[1:-1], right=False), 0, n_bins - 1)
    n = len(y_true)
    ece = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        n_b = int(np.sum(mask))
        if n_b == 0:
            continue
        acc_b = float(np.mean(y_true[mask]))
        conf_b = float(np.mean(y_score[mask]))
        ece += (n_b / n) * abs(acc_b - conf_b)
    return float(ece)


def decision_curve_analysis(
    y_true: np.ndarray,
    y_score: np.ndarray,
    thresholds: np.ndarray | list[float] | None = None,
    clinical_range: tuple[float, float] = _DEFAULT_CLINICAL_RANGE,
) -> dict[str, Any]:
    """决策曲线分析（DCA）：逐阈值比较模型净获益与两条极端策略线.

    净获益定义（Vickers & Elkin 2006 口径）：
        NB_model(t)    = TP/n − FP/n · pt(t),  pt(t) = t/(1−t)（阈值几率）
        NB_treat_all(t)= π − (1−π) · pt(t),  π 为患病率（阳性率）
        NB_treat_none  = 0（任何阈值下都不干预）

    「全治」线随 t 增大而下降，t = π 时穿过 0；模型只有在其工作区间内持续位于
    两条极端线**上方**才具备临床效用——这是比单一阈值 F1 更接近临床问题的证据。

    Args:
        y_true: 真实标签 (0/1)
        y_score: 预测概率 [0, 1]
        thresholds: 阈值网格，None 默认 0.05~0.95 步长 0.05
        clinical_range: 临床合理阈值区间（汇总判定用），默认 (0.1, 0.4)

    Returns:
        {
          "prevalence": float,
          "clinical_range": [lo, hi],
          "curve": [{threshold, pt, net_benefit_model,
                     net_benefit_treat_all, net_benefit_treat_none}, ...],
          "summary": {
            "net_benefit_min_in_range": float,       # 区间内模型 NB 最小值
            "treat_all_nb_in_range": [min, max],     # 区间内全治线 NB 范围
            "model_dominates_treat_all_in_range": bool,
            "model_dominates_treat_none_in_range": bool,
            "model_dominates_extremes_in_range": bool,  # 同时压过两条极端线
          },
        }

    ROUND_16 (P1-1) 门槛先定：clinical_range 内模型净获益须 **≥ 全治线且 ≥ 全不治线**；
    达不到则如实报 ``model_dominates_extremes_in_range=False``，**不得靠移阈值区间凑**
    （区间本身是固定的临床先验，不是可调参数）。
    """
    y_true = np.asarray(y_true).astype(float)
    y_score = np.asarray(y_score, dtype=float)
    if len(y_true) == 0:
        raise ValueError("decision_curve_analysis 需要非空样本")
    if np.any((y_score < 0) | (y_score > 1)):
        raise ValueError("decision_curve_analysis 的 y_score 必须在 [0,1]")

    n = len(y_true)
    prevalence = float(np.mean(y_true))
    pos = float(np.sum(y_true))
    neg = float(n - pos)

    if thresholds is None:
        grid = np.round(np.arange(0.05, 1.0, 0.05), 4)
    else:
        grid = np.asarray(thresholds, dtype=float)

    lo_c, hi_c = float(clinical_range[0]), float(clinical_range[1])
    if not (0.0 <= lo_c < hi_c < 1.0):
        raise ValueError(f"clinical_range 须满足 0 <= lo < hi < 1，得到 {clinical_range!r}")

    curve: list[dict[str, float]] = []
    in_range: list[dict[str, float]] = []
    for t in grid:
        t = float(t)
        if not (0.0 <= t < 1.0):
            raise ValueError(f"DCA 阈值须在 [0,1)，得到 {t}")
        pt = t / (1.0 - t)
        y_pred = (y_score >= t).astype(float)
        tp = float(np.sum((y_true == 1) & (y_pred == 1)))
        fp = float(np.sum((y_true == 0) & (y_pred == 1)))
        nb_model = tp / n - fp / n * pt
        nb_treat_all = pos / n - neg / n * pt
        row = {
            "threshold": round(t, 4),
            "pt": round(pt, 4),
            "net_benefit_model": round(nb_model, 6),
            "net_benefit_treat_all": round(nb_treat_all, 6),
            "net_benefit_treat_none": 0.0,
        }
        curve.append(row)
        # 区间判定用**原始 t**（不被 round 扰动），自定义网格的边界点才不会被
        # 四舍五入挤出临床区间
        if lo_c <= t <= hi_c:
            in_range.append(row)
    if in_range:
        nb_min = min(row["net_benefit_model"] for row in in_range)
        ta_vals = [row["net_benefit_treat_all"] for row in in_range]
        dominates_all = all(
            row["net_benefit_model"] >= row["net_benefit_treat_all"] for row in in_range
        )
        dominates_none = all(row["net_benefit_model"] >= 0.0 for row in in_range)
        summary = {
            "net_benefit_min_in_range": round(nb_min, 6),
            "treat_all_nb_in_range": [round(min(ta_vals), 6), round(max(ta_vals), 6)],
            "model_dominates_treat_all_in_range": bool(dominates_all),
            "model_dominates_treat_none_in_range": bool(dominates_none),
            "model_dominates_extremes_in_range": bool(dominates_all and dominates_none),
        }
    else:
        summary = {
            "net_benefit_min_in_range": 0.0,
            "treat_all_nb_in_range": [0.0, 0.0],
            "model_dominates_treat_all_in_range": False,
            "model_dominates_treat_none_in_range": False,
            "model_dominates_extremes_in_range": False,
        }

    return {
        "prevalence": round(prevalence, 4),
        "clinical_range": [lo_c, hi_c],
        "curve": curve,
        "summary": summary,
    }


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
    sens_ci = _wilson_ci(tp, tp + fn, confidence) if (tp + fn) > 0 else [0.0, 0.0]
    spec_ci = _wilson_ci(tn, tn + fp, confidence) if (tn + fp) > 0 else [0.0, 0.0]
    ppv_ci = _wilson_ci(tp, tp + fp, confidence) if (tp + fp) > 0 else [0.0, 0.0]
    npv_ci = _wilson_ci(tn, tn + fn, confidence) if (tn + fn) > 0 else [0.0, 0.0]

    # Bootstrap CI for AUC
    auc, auc_ci, auc_reliable, degenerate_samples = _bootstrap_auc_ci_with_count(
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
        degenerate_samples=degenerate_samples,
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
    # ROUND_16 (P1-3)：原有 sensitivity/specificity/ppv gap 之外，补齐文献标准
    # 公平性差距读数：TPR 差（=机会均等差距 equal-opportunity difference）、
    # FPR 差、FNR 差，以及 equalized odds 合成差距 max(tpr_gap, fpr_gap)。
    # 缺口量化是「评估」；缓解另有独立模块（fairness_mitigation，未接入生产）。
    disparities: dict[str, float] = {}
    if len(group_sensitivities) >= 2:
        tpr_gap = max(group_sensitivities.values()) - min(group_sensitivities.values())
        disparities["sensitivity_gap"] = round(tpr_gap, 4)
        disparities["tpr_gap"] = round(tpr_gap, 4)
    if len(group_specificities) >= 2:
        fpr_gap = max(1 - v for v in group_specificities.values()) - min(
            1 - v for v in group_specificities.values()
        )
        disparities["specificity_gap"] = round(max(group_specificities.values()) - min(group_specificities.values()), 4)
        disparities["fpr_gap"] = round(fpr_gap, 4)
    if len(group_sensitivities) >= 2:
        disparities["fnr_gap"] = round(tpr_gap, 4)  # FNR = 1 − TPR，组间差与 TPR 差相同
    if len(group_ppvs) >= 2:
        disparities["ppv_gap"] = round(max(group_ppvs.values()) - min(group_ppvs.values()), 4)
    if "tpr_gap" in disparities and "fpr_gap" in disparities:
        disparities["equalized_odds_gap"] = round(
            max(disparities["tpr_gap"], disparities["fpr_gap"]), 4
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
        metrics = compute_binary_metrics(y_true.astype(int), y_pred_bin, y_score_flat, confidence=confidence)
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

    # ROUND_16 (P1-1)：决策曲线 / 净获益 + ECE（仅二分类有意义；多类不强行套用）
    if n_classes <= 2:
        report["decision_curve"] = decision_curve_analysis(
            y_true.astype(int), y_score_flat
        )
        report["ece"] = round(compute_ece(y_true.astype(int), y_score_flat), 4)

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
