#!/usr/bin/env python
"""ROUND_33 (P1 校准)：校准与决策曲线分析的纯函数库。

设计纪律（与 v1_29 / v1_30 一脉相承）：
1. **只读 csv**：本模块不碰数据集、不碰 artifact，输入全部是 (y, p) 或 (y, p, group)。
2. **无外部评估依赖**：不 import sklearn/metrics，全部手写 numpy + scipy —— 这样
   「点估计」与「bootstrap CI」共用同一套实现，不会出现「CI 用一种算法、点估计用另一种」
   的隐性不一致（v1_30 已踩过：换 rankdata 必须保持 rng 序列，差 3.9e-4）。
3. **确定性**：无随机源泄漏到点估计；bootstrap 的 rng 由调用方显式传入 seed。
4. **行序即计算序**：调用方必须保证 y / p 按落盘行序传入（见 calibration_analysis.py）。

指标口径：
- brier_score             : mean((p - y)^2)，概率级整体校准+分辨混合度量
- expected_calibration_error : 等宽分箱 ECE（默认 10 箱），Σ |B_k|/n · |acc_k - conf_k|
- max_calibration_error   : max_k |acc_k - conf_k|
- calibration_slope_intercept : Platt 缩放（y ~ logit(p) 的逻辑回归），理想 slope=1 / intercept=0。
                               用 Newton-Raphson（IRLS）手写，25 步固定迭代，无早停 ⇒ 确定性。
- decision_curve          : 净获益 net_benefit(t) = TP/n - (FP/n)·(t/(1-t))，
                               同时返回 treat_all / treat_none 基线，t 由调用方给定。
"""

from __future__ import annotations

import numpy as np

NEWTON_MAX_ITER = 100
NEWTON_TOL = 1e-12


def _as_arrays(y, p) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=np.float64).ravel()
    p = np.asarray(p, dtype=np.float64).ravel()
    if y.shape != p.shape:
        raise ValueError(f"y 与 p 长度不一致: {y.shape} vs {p.shape}")
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("p 必须落在 [0, 1]：存在越界概率值")
    return y, p


def brier_score(y, p) -> float:
    """Brier 分数（越小越好）。空输入返回 nan，由调用方记账。"""
    y, p = _as_arrays(y, p)
    if y.size == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def _bin_stats(y: np.ndarray, p: np.ndarray, edges: np.ndarray):
    """等宽分箱 → (每箱计数, 每箱平均标签, 每箱平均概率)。空箱计数为 0。"""
    n = y.size
    n_bins = len(edges) - 1
    # 右闭区间归属：p=1.0 归入最后一箱（np.searchsorted 的 side='right' 语义）
    idx = np.searchsorted(edges, p, side="right") - 1
    idx = np.clip(idx, 0, n_bins - 1)
    counts = np.bincount(idx, minlength=n_bins).astype(np.float64)
    sum_y = np.bincount(idx, weights=y, minlength=n_bins)
    sum_p = np.bincount(idx, weights=p, minlength=n_bins)
    nonzero = counts > 0
    acc = np.zeros(n_bins)
    conf = np.zeros(n_bins)
    acc[nonzero] = sum_y[nonzero] / counts[nonzero]
    conf[nonzero] = sum_p[nonzero] / counts[nonzero]
    return counts / float(n), acc, conf


def expected_calibration_error(y, p, n_bins: int = 10) -> float:
    """ECE：等宽分箱（默认 10 箱）。"""
    y, p = _as_arrays(y, p)
    if y.size == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    weights, acc, conf = _bin_stats(y, p, edges)
    return float(np.sum(weights * np.abs(acc - conf)))


def max_calibration_error(y, p, n_bins: int = 10) -> float:
    """MCE：等宽分箱（默认 10 箱）。空箱不计入。"""
    y, p = _as_arrays(y, p)
    if y.size == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    _, acc, conf = _bin_stats(y, p, edges)
    return float(np.max(np.abs(acc - conf)))


def reliability_table(y, p, n_bins: int = 10) -> list[dict]:
    """校准曲线（reliability diagram）的分箱表：空箱一并返回，便于复算核对。"""
    y, p = _as_arrays(y, p)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    counts, acc, conf = _bin_stats(y, p, edges)
    out = []
    for k in range(n_bins):
        out.append(
            {
                "bin": k,
                "lower": float(edges[k]),
                "upper": float(edges[k + 1]),
                "count": int(round(counts[k] * y.size)),
                "observed_rate": float(acc[k]),
                "mean_predicted": float(conf[k]),
            }
        )
    return out


def calibration_slope_intercept(y, p) -> dict:
    """Platt 缩放的 calibration slope / intercept。

    模型：logit(p) = intercept + slope · x，其中 x = logit(p)。
    理想校准 = slope 1 / intercept 0；slope<1 ⇒ 预测过于极端（过自信）。

    Newton-Raphson（IRLS）固定 25 步，无早停 ⇒ 同样输入必然同样输出。
    """
    y, p = _as_arrays(y, p)
    if y.size == 0:
        return {"slope": float("nan"), "intercept": float("nan")}
    # 概率贴边裁剪，避免 logit 无穷（0/1 的概率只可能来自模型输出）
    eps = 1e-12
    p_c = np.clip(p, eps, 1.0 - eps)
    x = np.log(p_c / (1.0 - p_c))
    n = x.size
    design = np.column_stack([np.ones(n), x])
    beta = np.zeros(2)
    for _ in range(NEWTON_MAX_ITER):
        eta = design @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.maximum(mu * (1.0 - mu), 1e-10)
        grad = design.T @ (y - mu)
        hess = design.T @ (design * w[:, None])
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            break
        beta = beta + step
        if np.max(np.abs(step)) < NEWTON_TOL:
            break
    return {"slope": float(beta[1]), "intercept": float(beta[0])}


def decision_curve(y, p, thresholds) -> dict:
    """决策曲线分析（DCA）：净获益 vs 阈值。

    net_benefit(t)      = TP/n - (FP/n) · (t/(1-t))
    treat_all(t)        = prevalence - (1-prevalence) · (t/(1-t))
    treat_none(t)       = 0
    阈值 t 为「概率阈值」：t=prevalence 时 treat_all=0。
    """
    y, p = _as_arrays(y, p)
    t = np.asarray(thresholds, dtype=np.float64).ravel()
    if y.size == 0:
        raise ValueError("decision_curve 不接受空输入")
    if np.any((t <= 0.0) | (t >= 1.0)):
        raise ValueError("阈值必须落在 (0, 1) 开区间")
    n = float(y.size)
    prev = float(y.mean())
    odds = t / (1.0 - t)
    # 向量化：对每个阈值统计 TP / FP
    pred = p[None, :] >= t[:, None]
    pos = y[None, :] == 1.0
    tp = (pred & pos).sum(axis=1).astype(np.float64)
    fp = (pred & ~pos).sum(axis=1).astype(np.float64)
    nb_model = tp / n - (fp / n) * odds
    nb_all = prev - (1.0 - prev) * odds
    nb_none = np.zeros_like(t)
    return {
        "thresholds": t,
        "net_benefit_model": nb_model,
        "net_benefit_treat_all": nb_all,
        "net_benefit_treat_none": nb_none,
        "prevalence": prev,
    }
