#!/usr/bin/env python
"""ROUND_28 (T5)：论文数字校验闸门——「文档里写 A、产物里是 B」在本仓不可发生。

纪律（ROUND_28 提示词 §〇 / §二）
--------------------------------
论文里的每个数字必须能由**已提交产物**用一条命令复算；不得从任何 ROUND 汇报转引。
本脚本是这条纪律的机器化：它从已提交的 csv/json **复算**台账里每个「可进论文」的数字，
再与 `docs/thesis/CLAIMS_LEDGER.md` / `docs/thesis/RESULTS_CHAPTER.md` 里出现的数字
逐一比对（容差 = 展示精度），任一漂移即红；黑名单数字若无拒绝标记出现在任何论文文档即红。

复算范围与边界（如实记账，不假装更强）
------------------------------------
1. **点估计 / 混淆矩阵 / n / AUC 点估计**：本脚本内的**独立实现**（`threshold_metrics` /
   `auc_point`），不复用 v1_29 评估脚本的代码——两套实现互为交叉验证。
2. **bootstrap 95% CI**：复用与 v1_29 评估脚本**同一抽样序列**（逐次 `rng.randint(0, n, n)`、
   B=10000、seed=42）与同一分位法；AUC 的 tie 处理用 `scipy.rankdata`（method="average"，
   与 01 的 mergesort 平均秩数学同值；02 的 `--verify-fast` 已实测两端点差 0.000e+00）。
   即 CI 层验证的是「文档 ⇄ 已提交 json」与「json ⇄ 同序列重算」的一致性，不是第三套算法。
3. **本闸门不替代 ROUND_27 的「提交产物 == 单命令产物」硬闸门**：那条命令
   （`01_reproducible_eval.py --report-only`）需要原始数据集（`datasets/` 不在版本库），
   CI 干净 checkout 跑不了；本闸门只到 csv/json 层（与外部审稿人复算入口同一层）。
4. **PHQ-9 的 682 行**：原始数据不在版本库，也无 json 工件记录行数 ⇒ 只能做**跨文档对齐**
   （与 `docs/model-evaluation/TRANSFER_MATRIX.md` 的字面量比对），脚本不假装能复算它。
5. **`fusion_weight_sensitivity.csv` 的生成脚本未入库**：本闸门复算的是它的**内部一致性**
   （加权平均公式 + 风险等级阈值表 + 生产权重行存在），不是重新生成它。

只读承诺
--------
本脚本不写任何文件（无 write_text/write_bytes/mkdir；test_p2_55 用 AST 钉死这一点）。

用法
----
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/verify_thesis_numbers.py          # 全量校验
    .venv/Scripts/python.exe scripts/modeling/eval/verify_thesis_numbers.py --show   # 只打印复算真值表
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]  # backend/scripts/modeling/eval -> 仓库根
BACKEND = REPO / "backend"
EVAL_DOCS = REPO / "docs" / "model-evaluation"
THESIS = REPO / "docs" / "thesis"
ARTIFACTS = BACKEND / "models" / "artifacts"

LEDGER = THESIS / "CLAIMS_LEDGER.md"
CHAPTER = THESIS / "RESULTS_CHAPTER.md"
QA = THESIS / "REVIEWER_QA.md"
LIMITATIONS = THESIS / "LIMITATIONS.md"
THESIS_DOCS = (LEDGER, CHAPTER, QA, LIMITATIONS)

BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42
DECISION = 0.5  # 判定阈值（与三个评估单元的 json.threshold 一致）

# ────────────────────────── 单元定义（csv ⇄ json 已成对提交） ──────────────────────────

UNITS: dict[str, dict] = {
    "physio_v2": {
        "label": "生理域内（生产路径）",
        "csv": ARTIFACTS / "physiological_optimized" / "test_predictions.csv",
        "sha_sidecar": ARTIFACTS / "physiological_optimized" / "test_predictions.csv.sha256",
        "json": EVAL_DOCS / "physio_v2_current_data_eval.json",
        "has_refit": True,
    },
    "physio_kaggle": {
        "label": "生理 × Kaggle Wearable（降级）",
        "csv": ARTIFACTS / "eval_transfer" / "transfer_physio_kaggle_predictions.csv",
        "sha_sidecar": ARTIFACTS / "eval_transfer" / "transfer_physio_kaggle_predictions.csv.sha256",
        "json": EVAL_DOCS / "transfer_physio_kaggle_eval.json",
        "has_refit": False,
    },
    "text_ood": {
        "label": "文本 × OOD(strict)（域内压力测试）",
        "csv": ARTIFACTS / "eval_transfer" / "transfer_text_ood_predictions.csv",
        "sha_sidecar": ARTIFACTS / "eval_transfer" / "transfer_text_ood_predictions.csv.sha256",
        "json": EVAL_DOCS / "transfer_text_ood_eval.json",
        "has_refit": False,
    },
}

GROUPWISE_CSV = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
GROUPWISE_CI_JSON = BACKEND / "scripts" / "modeling" / "eval" / "v1_30" / "groupwise_ci.json"
GROUPWISE_JSON = REPO / "docs" / "planning" / "backend_text_bilingual_v2_metrics.json"
SENSITIVITY_CSV = EVAL_DOCS / "fusion_weight_sensitivity.csv"
TRANSFER_MATRIX = EVAL_DOCS / "TRANSFER_MATRIX.md"
RISK_THRESHOLDS_PY = BACKEND / "app" / "core" / "risk_thresholds.py"
FUSION_ENGINE_PY = BACKEND / "app" / "ml" / "fusion_engine.py"

METRIC_LABELS = {
    "Accuracy": "acc",
    "Precision": "prec",
    "Recall": "rec",
    "F1": "f1",
    "ROC AUC": "roc_auc",
}

# ────────────────────────── 独立指标实现（刻意不复用 v1_29 代码） ──────────────────────────


def threshold_metrics(y: np.ndarray, score: np.ndarray, thr: float = DECISION) -> dict:
    """阈值指标 + 混淆矩阵（独立实现；与 01 的公式逐项对应，便于交叉验证）。"""
    pred = score >= thr
    pos = y == 1
    tp = int((pred & pos).sum())
    fp = int((pred & ~pos).sum())
    fn = int((~pred & pos).sum())
    tn = int((~pred & ~pos).sum())
    n = tp + fp + fn + tn
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"n": n, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "acc": (tp + tn) / n, "prec": prec, "rec": rec, "f1": f1}


def auc_point(y: np.ndarray, score: np.ndarray) -> float:
    """Mann-Whitney U 的 ROC AUC（mergesort + 平均秩；纯 numpy，无 scipy）。"""
    pos = score[y == 1]
    neg = score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    combined = np.concatenate([pos, neg])
    order = np.argsort(combined, kind="mergesort")
    ranks = np.empty(len(order), dtype=np.float64)
    ranks[order] = np.arange(1, len(order) + 1, dtype=np.float64)
    sorted_vals = combined[order]
    i = 0
    while i < len(sorted_vals):
        j = i
        while j + 1 < len(sorted_vals) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            avg = ranks[order[i : j + 1]].mean()
            ranks[order[i : j + 1]] = avg
        i = j + 1
    u = ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


def _auc_rank(y: np.ndarray, score: np.ndarray) -> float:
    """bootstrap 内使用的向量化 AUC（scipy 平均秩；与 auc_point 数学同值）。"""
    from scipy.stats import rankdata

    pos_mask = y == 1
    n_pos = int(pos_mask.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r = rankdata(score, method="average")
    u = float(r[pos_mask].sum()) - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def bootstrap_ci(y: np.ndarray, score: np.ndarray, B: int = BOOTSTRAP_B, seed: int = BOOTSTRAP_SEED) -> dict:
    """非参数 bootstrap 分位 CI。**抽样序列与 v1_29 完全一致**（逐次 rng.randint(0, n, n)）。"""
    rng = np.random.RandomState(seed)
    n = len(y)
    samples: dict[str, list[float]] = {"acc": [], "prec": [], "rec": [], "f1": [], "roc_auc": []}
    for _ in range(B):
        idx = rng.randint(0, n, n)
        ys, ss = y[idx], score[idx]
        m = threshold_metrics(ys, ss)
        for k in ("acc", "prec", "rec", "f1"):
            samples[k].append(m[k])
        a = _auc_rank(ys, ss)
        if not np.isnan(a):
            samples["roc_auc"].append(a)
    out = {}
    for k, vals in samples.items():
        arr = np.array(vals, dtype=np.float64)
        out[k] = {
            "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))],
            "bootstrap_n": int(len(arr)),
        }
    return out


# ────────────────────────── 产物读取与复算（带缓存：全闸门只算一轮 bootstrap） ──────────────────────────


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_predictions_csv(path: Path, refit: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """读逐样本 csv（列：sample_id,row_index,y_true,y_score,y_pred[,y_score_refit_scaler]）。

    行序 = 落盘行序（row_index 升序）——ROUND_27 的根因教训：CI 必须按落盘序算。
    """
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    header = lines[0].split(",")
    expected = ["sample_id", "row_index", "y_true", "y_score", "y_pred"]
    if refit:
        expected.append("y_score_refit_scaler")
    assert header == expected, f"{path.name} 列表头不符：{header}"
    y, s, preds, refit_scores = [], [], [], []
    for ln in lines[1:]:
        parts = ln.split(",")
        y.append(int(parts[2]))
        s.append(float(parts[3]))
        preds.append(int(parts[4]))
        if refit:
            refit_scores.append(float(parts[5]))
    return (
        np.array(y, dtype=np.int64),
        np.array(s, dtype=np.float64),
        np.array(preds, dtype=np.int64),
        np.array(refit_scores, dtype=np.float64) if refit else None,
    )


_UNIT_CACHE: dict[str, dict] = {}


def recompute_unit(unit: str) -> dict:
    """从一个单元已提交的 csv 复算全部数字（点估计独立实现 + 同序列 bootstrap）。"""
    if unit in _UNIT_CACHE:
        return _UNIT_CACHE[unit]
    spec = UNITS[unit]
    y, s, preds, refit_scores = read_predictions_csv(spec["csv"], spec["has_refit"])
    # 工件内部一致性：y_pred 列必须就是 (y_score >= 0.5)
    assert np.array_equal(preds, (s >= DECISION).astype(np.int64)), (
        f"{unit} 的 y_pred 列与 y_score>={DECISION} 不一致（工件被手改过？）"
    )
    m = threshold_metrics(y, s)
    ci = bootstrap_ci(y, s)
    truth = {
        "n": m["n"], "TP": m["TP"], "FP": m["FP"], "FN": m["FN"], "TN": m["TN"],
        "acc": m["acc"], "prec": m["prec"], "rec": m["rec"], "f1": m["f1"],
        "roc_auc": auc_point(y, s),
        "acc_ci": ci["acc"]["ci95"], "prec_ci": ci["prec"]["ci95"],
        "rec_ci": ci["rec"]["ci95"], "f1_ci": ci["f1"]["ci95"],
        "roc_auc_ci": ci["roc_auc"]["ci95"],
        "csv_sha256": sha256_of(spec["csv"]),
    }
    if refit_scores is not None:
        rm = threshold_metrics(y, refit_scores)
        truth["refit"] = {"f1": rm["f1"], "rec": rm["rec"], "roc_auc": auc_point(y, refit_scores)}
    _UNIT_CACHE[unit] = truth
    return truth


_GROUPWISE_CACHE: dict | None = None


def recompute_groupwise() -> dict:
    """文本模态 groupwise OOF：从已提交逐样本 csv 复算（阈值 0.5）。"""
    global _GROUPWISE_CACHE
    if _GROUPWISE_CACHE is not None:
        return _GROUPWISE_CACHE
    y, s = _load_groupwise_ys()
    m = threshold_metrics(y, s)
    _GROUPWISE_CACHE = {
        "n": m["n"], "acc": m["acc"], "prec": m["prec"], "rec": m["rec"], "f1": m["f1"],
        "roc_auc": auc_point(y, s),
        "positive_rate": float((y == 1).mean()),
    }
    return _GROUPWISE_CACHE


def _load_groupwise_ys() -> tuple[np.ndarray, np.ndarray]:
    rows = GROUPWISE_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]
    y = np.array([int(ln.split(",")[0]) for ln in rows], dtype=np.int64)
    s = np.array([float(ln.split(",")[2]) for ln in rows], dtype=np.float64)  # p_groupwise
    return y, s


# ─────────────── ROUND_33 (P1 校准)：校准/DCA 数字的独立复算 ───────────────
# 边界：只读 v1_33/calibration_analysis.json 与已提交逐样本 csv；
# 点估计刻意用**另一套算法路径**（ECE 用显式区间遍历而非 searchsorted；
# slope 用 Nelder-Mead 直接最小化 logloss 而非 Newton/IRLS），
# 与 v1_33/calibration_lib.py 互为交叉验证。

CALIBRATION_JSON = Path(__file__).resolve().parent / "v1_33" / "calibration_analysis.json"
SAFETY_NET_JSON = Path(__file__).resolve().parent / "v1_36" / "safety_net_analysis.json"

CALIB_UNITS: dict[str, dict] = {
    "text_groupwise_oof": {"csv": GROUPWISE_CSV, "kind": "groupwise", "role": "citable"},
    "physio_current_split": {
        "csv": UNITS["physio_v2"]["csv"], "kind": "csv",
        "role": "citable_secondary", "has_refit": UNITS["physio_v2"]["has_refit"],
    },
    "text_ood_strict": {
        "csv": UNITS["text_ood"]["csv"], "kind": "csv",
        "role": "stress_only", "has_refit": UNITS["text_ood"]["has_refit"],
    },
    "physio_kaggle": {
        "csv": UNITS["physio_kaggle"]["csv"], "kind": "csv",
        "role": "stress_only", "has_refit": UNITS["physio_kaggle"]["has_refit"],
    },
}

CALIB_N_BINS = 10


def _indep_brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _indep_ece(y: np.ndarray, p: np.ndarray, n_bins: int = CALIB_N_BINS) -> float:
    """等宽箱 ECE，[lo, hi) 归属、末箱闭区间。

    与 calibration_lib 的 searchsorted(edges, p, 'right')-1（即 (lo, hi] 归属）
    在箱边界上数学等价：p 恰等于边界值时两者归同一箱（见下表 p=0.1 → bin 1）。
    """
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = float(y.size)
    total = 0.0
    for k in range(n_bins):
        lo, hi = float(edges[k]), float(edges[k + 1])
        mask = (p >= lo) & (p < hi) if k < n_bins - 1 else (p >= lo) & (p <= hi)
        if not mask.any():
            continue
        total += (float(mask.sum()) / n) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(total)


def _indep_slope_intercept(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """Platt slope / intercept：Nelder-Mead 直接最小化 logloss（与库的 Newton 不同路径）。"""
    from scipy.optimize import minimize

    pc = np.clip(p, 1e-12, 1.0 - 1e-12)
    x = np.log(pc / (1.0 - pc))

    def nll(beta):
        eta = beta[0] + beta[1] * x
        return float(np.sum(np.logaddexp(0.0, eta) - y * eta))

    res = minimize(
        nll, x0=np.zeros(2), method="Nelder-Mead",
        options={"xatol": 1e-12, "fatol": 1e-14, "maxiter": 20000},
    )
    return float(res.x[1]), float(res.x[0])


def _load_calib_ys(unit: str) -> tuple[np.ndarray, np.ndarray]:
    spec = CALIB_UNITS[unit]
    if spec["kind"] == "groupwise":
        y, s = _load_groupwise_ys()
        return y.astype(np.float64), s.astype(np.float64)
    y, s, _, _ = read_predictions_csv(spec["csv"], refit=spec["has_refit"])
    return y.astype(np.float64), s.astype(np.float64)


# ─────────────── ROUND_36 (P1 漏报安全网)：双阈值规则的独立复算 ───────────────
# 独立路径：用 flatnonzero + len 而非库的布尔 mask 求和；规则参数从 v1_36 产物读。


def _indep_safety_net(y: np.ndarray, p: np.ndarray, t_low: float, t_high: float) -> dict:
    i_alert = np.flatnonzero(p >= t_high)
    i_sn = np.flatnonzero((p >= t_low) & (p < t_high))
    i_low = np.flatnonzero(p < t_low)
    tp = int(np.sum(y[i_alert] == 1.0))
    fp = int(len(i_alert) - tp)
    sn_caught = int(np.sum(y[i_sn] == 1.0))
    sn_total = int(len(i_sn))
    n = int(y.size)
    P = int(np.sum(y == 1.0))
    return {
        "tp": tp,
        "fp": fp,
        "sn_total": sn_total,
        "sn_caught": sn_caught,
        "net_recall": (tp + sn_caught) / P if P else float("nan"),
        "review_burden": (tp + fp + sn_total) / n,
        "alert_precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "sn_precision": sn_caught / sn_total if sn_total else float("nan"),
        "burden_identity": float(len(i_alert) + len(i_sn)) / n,
        "net_recall_identity": 1.0 - float(np.sum(y[i_low] == 1.0)) / P if P else float("nan"),
    }


def recompute_safety_net() -> dict:
    """从已提交 csv + 预设标准独立复算安全网工作点（不 import v1_36 的库）。"""
    y, p = _load_calib_ys("text_groupwise_oof")
    best: tuple | None = None
    best_m: dict | None = None
    n_feasible = 0
    t_high_grid = [round(0.05 * k, 2) for k in range(2, 13)]
    t_low_grid = [round(0.01 * k, 2) for k in range(1, 12)]
    for t_high in t_high_grid:
        for t_low in t_low_grid:
            if not (0.0 < t_low < t_high < 1.0):
                continue
            m = _indep_safety_net(y, p, t_low, t_high)
            if not (m["net_recall"] >= TARGET_NET_RECALL):
                continue
            n_feasible += 1
            key = (round(m["review_burden"], 12), -t_high, -t_low)
            if best is None or key < best:
                best = key
                best_m = {"t_low": t_low, "t_high": t_high, **m}
    out = {"feasible": best_m is not None, "n_feasible": n_feasible, "point": best_m}
    if best_m is not None:
        # 成本等价对照：单阈值直接下调到同一 t_low 的读数
        i_alert = np.flatnonzero(p >= best_m["t_low"])
        tp_low = int(np.sum(y[i_alert] == 1.0))
        out["single_at_t_low"] = {
            "threshold": best_m["t_low"],
            "recall": (tp_low / int(np.sum(y == 1.0))) if int(np.sum(y == 1.0)) else float("nan"),
            "precision": tp_low / len(i_alert) if len(i_alert) else float("nan"),
            "alert_rate": len(i_alert) / y.size,
        }
    return out


TARGET_NET_RECALL = 0.80


# ─────────────── ROUND_37 (P1 融合消融)：模态缺失翻转的独立复算 ───────────────
# 独立路径：直接调生产 FusionEngine 重算（不复用 v1_37 脚本的汇总逻辑），
# 并核验产物的汇总统计、worst case 与分层模式。


def recompute_ablation() -> dict:
    """从分数网格独立重算消融翻转统计（确定性穷举，无抽样）。"""
    import sys as _sys

    if str(BACKEND) not in _sys.path:
        _sys.path.insert(0, str(BACKEND))
    from app.ml.fusion_engine import DEFAULT_WEIGHTS as PROD_WEIGHTS
    from app.ml.fusion_engine import FusionEngine as ProdEngine

    engine = ProdEngine()
    grid = list(range(0, 101, 10))
    keep = {
        "drop_structured": ("text", "physiological"),
        "drop_text": ("structured", "physiological"),
        "drop_physiological": ("structured", "text"),
        "only_structured": ("structured",),
        "only_text": ("text",),
        "only_physiological": ("physiological",),
    }
    rows = []
    for s in grid:
        for t in grid:
            for p in grid:
                scores = {"structured": float(s), "text": float(t), "physiological": float(p)}
                full = int(engine.fuse(scores)["risk_level"])
                row = {"full": full, "spread": max(scores.values()) - min(scores.values())}
                for name, mods in keep.items():
                    row[name] = int(engine.fuse({m: scores[m] for m in mods})["risk_level"])
                rows.append(row)
    out: dict[str, object] = {"weights": dict(engine.weights), "n": len(rows)}
    for name in keep:
        deltas = np.array([r[name] - r["full"] for r in rows], dtype=np.int64)
        absd = np.abs(deltas)
        agree = np.array([r["spread"] < 20 for r in rows])
        conflict = np.array([r["spread"] >= 40 for r in rows])
        out[f"{name}_flip_rate"] = float((absd >= 1).mean())
        out[f"{name}_max_abs_delta"] = int(absd.max())
        out[f"{name}_agree_flip_rate"] = float((absd[agree] >= 1).mean()) if agree.any() else float("nan")
        out[f"{name}_agree_max_abs_delta"] = int(absd[agree].max()) if agree.any() else -1
        out[f"{name}_conflict_flip_rate"] = (
            float((absd[conflict] >= 1).mean()) if conflict.any() else float("nan")
        )
    # worst case：仅生理相对完整模态的 |Δ| 最大者
    worst = max(rows, key=lambda r: abs(r["only_physiological"] - r["full"]))
    out["worst_delta_only_physio"] = int(abs(worst["only_physiological"] - worst["full"]))
    out["worst_full_level"] = int(worst["full"])
    out["worst_only_physio_level"] = int(worst["only_physiological"])
    # 聚合：所有消融配置里最保守的两个数（供台账「一致层最大翻转」引用）
    out["agree_max_abs_delta"] = int(max(out[f"{n}_agree_max_abs_delta"] for n in keep))
    assert engine.weights == PROD_WEIGHTS
    return out


def _indep_net_benefit(y: np.ndarray, p: np.ndarray, thr: float) -> float:
    """DCA 净获益（独立实现）：TP/n − (FP/n)·(t/(1−t))。"""
    pred = p >= thr
    pos = y == 1.0
    n = float(y.size)
    tp = float((pred & pos).sum())
    fp = float((pred & ~pos).sum())
    return tp / n - (fp / n) * (thr / (1.0 - thr))


DCA_REPORT_THRESHOLDS = (0.05, 0.30, 0.50)


def recompute_calibration() -> dict:
    """从已提交 csv 独立复算四个单元的校准点估计。"""
    out: dict[str, dict] = {}
    for unit in CALIB_UNITS:
        y, p = _load_calib_ys(unit)
        slope, intercept = _indep_slope_intercept(y, p)
        entry = {
            "n": int(y.size),
            "positive_rate": float(y.mean()),
            "brier": _indep_brier(y, p),
            "ece": _indep_ece(y, p),
            "calibration_slope": slope,
            "calibration_intercept": intercept,
        }
        for thr in DCA_REPORT_THRESHOLDS:
            entry[f"nb_{thr:g}"] = _indep_net_benefit(y, p, thr)
        out[unit] = entry
    return out


def recompute_calibration_ci(unit: str, B: int = BOOTSTRAP_B, seed: int = BOOTSTRAP_SEED) -> dict:
    """仅对**主口径** text_groupwise_oof 独立复算 bootstrap CI（按 group 重采样）。

    与 v1_33/calibration_analysis.py 同源：同 seed、同 `rng.randint(0, G, G)` 抽样逻辑。
    其它三个单元只做结构校验（见 check_calibration_artifact），理由：
    - physio_current_split n=157：CI 必然极宽，点估计已足以外推结论；
    - 两个 stress_only 单元不作引用，CI 的精度无消费方。
    """
    if unit != "text_groupwise_oof":
        raise ValueError(f"CI 独立复算仅限 text_groupwise_oof，收到 {unit!r}")
    y, p = _load_calib_ys(unit)
    groups = np.array(
        [ln.split(",")[1] for ln in GROUPWISE_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]],
        dtype=object,
    )
    uniq = np.unique(groups)
    G = len(uniq)
    pos = {gg: i for i, gg in enumerate(uniq)}
    row_g = np.array([pos[gg] for gg in groups], dtype=np.int64)
    rng = np.random.RandomState(seed)
    samples = {"brier": [], "ece": []}
    for _ in range(B):
        pick = rng.randint(0, G, G)
        cnt = np.bincount(pick, minlength=G)
        sel = np.repeat(np.arange(y.size), cnt[row_g])
        yb, pb = y[sel], p[sel]
        samples["brier"].append(_indep_brier(yb, pb))
        samples["ece"].append(_indep_ece(yb, pb))
    return {
        k: {"ci95": [float(np.percentile(np.array(v), 2.5)), float(np.percentile(np.array(v), 97.5))]}
        for k, v in samples.items()
    }


_GROUPWISE_CI_CACHE: dict | None = None


def recompute_groupwise_ci() -> dict:
    """文本模态 groupwise 的**分组级** bootstrap 95% CI（按 group 重采样，B=10000, seed=42）。

    与 v1_30/groupwise_ci.py 同一抽样序列（按 group 排序后逐次 rng.randint(0, G, G)），
    只取各指标 ci95；点估计复用 recompute_groupwise。
    """
    global _GROUPWISE_CI_CACHE
    if _GROUPWISE_CI_CACHE is not None:
        return _GROUPWISE_CI_CACHE
    from scipy.stats import rankdata

    y, s = _load_groupwise_ys()
    g = np.array([ln.split(",")[1] for ln in GROUPWISE_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]])
    order = np.argsort(g, kind="mergesort")
    ys, ss, gs = y[order], s[order], g[order]
    uniq = np.unique(g)
    G = len(uniq)
    pos = {gg: i for i, gg in enumerate(uniq)}
    row_g = np.array([pos[gg] for gg in gs], dtype=np.int64)

    def _m(yv: np.ndarray, sv: np.ndarray) -> tuple[float, float, float, float]:
        pred = sv >= DECISION
        posm = yv == 1
        tp = int((pred & posm).sum()); fp = int((pred & ~posm).sum()); fn = int((~pred & posm).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        npos = int(posm.sum()); nneg = len(yv) - npos
        if npos == 0 or nneg == 0:
            return f1, float("nan"), rec, prec
        r = rankdata(sv, method="average")
        auc = float((r[posm].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))
        return f1, auc, rec, prec

    rng = np.random.RandomState(BOOTSTRAP_SEED)
    samples = {k: [] for k in ("f1", "roc_auc", "rec", "prec")}
    for _ in range(BOOTSTRAP_B):
        pick = rng.randint(0, G, G)
        cnt = np.bincount(pick, minlength=G)
        idx = np.repeat(np.arange(len(ys)), cnt[row_g])
        f1, auc, rec, prec = _m(ys[idx], ss[idx])
        if not np.isnan(auc):
            samples["f1"].append(f1); samples["roc_auc"].append(auc)
            samples["rec"].append(rec); samples["prec"].append(prec)
    out = {}
    for k, vals in samples.items():
        arr = np.array(vals, dtype=np.float64)
        out[k] = [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
    _GROUPWISE_CI_CACHE = out
    return out


# ────────────────────────── 融合权重敏感性 ──────────────────────────


def _ast_dict_assignment(path: Path, const_name: str) -> ast.Dict | None:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id == const_name and isinstance(node.value, ast.Dict):
                return node.value
    return None


def _ast_const_dict(d: ast.Dict) -> dict:
    return {
        k.value: v.value
        for k, v in zip(d.keys, d.values)
        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
    }


def production_fusion_facts() -> dict:
    """从源码 AST 取生产融合权重与融合档阈值（不 import app，避免副作用）。"""
    weights_node = _ast_dict_assignment(FUSION_ENGINE_PY, "DEFAULT_WEIGHTS")
    assert weights_node is not None, "fusion_engine.py 里找不到 DEFAULT_WEIGHTS"
    weights = _ast_const_dict(weights_node)
    thr_node = _ast_dict_assignment(RISK_THRESHOLDS_PY, "MODALITY_RISK_THRESHOLDS")
    assert thr_node is not None, "risk_thresholds.py 里找不到 MODALITY_RISK_THRESHOLDS"
    fusion_thr = None
    for k, v in zip(thr_node.keys, thr_node.values):
        if isinstance(k, ast.Constant) and k.value == "fusion" and isinstance(v, ast.Dict):
            fusion_thr = _ast_const_dict(v)
    assert fusion_thr is not None, "MODALITY_RISK_THRESHOLDS 里没有 fusion 档"
    return {"weights": weights, "bands": fusion_thr}


def _level(score: float, bands: dict) -> int:
    if score >= bands["critical"]:
        return 4
    if score >= bands["high"]:
        return 3
    if score >= bands["moderate"]:
        return 2
    if score >= bands["mild"]:
        return 1
    return 0


def recompute_sensitivity(prod: dict) -> dict:
    """复算 fusion_weight_sensitivity.csv：加权平均公式 + 等级阈值表 + 权重和。"""
    lines = SENSITIVITY_CSV.read_text(encoding="utf-8").strip().splitlines()
    header = lines[0].split(",")
    assert header == ["w_structured", "w_text", "w_physio", "case", "risk_score", "risk_level"], header
    rows = []
    for ln in lines[1:]:
        w_s, w_t, w_p, case, score, level = ln.split(",")
        m = re.match(r"^[a-z_\-]+\((\d+)/(\d+)/(\d+)\)$", case)
        assert m, f"case 列无法解析：{case!r}"
        s_in, t_in, p_in = (int(g) for g in m.groups())
        rows.append({
            "w_s": float(w_s), "w_t": float(w_t), "w_p": float(w_p),
            "case": case.split("(")[0], "inputs": (s_in, t_in, p_in),
            "score": float(score), "level": int(level),
        })
    out: dict = {"rows": rows, "by_case": {}}
    for r in rows:
        # 权重和（csv 的 w_text/w_physio 是 4 位小数，容差放到 1e-3）
        assert abs(r["w_s"] + r["w_t"] + r["w_p"] - 1.0) <= 1e-3, f"权重和不为 1：{r}"
        s_in, t_in, p_in = r["inputs"]
        expect = round(r["w_s"] * s_in + r["w_t"] * t_in + r["w_p"] * p_in, 2)
        assert abs(expect - r["score"]) <= 5e-3 + 1e-9, (
            f"risk_score 与加权平均不符：{r['case']} w={r['w_s']} 记录 {r['score']} vs 复算 {expect}"
        )
        expect_level = _level(r["score"], prod["bands"])
        assert expect_level == r["level"], (
            f"risk_level 与阈值表不符：{r['case']} score={r['score']} 记录 {r['level']} vs 复算 {expect_level}"
        )
        out["by_case"].setdefault(r["case"], []).append((r["w_s"], r["level"]))
    # 生产权重行必须在扫描范围内
    pw = prod["weights"]
    prod_row = [r for r in rows
                if abs(r["w_s"] - pw["structured"]) < 1e-9
                and abs(r["w_t"] - pw["text"]) < 1e-9
                and abs(r["w_p"] - pw["physiological"]) < 1e-9]
    assert prod_row, f"敏感性扫描缺少生产权重行 {pw}"
    return out


# ────────────────────────── 文档解析 ──────────────────────────

NUM = r"\d+(?:\.\d+)?"
LEDGER_ROW = re.compile(
    r"^\|\s*(?P<id>[CSX]-\d+)\s*\|\s*(?P<metric>[^|]+?)\s*\|\s*(?P<point>[^|]+?)\s*\|\s*(?P<ci>[^|]+?)\s*\|"
)
CHAPTER_MAIN = re.compile(
    r"^\|\s*(?P<label>Accuracy|Precision|Recall|F1|ROC AUC)\s*\|\s*(?P<point>" + NUM + r")\s*\|\s*\[\s*(?P<lo>" + NUM + r")\s*,\s*(?P<hi>" + NUM + r")\s*\]\s*\|"
)
CHAPTER_CM = re.compile(r"TP=(\d+)\s*/\s*FP=(\d+)\s*/\s*FN=(\d+)\s*/\s*TN=(\d+)")
CHAPTER_REFIT = re.compile(
    r"^\|\s*(?P<label>生产路径[^|]*?|诊断对照[^|]*?)\s*\|\s*(?P<f1>" + NUM + r")\s*\|\s*(?P<rec>" + NUM + r")\s*\|\s*(?P<auc>" + NUM + r")\s*\|"
)
CHAPTER_TRANSFER = re.compile(
    r"^\|\s*(?P<unit>[^|]*(?:Kaggle|OOD)[^|]*?)\s*\|\s*(?P<n>\d+)\s*\|\s*(?P<f1p>" + NUM + r")\s*\[\s*(?P<f1lo>" + NUM + r")\s*,\s*(?P<f1hi>" + NUM + r")\s*\]\s*\|\s*"
    r"(?P<aucp>" + NUM + r")\s*\[\s*(?P<auclo>" + NUM + r")\s*,\s*(?P<auchi>" + NUM + r")\s*\]\s*\|\s*"
    r"(?P<tp>\d+)\s*/\s*(?P<fp>\d+)\s*/\s*(?P<fn>\d+)\s*/\s*(?P<tn>\d+)\s*\|"
)
CHAPTER_GROUPWISE = re.compile(r"groupwise[^|\n]*?(\d\.\d{4})")
CHAPTER_GW_TABLE = re.compile(
    r"^\|\s*(?P<label>(?:F1|ROC AUC|Recall|Precision))（跨被试）\s*\|\s*(?P<point>" + NUM + r")\s*\|\s*\[\s*(?P<lo>" + NUM + r")\s*,\s*(?P<hi>" + NUM + r")\s*\]\s*\|"
)
CLAIM_REF = re.compile(r"[CDSXB]-\d+")
# 黑名单 token：n=139 那组（优化版 + 原始版整行）+ registry 0.9530 + bootstrap 均值误记 0.8527
FORBIDDEN = [
    (re.compile(r"(?<![\d.])0\.8542(?![\d])"), "n=139 优化版 F1（metrics.json / upgrade_baseline:19）"),
    (re.compile(r"(?<![\d.])0\.8541667(?![\d])"), "n=139 优化版 F1 全精度"),
    (re.compile(r"(?<![\d.])0\.9653(?![\d])"), "n=139 优化版 AUC"),
    (re.compile(r"(?<![\d.])0\.965(?![\d])"), "n=139 优化版 AUC（三位形式）"),
    (re.compile(r"(?<![\d.])0\.8993(?![\d])"), "n=139 优化版 Accuracy"),
    (re.compile(r"(?<![\d.])0\.9318(?![\d])"), "n=139 优化版 Precision"),
    (re.compile(r"(?<![\d.])0\.7885(?![\d])"), "n=139 优化版 Recall"),
    (re.compile(r"(?<![\d.])0\.7243(?![\d])"), "n=139 原始版 F1"),
    (re.compile(r"(?<![\d.])0\.6600(?![\d])"), "n=139 原始版 Accuracy"),
    (re.compile(r"(?<![\d.])0\.6091(?![\d])"), "n=139 原始版 Precision"),
    (re.compile(r"(?<![\d.])0\.8933(?![\d])"), "n=139 原始版 Recall"),
    (re.compile(r"(?<![\d.])0\.9530(?![\d])"), "registry test_f1（第三套数字，hidden_dims 与实际不符）"),
    (re.compile(r"(?<![\d.])0\.8527(?![\d])"), "bootstrap 均值被误记为 point"),
    (re.compile(r"(?<![\d.,])139(?![\d.,])"), "n=139 测试集样本量（不可复现）"),
]
# 同行出现拒绝/历史标记时，黑名单数字允许出现（黑名单节、问答的拒绝性引用）
REJECT = re.compile(
    r"不引用|禁用|不得|不可复现|❌|历史口径|已废弃|superseded|SUPERSED|黑名单|误记|虚高|无统计意义|不作为|不可比|已取代"
)
# ≥3 位小数的数字必须同行带台账编号或拒绝标记（防「QA/局限里凭空出现一个数」）
FINE_NUM = re.compile(r"(?<![\d.])\d+\.\d{3,}(?![\d])")

REQUIRED_QA_MARKERS = (
    "泛化",      # Q1 高 AUC 为何不主张泛化
    "Recall",    # Q2 Recall 0.60
    "n = 157",   # Q3 样本量
    "0.85",      # Q4 旧口径（问题用约数，答案给黑名单）
    "泄漏",      # Q5 文本 F1 0.986
    "外部",      # Q6 为何无正向迁移
    "复现",      # Q7 可复现性
)


# ────────────────────────── 台账期望表（id → 真值来源） ──────────────────────────
# kind:
#   unit      → (unit, metric, part)   part: "point" | "cm"；复算自已提交 csv，CI 取同指标 ci95
#   refit     → (metric,)              诊断列复算
#   groupwise → (field,)               文本 groupwise csv 复算
#   dataset   → (field,)               json dataset / meta / groupwise 行数
#   sens      → (claim,)               敏感性 csv 复算
#   crossdoc  → (literal,)             TRANSFER_MATRIX.md 字面量对齐
EXPECTED: dict[str, tuple] = {
    "C-01": ("unit", "physio_v2", "acc", "point"),
    "C-02": ("unit", "physio_v2", "prec", "point"),
    "C-03": ("unit", "physio_v2", "rec", "point"),
    "C-04": ("unit", "physio_v2", "f1", "point"),
    "C-05": ("unit", "physio_v2", "roc_auc", "point"),
    "C-06": ("unit", "physio_v2", "cm", "cm"),
    "C-07": ("refit", "f1"),
    "C-08": ("refit", "rec"),
    "C-09": ("refit", "roc_auc"),
    "C-10": ("unit", "physio_kaggle", "acc", "point"),
    "C-11": ("unit", "physio_kaggle", "f1", "point"),
    "C-12": ("unit", "physio_kaggle", "roc_auc", "point"),
    "C-13": ("unit", "physio_kaggle", "prec", "point"),
    "C-14": ("unit", "physio_kaggle", "rec", "point"),
    "C-15": ("unit", "physio_kaggle", "cm", "cm"),
    "C-16": ("unit", "text_ood", "acc", "point"),
    "C-17": ("unit", "text_ood", "prec", "point"),
    "C-18": ("unit", "text_ood", "rec", "point"),
    "C-19": ("unit", "text_ood", "f1", "point"),
    "C-20": ("unit", "text_ood", "roc_auc", "point"),
    "C-21": ("unit", "text_ood", "cm", "cm"),
    "C-22": ("groupwise", "f1"),
    "C-23": ("groupwise", "roc_auc"),
    "C-24": ("groupwise", "rec"),
    "C-25": ("groupwise", "prec"),
    # ROUND_33 (P1 校准)：spec[3] == "ci" 时 CI 也参与校验（主口径独立复算，其余结构校验）
    "C-26": ("calib", "text_groupwise_oof", "brier", "ci"),
    "C-27": ("calib", "text_groupwise_oof", "ece", "ci"),
    "C-28": ("calib", "text_groupwise_oof", "calibration_slope", "point"),
    "C-29": ("calib", "physio_current_split", "ece", "ci"),
    "C-30": ("calib", "physio_kaggle", "brier", "ci"),
    "C-31": ("calib", "text_ood_strict", "brier", "ci"),
    # ROUND_33：DCA 代表点净获益（无 CI，method 已声明）
    "C-32": ("calib_dca", "text_groupwise_oof", "nb_0.5", "point"),
    "C-33": ("calib_dca", "text_groupwise_oof", "nb_0.05", "point"),
    # ROUND_36（P1 漏报安全网）：spec[3]=="ci" 时 CI 也校验
    "C-34": ("safetynet", "text_groupwise_oof", "net_recall", "ci"),
    "C-35": ("safetynet", "text_groupwise_oof", "review_burden", "point"),
    "C-36": ("safetynet", "text_groupwise_oof", "sn_precision", "point"),
    # ROUND_36：双阈值 vs 单阈值下调的精确率对比（「更可信但不省钱」的两个读数）
    "C-37": ("safetynet", "text_groupwise_oof", "alert_precision", "point"),
    "C-38": ("safetynet_single", "precision_at_t_low", "point"),
    "X-01": ("sens", "agree_low"),
    "X-02": ("sens", "agree_high"),
    "X-03": ("sens", "mid_all"),
    "X-04": ("sens", "conflict_s-low_t-high"),
    "X-05": ("sens", "conflict_s-high_t-low"),
    "X-06": ("sens", "production_row"),
    # ROUND_37（P1 融合消融）：模态缺失下的等级翻转（确定性穷举，无 CI）
    "X-07": ("ablation", "agree_max_abs_delta"),
    "X-08": ("ablation", "only_physiological_conflict_flip_rate"),
    "X-09": ("ablation", "worst_delta_only_physio"),
    "S-01": ("dataset", "depresjon_rows"),
    "S-02": ("dataset", "kaggle_rows"),
    "S-03": ("dataset", "ood_rows"),
    "S-04": ("crossdoc", "682"),
    "S-05": ("dataset", "groupwise_rows"),
    "S-06": ("dataset", "split"),
    "S-07": ("dataset", "test_n"),
    "S-08": ("dataset", "class_counts"),
}


def build_truth() -> dict:
    """复算一切，返回 {claim_id: 真值}（数值或字符串）。"""
    units = {u: recompute_unit(u) for u in UNITS}
    gw = recompute_groupwise()
    prod = production_fusion_facts()
    sens = recompute_sensitivity(prod)

    truth: dict = {}
    for cid, spec in EXPECTED.items():
        kind = spec[0]
        if kind == "unit":
            _, unit, metric, part = spec
            t = units[unit]
            if part == "point":
                truth[cid] = t[metric]
            else:
                truth[cid] = f"TP={t['TP']} / FP={t['FP']} / FN={t['FN']} / TN={t['TN']}"
        elif kind == "refit":
            truth[cid] = units["physio_v2"]["refit"][spec[1]]
        elif kind == "groupwise":
            truth[cid] = gw[spec[1]]
        elif kind == "calib":
            calib = recompute_calibration()
            unit, metric, part = spec[1], spec[2], spec[3]
            truth[cid] = calib[unit][metric]
        elif kind == "calib_dca":
            calib = recompute_calibration()
            truth[cid] = calib[spec[1]][spec[2]]
        elif kind == "safetynet":
            sn = recompute_safety_net()
            if not sn["feasible"]:
                raise AssertionError("安全网工作点不可达（独立复算）⇒ 台账 C-34~C-36 失去依据")
            truth[cid] = sn["point"][spec[2]]
        elif kind == "safetynet_single":
            sn = recompute_safety_net()
            if not sn["feasible"]:
                raise AssertionError("安全网工作点不可达 ⇒ 成本等价对照失去依据")
            truth[cid] = sn["single_at_t_low"]["precision"]
        elif kind == "ablation":
            truth[cid] = recompute_ablation()[spec[1]]
        elif kind == "dataset":
            field = spec[1]
            pj = json.loads(UNITS["physio_v2"]["json"].read_text(encoding="utf-8"))
            kj = json.loads(UNITS["physio_kaggle"]["json"].read_text(encoding="utf-8"))
            tj = json.loads(UNITS["text_ood"]["json"].read_text(encoding="utf-8"))
            if field == "depresjon_rows":
                truth[cid] = pj["dataset"]["rows"]
            elif field == "kaggle_rows":
                truth[cid] = kj["dataset"]["rows"]
            elif field == "ood_rows":
                truth[cid] = tj["dataset"]["rows"]
            elif field == "groupwise_rows":
                truth[cid] = gw["n"]
            elif field == "split":
                sp = pj["dataset"]["split"]
                truth[cid] = f"{sp['train']} / {sp['val']} / {sp['test']}"
            elif field == "test_n":
                truth[cid] = pj["meta"]["n"]
            elif field == "class_counts":
                cc = pj["dataset"]["class_counts"]
                truth[cid] = f"{cc['0']} / {cc['1']}"
        elif kind == "sens":
            claim = spec[1]
            if claim == "production_row":
                w = prod["weights"]
                truth[cid] = f"{w['structured']:g}/{w['text']:g}/{w['physiological']:g}"
            else:
                pairs = sens["by_case"][claim]
                levels = [lv for _, lv in pairs]
                flip = next((w for w, lv in pairs if lv != levels[0]), None)
                if flip is None:
                    truth[cid] = f"{levels[0]} 级（{len(pairs)}/{len(pairs)} 行）"
                else:
                    truth[cid] = f"{levels[0]}→{levels[-1]} @{flip:g}"
        elif kind == "crossdoc":
            literal = spec[1]
            matrix = TRANSFER_MATRIX.read_text(encoding="utf-8")
            if literal not in matrix:
                raise AssertionError(f"TRANSFER_MATRIX.md 里找不到字面量 {literal}（跨文档对齐失败）")
            truth[cid] = int(literal)
    return truth


# ────────────────────────── 比对工具 ──────────────────────────


def ndec(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def tol_for(text: str) -> float:
    """展示精度容差：半个末位 + 1e-12。"""
    return 0.5 * 10.0 ** (-ndec(text)) + 1e-12


def check_equal(name: str, doc_value: float, truth_value: float, tol: float, failures: list[str]) -> None:
    if abs(doc_value - truth_value) > tol:
        failures.append(f"[{name}] 文档值 {doc_value} vs 复算真值 {truth_value}（容差 {tol:g}）")


def same_claim_text(doc: str, truth: str) -> bool:
    """字符串型登记项的相等判定：忽略空白；数字按数值比（"0.30" == "0.3"）。"""
    a = re.sub(r"\s+", "", doc)
    b = re.sub(r"\s+", "", truth)
    if a == b:
        return True
    toks_a = re.split(r"(\d+(?:\.\d+)?)", a)
    toks_b = re.split(r"(\d+(?:\.\d+)?)", b)
    if len(toks_a) != len(toks_b):
        return False
    for x, y in zip(toks_a, toks_b):
        if re.fullmatch(r"\d+(?:\.\d+)?", x):
            if float(x) != float(y):
                return False
        elif x != y:
            return False
    return True


def check_ledger(truth: dict, failures: list[str]) -> None:
    if not LEDGER.exists():
        failures.append(f"缺少 {LEDGER}")
        return
    seen: dict[str, tuple[str, str, int]] = {}
    for lineno, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        m = LEDGER_ROW.match(line)
        if m:
            seen[m.group("id")] = (m.group("point"), m.group("ci"), lineno)
    missing = sorted(set(EXPECTED) - set(seen))
    extra = sorted(set(seen) - set(EXPECTED))
    if missing:
        failures.append(f"台账缺少登记行：{missing}")
    if extra:
        failures.append(f"台账有未登记/无产物支撑的行：{extra}")
    units = {u: recompute_unit(u) for u in UNITS}
    for cid in sorted(set(EXPECTED) & set(seen)):
        point, ci, lineno = seen[cid]
        t = truth[cid]
        where = f"台账 {cid}（第 {lineno} 行）"
        spec = EXPECTED[cid]
        if isinstance(t, str):
            if not same_claim_text(point, t):
                failures.append(f"[{where}] 文档值 {point!r} vs 复算真值 {t!r}")
        else:
            check_equal(where, float(point), float(t), tol_for(point), failures)
        # CI：unit·point 与 groupwise 类有 CI；其余必须写「—」
        if spec[0] == "unit" and spec[3] == "point":
            _, unit, metric, _ = spec
            lo_truth, hi_truth = units[unit][f"{metric}_ci"]
            pair = re.findall(NUM, ci)
            if len(pair) != 2:
                failures.append(f"[{where}] CI 单元格无法解析为两个数：{ci!r}")
            else:
                check_equal(f"{where} CI 下界", float(pair[0]), lo_truth, tol_for(pair[0]), failures)
                check_equal(f"{where} CI 上界", float(pair[1]), hi_truth, tol_for(pair[1]), failures)
        elif spec[0] == "groupwise":
            gw_ci = recompute_groupwise_ci()
            lo_truth, hi_truth = gw_ci[spec[1]]
            pair = re.findall(NUM, ci)
            if len(pair) != 2:
                failures.append(f"[{where}] groupwise CI 单元格无法解析为两个数：{ci!r}")
            else:
                check_equal(f"{where} CI 下界", float(pair[0]), lo_truth, tol_for(pair[0]), failures)
                check_equal(f"{where} CI 上界", float(pair[1]), hi_truth, tol_for(pair[1]), failures)
        elif spec[0] == "calib":
            if not CALIBRATION_JSON.exists():
                failures.append(f"缺少校准分析产物 {CALIBRATION_JSON}")
                continue
            calib_json = json.loads(CALIBRATION_JSON.read_text(encoding="utf-8"))
            u = calib_json["units"][spec[1]]
            if spec[3] == "point":
                # slope/intercept 无 CI：单元格必须是「—」
                if ci.strip() not in ("—", "-", ""):
                    failures.append(f"[{where}] 点估计类登记的 CI 单元格应为「—」，实际为 {ci!r}")
            else:
                pair = re.findall(NUM, ci)
                if len(pair) != 2:
                    failures.append(f"[{where}] CI 单元格无法解析为两个数：{ci!r}")
                else:
                    jlo, jhi = u["metrics"][spec[2]]["ci95"]
                    check_equal(f"{where} CI 下界", float(pair[0]), jlo, tol_for(pair[0]), failures)
                    check_equal(f"{where} CI 上界", float(pair[1]), jhi, tol_for(pair[1]), failures)
                    # 主口径：CI 还必须与独立复算一致（同源抽样序列 + 独立指标实现）
                    if spec[1] == "text_groupwise_oof":
                        indep = recompute_calibration_ci(spec[1])
                        check_equal(
                            f"{where} CI 下界（独立复算）", jlo, indep[spec[2]]["ci95"][0], 1e-6, failures
                        )
                        check_equal(
                            f"{where} CI 上界（独立复算）", jhi, indep[spec[2]]["ci95"][1], 1e-6, failures
                        )
        elif spec[0] == "calib_dca":
            # DCA 代表点净获益：与产物 dca.net_benefit_model 在对应阈值处对拍（无 CI）
            if not CALIBRATION_JSON.exists():
                failures.append(f"缺少校准分析产物 {CALIBRATION_JSON}")
                continue
            u = json.loads(CALIBRATION_JSON.read_text(encoding="utf-8"))["units"][spec[1]]
            thr = float(spec[2].split("_")[1])
            idx = u["dca"]["thresholds"].index(thr)
            jval = u["dca"]["net_benefit_model"][idx]
            if ci.strip() not in ("—", "-", ""):
                failures.append(f"[{where}] DCA 代表点的 CI 单元格应为「—」，实际为 {ci!r}")
            # 点估计的比对由上方 truth 分支完成（独立复算 vs 文档），此处补产物层校验
            check_equal(f"[{where}] 产物值", float(point), float(jval), tol_for(point), failures)
        elif spec[0] == "safetynet":
            if not SAFETY_NET_JSON.exists():
                failures.append(f"缺少安全网产物 {SAFETY_NET_JSON}")
                continue
            sn_doc = json.loads(SAFETY_NET_JSON.read_text(encoding="utf-8"))
            pt = sn_doc["operating_point"]["operating_point"]
            if spec[3] == "point":
                if ci.strip() not in ("—", "-", ""):
                    failures.append(f"[{where}] 点估计类登记的 CI 单元格应为「—」，实际为 {ci!r}")
            else:
                pair = re.findall(NUM, ci)
                if len(pair) != 2:
                    failures.append(f"[{where}] CI 单元格无法解析为两个数：{ci!r}")
                else:
                    jlo, jhi = sn_doc["operating_point"]["net_recall_ci95"]["ci95"]
                    check_equal(f"{where} CI 下界", float(pair[0]), jlo, tol_for(pair[0]), failures)
                    check_equal(f"{where} CI 上界", float(pair[1]), jhi, tol_for(pair[1]), failures)
        elif spec[0] == "safetynet_single":
            if not SAFETY_NET_JSON.exists():
                failures.append(f"缺少安全网产物 {SAFETY_NET_JSON}")
                continue
            sn_doc = json.loads(SAFETY_NET_JSON.read_text(encoding="utf-8"))
            single = sn_doc["cost_equivalence"]["single_threshold_at_t_low"]
            if ci.strip() not in ("—", "-", ""):
                failures.append(f"[{where}] 点估计类登记的 CI 单元格应为「—」，实际为 {ci!r}")
            check_equal(f"[{where}] 产物值", float(point), float(single["precision"]),
                        tol_for(point), failures)
        elif ci.strip() not in ("—", "-", ""):
            failures.append(f"[{where}] 非单元类登记的 CI 单元格应为「—」，实际为 {ci!r}")


def check_chapter(failures: list[str]) -> None:
    if not CHAPTER.exists():
        failures.append(f"缺少 {CHAPTER}")
        return
    text = CHAPTER.read_text(encoding="utf-8")
    lines = text.splitlines()
    units = {u: recompute_unit(u) for u in UNITS}
    gw = recompute_groupwise()

    # 1) 主表（域内五指标 + CI）
    found = {}
    for line in lines:
        m = CHAPTER_MAIN.match(line)
        if m:
            found[m.group("label")] = m
    for label, key in METRIC_LABELS.items():
        if label not in found:
            failures.append(f"结果章节主表缺少 {label} 行")
            continue
        m = found[label]
        t = units["physio_v2"]
        check_equal(f"章节主表 {label}", float(m.group("point")), t[key], tol_for(m.group("point")), failures)
        lo, hi = t[f"{key}_ci"]
        check_equal(f"章节主表 {label} CI 下界", float(m.group("lo")), lo, tol_for(m.group("lo")), failures)
        check_equal(f"章节主表 {label} CI 上界", float(m.group("hi")), hi, tol_for(m.group("hi")), failures)

    # 2) 混淆矩阵（域内）
    cm = CHAPTER_CM.search(text)
    if not cm:
        failures.append("结果章节找不到混淆矩阵行（TP/FP/FN/TN）")
    else:
        t = units["physio_v2"]
        got = [int(g) for g in cm.groups()]
        want = [t["TP"], t["FP"], t["FN"], t["TN"]]
        if got != want:
            failures.append(f"章节混淆矩阵 {got} vs 复算 {want}")

    # 3) 诊断对照表（生产 vs 重拟合 scaler）
    for line in lines:
        m = CHAPTER_REFIT.match(line)
        if not m:
            continue
        if m.group("label").startswith("生产路径"):
            base = units["physio_v2"]
            check_equal("诊断表·生产 F1", float(m.group("f1")), base["f1"], tol_for(m.group("f1")), failures)
            check_equal("诊断表·生产 Recall", float(m.group("rec")), base["rec"], tol_for(m.group("rec")), failures)
            check_equal("诊断表·生产 AUC", float(m.group("auc")), base["roc_auc"], tol_for(m.group("auc")), failures)
        else:
            t = units["physio_v2"]["refit"]
            check_equal("诊断表·重拟合 F1", float(m.group("f1")), t["f1"], tol_for(m.group("f1")), failures)
            check_equal("诊断表·重拟合 Recall", float(m.group("rec")), t["rec"], tol_for(m.group("rec")), failures)
            check_equal("诊断表·重拟合 AUC", float(m.group("auc")), t["roc_auc"], tol_for(m.group("auc")), failures)

    # 4) 迁移表（两个降级单元）
    for line in lines:
        m = CHAPTER_TRANSFER.match(line)
        if not m:
            continue
        unit_key = "physio_kaggle" if "Kaggle" in m.group("unit") else "text_ood"
        t = units[unit_key]
        tag = f"迁移表[{unit_key}]"
        if int(m.group("n")) != t["n"]:
            failures.append(f"{tag} n={m.group('n')} vs 复算 {t['n']}")
        check_equal(f"{tag} F1", float(m.group("f1p")), t["f1"], tol_for(m.group("f1p")), failures)
        check_equal(f"{tag} F1 CI 下界", float(m.group("f1lo")), t["f1_ci"][0], tol_for(m.group("f1lo")), failures)
        check_equal(f"{tag} F1 CI 上界", float(m.group("f1hi")), t["f1_ci"][1], tol_for(m.group("f1hi")), failures)
        check_equal(f"{tag} AUC", float(m.group("aucp")), t["roc_auc"], tol_for(m.group("aucp")), failures)
        check_equal(f"{tag} AUC CI 下界", float(m.group("auclo")), t["roc_auc_ci"][0], tol_for(m.group("auclo")), failures)
        check_equal(f"{tag} AUC CI 上界", float(m.group("auchi")), t["roc_auc_ci"][1], tol_for(m.group("auchi")), failures)
        got_cm = [int(m.group(k)) for k in ("tp", "fp", "fn", "tn")]
        want_cm = [t["TP"], t["FP"], t["FN"], t["TN"]]
        if got_cm != want_cm:
            failures.append(f"{tag} 混淆矩阵 {got_cm} vs 复算 {want_cm}")

    # 5) 样本量第一行纪律 + 数据集规模字面量
    for literal in ("n = 157", "1029", "10000", "682", "2523", "719 / 153 / 157"):
        if literal not in text:
            failures.append(f"结果章节缺少必备字面量：{literal!r}（样本量/数据集规模必须写明）")

    # 6) 真 groupwise 泛化口径必须出现（不得只写泄漏口径）
    gm = CHAPTER_GROUPWISE.search(text)
    if not gm:
        failures.append("结果章节未写出真 groupwise 泛化口径 F1（0.5864 必须出现，不得只写泄漏口径）")
    else:
        check_equal("章节 groupwise F1", float(gm.group(1)), gw["f1"], 5e-5, failures)

    # 7) groupwise 跨被试 CI 表（F1/ROC AUC/Recall/Precision 点估计 + 分组 bootstrap CI）
    gw_ci = recompute_groupwise_ci()
    gw_metric = {"F1": "f1", "ROC AUC": "roc_auc", "Recall": "rec", "Precision": "prec"}
    gw_seen: set[str] = set()
    for line in lines:
        m = CHAPTER_GW_TABLE.match(line)
        if not m:
            continue
        label = m.group("label")
        gw_seen.add(label)
        key = gw_metric[label]
        check_equal(f"章节 groupwise 表 {label}", float(m.group("point")), gw[key], tol_for(m.group("point")), failures)
        lo, hi = gw_ci[key]
        check_equal(f"章节 groupwise 表 {label} CI 下界", float(m.group("lo")), lo, tol_for(m.group("lo")), failures)
        check_equal(f"章节 groupwise 表 {label} CI 上界", float(m.group("hi")), hi, tol_for(m.group("hi")), failures)
    for label in gw_metric:
        if label not in gw_seen:
            failures.append(f"结果章节 groupwise 跨被试表缺少 {label}（跨被试）行")


def check_blacklist(failures: list[str]) -> None:
    for doc in THESIS_DOCS:
        if not doc.exists():
            continue
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, why in FORBIDDEN:
                if pattern.search(line) and not REJECT.search(line):
                    failures.append(
                        f"[黑名单] {doc.name}:{lineno} 出现禁用数字（{why}）且同行无拒绝标记：{line.strip()[:80]}"
                    )


def check_citation_discipline(failures: list[str]) -> None:
    """QA / 局限文档：≥3 位小数的数字必须同行带台账编号或拒绝标记。"""
    for doc in (QA, LIMITATIONS):
        if not doc.exists():
            failures.append(f"缺少 {doc}")
            continue
        text = doc.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in FINE_NUM.finditer(line):
                if not (CLAIM_REF.search(line) or REJECT.search(line)):
                    failures.append(
                        f"[引用纪律] {doc.name}:{lineno} 的 {m.group(0)} 未带台账编号或拒绝标记"
                    )
    if QA.exists():
        qa_text = QA.read_text(encoding="utf-8")
        for marker in REQUIRED_QA_MARKERS:
            if marker not in qa_text:
                failures.append(f"REVIEWER_QA.md 缺少必答主题标记：{marker!r}")


def check_artifacts(failures: list[str]) -> None:
    """csv ⇄ json ⇄ sidecar 三层对拍（sha + n + CM + 点估计 + CI）。"""
    for unit, spec in UNITS.items():
        tag = f"工件[{unit}]"
        csv_path, json_path = spec["csv"], spec["json"]
        if not csv_path.exists():
            failures.append(f"{tag} 缺少逐样本 csv：{csv_path}")
            continue
        if not json_path.exists():
            failures.append(f"{tag} 缺少评估 json：{json_path}")
            continue
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        digest = sha256_of(csv_path)
        recorded = payload.get("reproducibility", {}).get("predictions_csv_sha256")
        if recorded != digest:
            failures.append(f"{tag} csv sha256 与 json 记录不符：{digest} vs {recorded}")
        if spec["sha_sidecar"].exists():
            side = spec["sha_sidecar"].read_text(encoding="utf-8").split()
            if not side or side[0] != digest:
                failures.append(f"{tag} csv sha256 与 sidecar 文件不符：{digest} vs {side[:1]}")
        t = recompute_unit(unit)
        meta = payload["meta"]
        for key in ("n", "TP", "FP", "FN", "TN"):
            if int(meta[key]) != int(t[key]):
                failures.append(f"{tag} json meta.{key}={meta[key]} vs 复算 {t[key]}")
        for key in ("acc", "prec", "rec", "f1", "roc_auc"):
            block = payload[key]
            check_equal(f"{tag} json {key}.point", float(block["point"]), t[key], 1e-6 + 1e-9, failures)
            lo, hi = t[f"{key}_ci"]
            check_equal(f"{tag} json {key}.ci95[0]", float(block["ci95"][0]), lo, 1e-6 + 1e-9, failures)
            check_equal(f"{tag} json {key}.ci95[1]", float(block["ci95"][1]), hi, 1e-6 + 1e-9, failures)
        if abs(float(payload.get("threshold", -1)) - DECISION) > 1e-12:
            failures.append(f"{tag} json.threshold={payload.get('threshold')} != {DECISION}")
        if spec["has_refit"]:
            diag = payload.get("diagnostic_refit_scaler", {})
            for key in ("f1", "rec", "roc_auc"):
                if key in diag:
                    check_equal(f"{tag} 诊断 {key}", float(diag[key]), t["refit"][key], 1e-6 + 1e-9, failures)


def check_groupwise_artifact(failures: list[str]) -> None:
    """文本 groupwise：csv 复算 ⇄ metrics json 的 groupwise_ooF 块（json 为 3–4 位小数）。"""
    if not GROUPWISE_CSV.exists() or not GROUPWISE_JSON.exists():
        failures.append("groupwise csv 或 metrics json 缺失")
        return
    payload = json.loads(GROUPWISE_JSON.read_text(encoding="utf-8"))
    block = payload["groupwise_ooF"]
    t = recompute_groupwise()
    # json 键名 → 复算字典键名（accuracy → acc 等）
    key_map = {"accuracy": "acc", "precision": "prec", "recall": "rec",
               "f1": "f1", "roc_auc": "roc_auc", "positive_rate": "positive_rate"}
    for key in key_map:
        if key in block:
            check_equal(f"groupwise json {key}", float(block[key]), t[key_map[key]], 5e-4 + 1e-9, failures)
    if int(block.get("n", -1)) != t["n"]:
        failures.append(f"groupwise json n={block.get('n')} vs 复算 {t['n']}")
    # groupwise_ci.json（ROUND_30）：分组 bootstrap CI 工件 ⇄ 独立复算（同序列）
    if GROUPWISE_CI_JSON.exists():
        ci_payload = json.loads(GROUPWISE_CI_JSON.read_text(encoding="utf-8"))
        # 行尾不敏感哈希（CRLF→LF），与 v1_30/groupwise_ci.py 一致
        oof_sha_lf = hashlib.sha256(GROUPWISE_CSV.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if ci_payload.get("oof_csv_sha256") != oof_sha_lf:
            failures.append(
                f"groupwise_ci.json 记录的 oof sha256 与当前 csv 不符："
                f"{ci_payload.get('oof_csv_sha256')} vs {oof_sha_lf}"
            )
        gw_ci = recompute_groupwise_ci()
        for key in ("f1", "roc_auc", "rec", "prec"):
            block_ci = ci_payload["metrics"][key]["ci95"]
            lo, hi = gw_ci[key]
            check_equal(f"groupwise_ci.json {key}.ci95[0]", float(block_ci[0]), lo, 1e-6 + 1e-9, failures)
            check_equal(f"groupwise_ci.json {key}.ci95[1]", float(block_ci[1]), hi, 1e-6 + 1e-9, failures)
            check_equal(f"groupwise_ci.json {key}.point", float(ci_payload["metrics"][key]["point"]),
                        t[key], 1e-6 + 1e-9, failures)


def check_calibration_artifact(failures: list[str]) -> None:
    """ROUND_33：校准分析产物的结构与口径边界校验（只读）。

    1. 四个单元的 **point**（brier/ece/slope/intercept）必须与独立复算一致；
    2. role 边界必须保持：仅 text_groupwise_oof 为 citable，
       两个 transfer 单元必须仍是 stress_only（防口径悄悄升级）；
    3. 每个单元的 source_sha256 必须与当前 csv 的行尾不敏感哈希一致；
    4. slope/intercept 不得带 CI（method.not_estimated 已声明）。
    """
    if not CALIBRATION_JSON.exists():
        failures.append(f"缺少校准分析产物 {CALIBRATION_JSON}")
        return
    doc = json.loads(CALIBRATION_JSON.read_text(encoding="utf-8"))
    truth = recompute_calibration()
    for unit, u in doc["units"].items():
        if unit not in truth:
            failures.append(f"校准产物出现未登记单元 {unit!r}")
            continue
        t = truth[unit]
        if u.get("role") != CALIB_UNITS[unit]["role"]:
            failures.append(f"[calib:{unit}] role 应为 {CALIB_UNITS[unit]['role']!r}，实际 {u.get('role')!r}")
        for metric in ("brier", "ece", "calibration_slope", "calibration_intercept"):
            doc_point = u["metrics"][metric]["point"] if metric in u["metrics"] else u[metric]
            check_equal(
                f"[calib:{unit}] {metric}（产物 vs 独立复算）",
                float(doc_point), float(t[metric]), 1e-6, failures,
            )
        if u.get("n") != t["n"]:
            failures.append(f"[calib:{unit}] n={u.get('n')} 与 csv 行数 {t['n']} 不一致")
        if abs(u.get("positive_rate", 0.0) - t["positive_rate"]) > 5e-5:
            failures.append(f"[calib:{unit}] positive_rate 与 csv 不一致")
        # 反斜杠归一化：ROUND_33 首版 json 在 Windows 上生成，source 带 "\\"，
        # Linux checkout 下不成分隔符 ⇒ 4 个 calib 单元在 CI 全部误报「不存在」
        # （ROUND_33 修复提交）。防御性兼容旧产物，同时生成端已改 as_posix()。
        src = REPO / u["source"].replace("\\", "/")
        if not src.exists():
            failures.append(f"[calib:{unit}] source 不存在：{u['source']}")
        elif u.get("source_sha256") != hashlib.sha256(src.read_bytes().replace(b"\r\n", b"\n")).hexdigest():
            # 行尾不敏感口径：与 v1_30/groupwise_ci.py、v1_33/calibration_analysis.py 一致
            # （Windows checkout 的 CRLF 与 Linux 的 LF 必须给出同一哈希）
            failures.append(f"[calib:{unit}] source_sha256 与当前 csv 不一致（csv 被改过？）")
        if "ci95" in u["metrics"].get("calibration_slope", {}):
            failures.append(f"[calib:{unit}] calibration_slope 不得带 CI（method.not_estimated）")
        dca = u.get("dca")
        if dca:
            for thr in DCA_REPORT_THRESHOLDS:
                if thr not in dca["thresholds"]:
                    failures.append(f"[calib:{unit}] dca.thresholds 缺少 {thr}")
                    continue
                idx = dca["thresholds"].index(thr)
                check_equal(
                    f"[calib:{unit}] DCA 净获益 NB(t={thr:g})",
                    float(dca["net_benefit_model"][idx]), float(t[f"nb_{thr:g}"]), 1e-6, failures,
                )


def check_ablation_artifact(failures: list[str]) -> None:
    """ROUND_37：融合消融产物的结构与口径边界校验（只读）。

    1. 引擎参数必须与生产 DEFAULT_WEIGHTS 一致；
    2. 汇总统计（翻转率/最大 Δ/分层）必须与独立重算一致；
    3. worst case 必须可复算；
    4. 产物必须自证「输入是合成网格、非性能证据」（防口径悄悄升级）。
    """
    abl_json = Path(__file__).resolve().parent / "v1_37" / "fusion_ablation.json"
    if not abl_json.exists():
        failures.append(f"缺少融合消融产物 {abl_json}")
        return
    doc = json.loads(abl_json.read_text(encoding="utf-8"))
    truth = recompute_ablation()
    if doc["engine"]["weights"] != truth["weights"]:
        failures.append(
            f"[ablation] 引擎权重 {doc['engine']['weights']} 与生产 {truth['weights']} 不一致"
        )
    if doc["engine"]["use_confidence_weighting"] is not True:
        failures.append("[ablation] 置信度加权必须为 True（生产配置）")
    if doc["grid"]["n_combinations"] != truth["n"]:
        failures.append("[ablation] 网格组合数与独立重算不一致")
    for name, s in doc["summary"].items():
        check_equal(f"[ablation:{name}] 翻转率", float(s["flip_rate"]),
                    float(truth[f"{name}_flip_rate"]), 5e-5, failures)
        if s["max_abs_delta"] != truth[f"{name}_max_abs_delta"]:
            failures.append(
                f"[ablation:{name}] 最大|Δ| {s['max_abs_delta']} vs 复算 "
                f"{truth[f'{name}_max_abs_delta']}"
            )
        for stratum in ("agree", "conflict"):
            b = s["by_stratum"].get(stratum)
            if b is None:
                continue
            check_equal(f"[ablation:{name}] {stratum} 翻转率", float(b["flip_rate"]),
                        float(truth[f"{name}_{stratum}_flip_rate"]), 5e-5, failures)
    top = doc["worst_cases"][0]
    if int(top["full_level"]) != int(truth["worst_full_level"]):
        failures.append("[ablation] worst case 的完整等级与复算不一致")
    if int(top["only_physiological_level"]) != int(truth["worst_only_physio_level"]):
        failures.append("[ablation] worst case 的仅生理等级与复算不一致")
    note = doc["_note"]
    for token in ("合成", "不是模型性能", "确定性分数网格"):
        if token not in note:
            failures.append(f"[ablation] 产物 _note 缺少口径边界声明：{token!r}")


def check_safety_net_artifact(failures: list[str]) -> None:
    """ROUND_36：安全网产物的结构与口径边界校验（只读）。

    1. 工作点必须与独立复算一致（含 t_low / t_high / net_recall / burden）；
    2. **结构恒等式**必须成立：burden == P(p>=t_low)、net_recall == 1 − FN率；
    3. **成本等价**必须成立：双阈值 burden == 单阈值下调到 t_low 的 alert_rate
       （这是「双阈值不省钱、只提高预警精确率」的机器化判据）；
    4. source 必须是 posix 路径（ROUND_33 的 Windows 反斜杠缺陷不许复发）。
    """
    if not SAFETY_NET_JSON.exists():
        failures.append(f"缺少安全网产物 {SAFETY_NET_JSON}")
        return
    doc = json.loads(SAFETY_NET_JSON.read_text(encoding="utf-8"))
    sn = recompute_safety_net()
    if not sn["feasible"]:
        failures.append("[safetynet] 独立复算下工作点不可达 ⇒ 产物宣称可行即失真")
        return
    truth = sn["point"]
    op = doc["operating_point"]
    if not op["feasible"]:
        failures.append("[safetynet] 产物标记不可达，但独立复算可行")
        return
    pt = op["operating_point"]
    if (pt["t_low"], pt["t_high"]) != (truth["t_low"], truth["t_high"]):
        failures.append(
            f"[safetynet] 工作点 ({pt['t_low']}, {pt['t_high']}) 与独立复算 "
            f"({truth['t_low']}, {truth['t_high']}) 不一致"
        )
    for key in ("net_recall", "review_burden", "sn_precision", "alert_precision"):
        check_equal(f"[safetynet] {key}", float(pt[key]), float(truth[key]), 1e-6, failures)
    ident = doc.get("structural_identity", {})
    check_equal(
        "[safetynet] burden 恒等式",
        float(ident.get("burden_reported", float("nan"))),
        float(ident.get("burden_equals_P_p_ge_t_low", float("nan"))),
        1e-6, failures,
    )
    check_equal(
        "[safetynet] net_recall 恒等式",
        float(ident.get("net_recall_reported", float("nan"))),
        float(ident.get("net_recall_equals_1_minus_fn_rate", float("nan"))),
        1e-6, failures,
    )
    cost = doc.get("cost_equivalence", {})
    if cost.get("same_burden") is not True:
        failures.append("[safetynet] 成本等价标记为假 ⇒ 「双阈值不省钱」的结论失效")
    single = cost.get("single_threshold_at_t_low", {})
    check_equal(
        "[safetynet] 成本等价数值",
        float(single.get("alert_rate", float("nan"))),
        float(ident.get("burden_reported", float("nan"))),
        1e-6, failures,
    )
    src = doc["data"].get("source", "")
    if "\\" in src:
        failures.append(f"[safetynet] source 含反斜杠（Windows 路径缺陷复发）：{src!r}")
    if doc["data"].get("source_sha256") != hashlib.sha256(
        (REPO / src).read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest():
        failures.append("[safetynet] source_sha256 与当前 csv 不一致")


def run_all(show_only: bool = False) -> int:
    failures: list[str] = []
    if show_only:
        truth = build_truth()
        for cid in sorted(truth):
            print(f"{cid}\t{truth[cid]}")
        return 0
    check_artifacts(failures)
    check_groupwise_artifact(failures)
    check_calibration_artifact(failures)
    check_safety_net_artifact(failures)
    check_ablation_artifact(failures)
    truth = build_truth()
    check_ledger(truth, failures)
    check_chapter(failures)
    check_blacklist(failures)
    check_citation_discipline(failures)
    if failures:
        print(f"论文数字校验 FAIL：{len(failures)} 处不一致\n")
        for item in failures:
            print(f"  ✗ {item}")
        print("\n修复方式：改文档使其与已提交产物一致，或改产物并同步文档与台账（两边都必须动）。")
        return 1
    print(
        f"论文数字校验 OK：台账 {len(EXPECTED)} 条 + 章节主表/迁移表/混淆矩阵/诊断表 "
        f"+ 黑名单 + 引用纪律，全部与已提交产物一致"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文数字校验闸门（只读）")
    ap.add_argument("--show", action="store_true", help="只打印复算真值表，不做文档校验")
    args = ap.parse_args(argv)
    return run_all(show_only=args.show)


if __name__ == "__main__":
    raise SystemExit(main())
