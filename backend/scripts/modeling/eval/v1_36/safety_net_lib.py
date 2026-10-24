#!/usr/bin/env python
"""ROUND_36（P1 漏报安全网）：双阈值「预警 + 安全网」规则的纯函数库。

动机（ROUND_33 的实测依据）
--------------------------
文本模态在唯一可引用泛化口径（groupwise OOF，n=8379 / 1277 组）上：
- Recall 0.5375 [C-24] ⇒ 固定阈值 0.5 下**漏掉约 46% 的阳性**；
- 校准斜率 1.3466 [C-28] > 1 ⇒ 概率系统性偏保守（欠自信），即「概率偏低」
  不是噪声而是结构性的 ⇒ **下调阈值是有依据的方向**，不是调参碰运气。

规则语义
--------
    p >= t_high            ⇒ 直接预警（进预警队列）
    t_low <= p < t_high    ⇒ 安全网（强制人工复核；漏报统计上计为「捕获」，
                              但复核成本单列，不混入预警精确率）
    p < t_low              ⇒ 阴性（放行）

为什么用双阈值而不是单阈值：单阈值下调会同时抬高 FP，把精确率一起打崩；
双阈值把「不确定带」单独送复核，用**可承受的人工成本**换漏报率下降。
精确率只对「直接预警」负责（安全网样本不参与精确率分母），这正是
「辅助初筛 + 人工复核」定位的数学形式。

纪律
----
1. 工作点选择标准**先定后扫**（见 pick_operating_point 的 docstring），
   防止「扫完再挑好看的那个」——那是事后调参，不是预设准则。
2. 无独立留出集：全部样本都是 OOF（训练时留出），不存在第二份数据可验证
   扫描出的工作点。这条选择性偏差风险必须随读数一起记账，不得隐去。
3. 纯 numpy 手写，不 import sklearn；CI 与点估计共用同一实现。
"""

from __future__ import annotations

import numpy as np

# 工作点选择标准（先定后扫，写死在这里以免被事后解释改写）
TARGET_NET_RECALL = 0.80  # 目标：净漏报率 ≤ 20%（抑郁筛查里漏报是主要风险）
DEFAULT_T_HIGH_GRID = [round(0.05 * k, 2) for k in range(2, 13)]  # 0.10 .. 0.60
DEFAULT_T_LOW_GRID = [round(0.01 * k, 2) for k in range(1, 12)]   # 0.01 .. 0.11


def _as_arrays(y, p) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=np.float64).ravel()
    p = np.asarray(p, dtype=np.float64).ravel()
    if y.shape != p.shape:
        raise ValueError(f"y 与 p 长度不一致：{y.shape} vs {p.shape}")
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("p 必须落在 [0, 1]")
    return y, p


def apply_safety_net(y, p, t_low: float, t_high: float) -> dict:
    """双阈值规则的计数与派生指标。

    前置约束：0 < t_low < t_high < 1（t_low == t_high 时规则退化成单阈值，
    调用方应使用 single_threshold_metrics）。
    """
    if not (0.0 < t_low < t_high < 1.0):
        raise ValueError(f"要求 0 < t_low < t_high < 1，收到 {t_low} / {t_high}")
    y, p = _as_arrays(y, p)
    pos = y == 1.0
    neg = ~pos
    alert = p >= t_high
    sn = (p >= t_low) & (p < t_high)
    tp = int((alert & pos).sum())
    fp = int((alert & neg).sum())
    sn_total = int(sn.sum())
    sn_caught = int((sn & pos).sum())
    fn = int(((p < t_low) & pos).sum())
    tn = int(((p < t_low) & neg).sum())
    n = int(y.size)
    P = int(pos.sum())
    N = int(neg.sum())
    net_recall = (tp + sn_caught) / P if P else float("nan")
    return {
        "t_low": float(t_low),
        "t_high": float(t_high),
        "n": n,
        "n_pos": P,
        "n_neg": N,
        "tp": tp,
        "fp": fp,
        "sn_total": sn_total,
        "sn_caught": sn_caught,
        "fn": fn,
        "tn": tn,
        "net_recall": float(net_recall),
        "miss_rate": float(1.0 - net_recall) if P else float("nan"),
        "alert_rate": float((tp + fp) / n),
        "review_burden": float((tp + fp + sn_total) / n),
        "alert_precision": float(tp / (tp + fp)) if (tp + fp) else float("nan"),
        "sn_precision": float(sn_caught / sn_total) if sn_total else float("nan"),
    }


