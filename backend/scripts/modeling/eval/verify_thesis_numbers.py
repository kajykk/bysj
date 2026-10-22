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
    rows = GROUPWISE_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]
    y = np.array([int(ln.split(",")[0]) for ln in rows], dtype=np.int64)
    s = np.array([float(ln.split(",")[2]) for ln in rows], dtype=np.float64)  # p_groupwise
    m = threshold_metrics(y, s)
    _GROUPWISE_CACHE = {
        "n": m["n"], "acc": m["acc"], "prec": m["prec"], "rec": m["rec"], "f1": m["f1"],
        "roc_auc": auc_point(y, s),
        "positive_rate": float((y == 1).mean()),
    }
    return _GROUPWISE_CACHE


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
    "X-01": ("sens", "agree_low"),
    "X-02": ("sens", "agree_high"),
    "X-03": ("sens", "mid_all"),
    "X-04": ("sens", "conflict_s-low_t-high"),
    "X-05": ("sens", "conflict_s-high_t-low"),
    "X-06": ("sens", "production_row"),
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
        # CI：仅 unit·point 类有 CI；其余必须写「—」
        if spec[0] == "unit" and spec[3] == "point":
            _, unit, metric, _ = spec
            lo_truth, hi_truth = units[unit][f"{metric}_ci"]
            pair = re.findall(NUM, ci)
            if len(pair) != 2:
                failures.append(f"[{where}] CI 单元格无法解析为两个数：{ci!r}")
            else:
                check_equal(f"{where} CI 下界", float(pair[0]), lo_truth, tol_for(pair[0]), failures)
                check_equal(f"{where} CI 上界", float(pair[1]), hi_truth, tol_for(pair[1]), failures)
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


def run_all(show_only: bool = False) -> int:
    failures: list[str] = []
    if show_only:
        truth = build_truth()
        for cid in sorted(truth):
            print(f"{cid}\t{truth[cid]}")
        return 0
    check_artifacts(failures)
    check_groupwise_artifact(failures)
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