def single_threshold_metrics(y, p, thr: float) -> dict:
    """单阈值基线（对照用）：thr 及以上判阳性。"""
    if not (0.0 < thr < 1.0):
        raise ValueError(f"阈值必须落在 (0, 1)：{thr}")
    y, p = _as_arrays(y, p)
    pos = y == 1.0
    pred = p >= thr
    tp = int((pred & pos).sum())
    fp = int((pred & ~pos).sum())
    fn = int((~pred & pos).sum())
    tn = int((~pred & ~pos).sum())
    P = int(pos.sum())
    n = int(y.size)
    return {
        "threshold": float(thr),
        "n": n,
        "n_pos": P,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "recall": float(tp / P) if P else float("nan"),
        "precision": float(tp / (tp + fp)) if (tp + fp) else float("nan"),
        "f1": (
            2.0 * tp / (2.0 * tp + fp + fn) if (2.0 * tp + fp + fn) else float("nan")
        ),
        "alert_rate": float((tp + fp) / n),
    }


def pick_operating_point(
    y,
    p,
    t_high_grid=None,
    t_low_grid=None,
    target_net_recall: float = TARGET_NET_RECALL,
) -> dict:
    """按**预设标准**选工作点：净 Recall ≥ target 且复核负担最小。

    标准先定后扫（不是扫完挑好看的）：
        1. 净 Recall ≥ target_net_recall（漏报率 ≤ 1 − target）；
        2. 在满足 1 的配置里取 review_burden 最小者；
        3. 仍并列则取 t_high 更高者（更少的直接预警、更多走复核），
           再并列取 t_low 更低者（更宽的捕获带）。
    若无任何配置满足 1 ⇒ 返回 {"feasible": False, ...}（如实报告不可达，
    不偷偷放宽标准）。
    """
    t_high_grid = t_high_grid or DEFAULT_T_HIGH_GRID
    t_low_grid = t_low_grid or DEFAULT_T_LOW_GRID
    best: dict | None = None
    best_key: tuple | None = None
    n_feasible = 0
    for t_high in t_high_grid:
        for t_low in t_low_grid:
            if not (0.0 < t_low < t_high < 1.0):
                continue
            m = apply_safety_net(y, p, t_low, t_high)
            # 注意用 `not (x >= target)` 而不是 `x < target`：无阳性时 net_recall 为 NaN，
            # NaN < target 是 False 会让 NaN 配置**逃过**筛选（NaN 比较的经典陷阱）。
            if not (m["net_recall"] >= target_net_recall):
                continue
            n_feasible += 1
            # 最小复核负担；并列时 t_high 更高、t_low 更低
            key = (round(m["review_burden"], 12), -t_high, -t_low)
            if best_key is None or key < best_key:
                best_key = key
                best = m
    if best is None:
        return {
            "feasible": False,
            "target_net_recall": float(target_net_recall),
            "n_feasible": 0,
            "reason": "网格内无任何配置达到目标净 Recall ⇒ 该目标在此数据上不可达",
        }
    return {
        "feasible": True,
        "target_net_recall": float(target_net_recall),
        "n_feasible": int(n_feasible),
        "operating_point": best,
    }


def sweep_safety_net(y, p, t_high_grid=None, t_low_grid=None) -> list[dict]:
    """全网格扫描（t_high × t_low），用于产物落盘与复算核对。"""
    t_high_grid = t_high_grid or DEFAULT_T_HIGH_GRID
    t_low_grid = t_low_grid or DEFAULT_T_LOW_GRID
    out = []
    for t_high in t_high_grid:
        for t_low in t_low_grid:
            if not (0.0 < t_low < t_high < 1.0):
                continue
            out.append(apply_safety_net(y, p, t_low, t_high))
    return out


def sweep_single(y, p, grid=None) -> list[dict]:
    """单阈值基线扫描。"""
    grid = grid or [round(0.01 * k, 2) for k in range(5, 96)]  # 0.05 .. 0.95
    return [single_threshold_metrics(y, p, t) for t in grid]
