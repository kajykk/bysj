#!/usr/bin/env python
"""ROUND_33 (P1 校准)：四单元概率级校准分析 + 决策曲线（DCA）。

口径边界（与 ROUND_27/30 的裁定一脉相承，**不可越界引用**）：

  ┌───────────────────────┬────────┬────────────────────────────────────────┐
  │ 单元                  │ 口径   │ 说明                                    │
  ├───────────────────────┼────────┼────────────────────────────────────────┤
  │ text_groupwise_oof    │ 可引用 │ 文本模态 groupwise(sibling-aware 去泄漏) │
  │                       │        │ OOF，n=8379 / 1277 组。**唯一可引用泛化  │
  │                       │        │ 口径**（F1 0.5864）。                    │
  │ physio_current_split  │ 可引用 │ 生理 v2 生产链在 depresjon@当前版本上的  │
  │                       │(次)    │ 确定性切分测试集，n=157。小样本 ⇒ CI 极宽 │
  │                       │        │ 如实记账，不与文本口径混引。             │
  │ text_ood_strict       │ 压力   │ OOD S2_ood_strict，2523 条 eda 改写 ⇒   │
  │                       │ 测试   │ 兄弟泄漏，**不是外迁**（TRANSFER_MATRIX）。│
  │ physio_kaggle         │ 压力   │ Kaggle Wearable 10000 条，3/13 特征映射   │
  │                       │ 测试   │ + 4 列默认值填充 ⇒ 跨数据集下界，非公平基准│
  └───────────────────────┴────────┴────────────────────────────────────────┘

实现纪律：
1. **只读 csv / 只写本目录 json 与 docs 报告**；不读 metrics.json / registry 旧值，
   不跑模型（概率已在 csv 里逐样本落盘，`--report-only` 语义天然成立）。
2. **行序即计算序**：各 csv 按 row_index 升序读入（groupwise_oof 无该列，按文件行序，
   与 v1_30/groupwise_ci.py 一致）。
3. **bootstrap 与点估计共用同一套纯函数**（calibration_lib），CI 与点估计不会算法分叉。
   文本按 group 重采样（B=10000, seed=42，与 v1_30 同源同 seed）；其余按行重采样。
4. **不做 calibration 后处理/重拟合**：本脚本只诊断，不产出「校准后模型」；
   slope/intercept 只作点估计（未给 CI）——理由见报告「未验证与记账」。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_33/calibration_analysis.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]  # backend/（HERE 已是目录，比 v1_29/01 的 __file__ 少一级）
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from calibration_lib import (  # noqa: E402
    brier_score,
    calibration_slope_intercept,
    decision_curve,
    expected_calibration_error,
    max_calibration_error,
    reliability_table,
)

OUT_JSON = HERE / "calibration_analysis.json"
REPORT_MD = BACKEND.parent / "docs" / "model-evaluation" / "CALIBRATION_REPORT.md"

BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42
N_BINS = 10
DCA_THRESHOLDS = [round(0.01 * k, 2) for k in range(1, 100)]  # 0.01 .. 0.99


def _sha(path: Path) -> str:
    """行尾不敏感哈希：CRLF→LF 再 sha256（防 Windows checkout 与 Linux 不一致）。"""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _read_two_col(path: Path, y_col: str, p_col: str) -> tuple[np.ndarray, np.ndarray]:
    """读 (y, p) 两列；按 row_index 升序（无该列则按文件行序）。"""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    header = lines[0].lstrip("\ufeff").split(",")
    i_y, i_p = header.index(y_col), header.index(p_col)
    i_ri = header.index("row_index") if "row_index" in header else None
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        parts = ln.split(",")
        ri = int(parts[i_ri]) if i_ri is not None else len(rows)
        rows.append((ri, float(parts[i_y]), float(parts[i_p])))
    rows.sort(key=lambda r: r[0])
    y = np.array([r[1] for r in rows], dtype=np.float64)
    p = np.array([r[2] for r in rows], dtype=np.float64)
    return y, p


def _read_grouped(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """读 groupwise_oof csv：按 group 字典序排序后返回 (y, p, group_id)。"""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].lstrip("\ufeff") == "label,group,p_groupwise,p_textwise", lines[0]
    y, s, g = [], [], []
    for ln in lines[1:]:
        parts = ln.split(",")
        y.append(float(parts[0]))
        g.append(parts[1])
        s.append(float(parts[2]))
    y = np.array(y, dtype=np.float64)
    s = np.array(s, dtype=np.float64)
    g = np.array(g)
    order = np.argsort(g, kind="mergesort")
    return y[order], s[order], g[order]


def _bootstrap_ci(y, p, groups=None, B=BOOTSTRAP_B, seed=BOOTSTRAP_SEED) -> dict:
    """bootstrap 分位 CI：brier / ece / mce **一次抽样同时收集三个指标**。

    与 v1_30/groupwise_ci.py 同源：同 seed=42、同 rng.randint(0, G, G) 抽样逻辑，
    使两个脚本的 bootstrap 样本完全一致（便于交叉核对）。
    故意不按指标分三次跑——那会让三次抽样序列不同（虽然同 seed，但 randint 消耗次数
    不同），指标间不可比，且白跑两遍。
    """
    rng = np.random.RandomState(seed)
    samples = {"brier": [], "ece": [], "mce": []}
    if groups is None:
        n = y.size
        for _ in range(B):
            pick = rng.randint(0, n, n)
            yb, pb = y[pick], p[pick]
            samples["brier"].append(brier_score(yb, pb))
            samples["ece"].append(expected_calibration_error(yb, pb, N_BINS))
            samples["mce"].append(max_calibration_error(yb, pb, N_BINS))
    else:
        uniq = np.unique(groups)
        G = len(uniq)
        pos = {gg: i for i, gg in enumerate(uniq)}
        row_g = np.array([pos[gg] for gg in groups], dtype=np.int64)
        for _ in range(B):
            pick = rng.randint(0, G, G)
            cnt = np.bincount(pick, minlength=G)
            sel = np.repeat(np.arange(y.size), cnt[row_g])
            yb, pb = y[sel], p[sel]
            samples["brier"].append(brier_score(yb, pb))
            samples["ece"].append(expected_calibration_error(yb, pb, N_BINS))
            samples["mce"].append(max_calibration_error(yb, pb, N_BINS))
    out = {}
    for k, vals in samples.items():
        arr = np.array(vals, dtype=np.float64)
        out[k] = {
            "ci95": [round(float(np.percentile(arr, 2.5)), 6), round(float(np.percentile(arr, 97.5)), 6)],
            "bootstrap_n": int(arr.size),
        }
    return out


def _dca_summary(dca: dict) -> dict:
    """净获益区间摘要：模型优于 treat_none / treat_all 的阈值范围。"""
    t = np.asarray(dca["thresholds"])
    nb = np.asarray(dca["net_benefit_model"])
    nb_all = np.asarray(dca["net_benefit_treat_all"])

    def _ranges(mask):
        if not mask.any():
            return []
        out = []
        start = t[mask][0]
        prev = start
        for cur in t[mask][1:]:
            if cur - prev > 0.0100001:
                out.append([round(float(start), 2), round(float(prev), 2)])
                start = cur
            prev = cur
        out.append([round(float(start), 2), round(float(prev), 2)])
        return out

    return {
        "model_beats_treat_none_ranges": _ranges(nb > 0),
        "model_beats_treat_all_ranges": _ranges(nb > nb_all),
    }


def analyze_unit(name: str, y, p, groups=None, meta: dict | None = None) -> dict:
    meta = meta or {}
    si = calibration_slope_intercept(y, p)
    dca = decision_curve(y, p, DCA_THRESHOLDS)
    unit = {
        **meta,
        "n": int(y.size),
        "positive_rate": round(float(y.mean()), 4),
        "metrics": {
            "brier": {"point": round(brier_score(y, p), 6)},
            "ece": {"point": round(expected_calibration_error(y, p, N_BINS), 6)},
            "mce": {"point": round(max_calibration_error(y, p, N_BINS), 6)},
        },
        "calibration_slope": round(si["slope"], 6),
        "calibration_intercept": round(si["intercept"], 6),
        "reliability_table": reliability_table(y, p, N_BINS),
        "dca": {
            "thresholds": [float(x) for x in dca["thresholds"]],
            "net_benefit_model": [round(float(x), 6) for x in dca["net_benefit_model"]],
            "net_benefit_treat_all": [round(float(x), 6) for x in dca["net_benefit_treat_all"]],
            "net_benefit_treat_none": [round(float(x), 6) for x in dca["net_benefit_treat_none"]],
            **_dca_summary(dca),
        },
    }
    if groups is not None:
        unit["n_groups"] = int(len(np.unique(groups)))
        unit["bootstrap"] = {"kind": "group", "B": BOOTSTRAP_B, "seed": BOOTSTRAP_SEED}
        ci = _bootstrap_ci(y, p, groups)
    else:
        unit["bootstrap"] = {"kind": "row", "B": BOOTSTRAP_B, "seed": BOOTSTRAP_SEED}
        ci = _bootstrap_ci(y, p)
    for k in ("brier", "ece", "mce"):
        unit["metrics"][k] = {"point": unit["metrics"][k]["point"], **ci[k]}
    return unit


def build_units() -> dict:
    units = {}

    # 1) 文本 groupwise OOF —— 唯一可引用泛化口径
    oof = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
    y, s, g = _read_grouped(oof)
    units["text_groupwise_oof"] = analyze_unit(
        "text_groupwise_oof", y, s, groups=g,
        meta={
            "role": "citable",
            "source": oof.relative_to(BACKEND.parent).as_posix(),
            "source_sha256": _sha(oof),
            "probability_column": "p_groupwise",
            "note": "sibling-aware 分组去泄漏 OOF；文本模态唯一可引用泛化口径。",
        },
    )

    # 2) 生理 v2 当前数据切分测试集（157 行）
    physio = BACKEND / "models" / "artifacts" / "physiological_optimized" / "test_predictions.csv"
    y, p = _read_two_col(physio, "y_true", "y_score")
    units["physio_current_split"] = analyze_unit(
        "physio_current_split", y, p,
        meta={
            "role": "citable_secondary",
            "source": physio.relative_to(BACKEND.parent).as_posix(),
            "source_sha256": _sha(physio),
            "probability_column": "y_score",
            "note": "depresjon@当前版本确定性切分测试集；n=157 极小，CI 必然极宽，单独记账。",
        },
    )

    # 3) 文本 OOD strict（2523 条，兄弟泄漏 ⇒ 压力测试）
    ood = BACKEND / "models" / "artifacts" / "eval_transfer" / "transfer_text_ood_predictions.csv"
    y, p = _read_two_col(ood, "y_true", "y_score")
    units["text_ood_strict"] = analyze_unit(
        "text_ood_strict", y, p,
        meta={
            "role": "stress_only",
            "source": ood.relative_to(BACKEND.parent).as_posix(),
            "source_sha256": _sha(ood),
            "probability_column": "y_score",
            "note": "eda 对 original 的兄弟改写 ⇒ 标签/兄弟泄漏，域内压力测试，不得作外迁引用。",
        },
    )

    # 4) 生理 → Kaggle（10000 条，3/13 特征映射 ⇒ 跨数据集下界）
    kag = BACKEND / "models" / "artifacts" / "eval_transfer" / "transfer_physio_kaggle_predictions.csv"
    y, p = _read_two_col(kag, "y_true", "y_score")
    units["physio_kaggle"] = analyze_unit(
        "physio_kaggle", y, p,
        meta={
            "role": "stress_only",
            "source": kag.relative_to(BACKEND.parent).as_posix(),
            "source_sha256": _sha(kag),
            "probability_column": "y_score",
            "note": "3/13 特征直接映射 + 4 列按生产默认值填充 ⇒ 跨数据集下界，非公平基准。",
        },
    )
    return units


def _render_report(units: dict) -> str:
    """机器生成的数据表报告；叙述与结论在 docs/thesis/RESULTS_CHAPTER.md §4ter。"""
    lines = [
        "# 校准与决策曲线分析报告（ROUND_33 · P1）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_33/calibration_analysis.py` 生成",
        "（同输入必然同输出，连跑两次字节一致）。**只读已落盘的逐样本 csv**，不跑模型、",
        "不读 `metrics.json` / registry 旧值。叙述、解读与引用边界见",
        "`docs/thesis/RESULTS_CHAPTER.md` §4ter 与 `docs/thesis/CLAIMS_LEDGER.md` C-26 ~ C-33。",
        "",
        "## 口径边界（先于指标）",
        "",
        "| 单元 | role | n | 说明 |",
        "|---|---|---|---|",
    ]
    for unit, u in units.items():
        lines.append(
            f"| `{unit}` | {u['role']} | {u['n']} | {u.get('note', '')} |"
        )
    lines += [
        "",
        "**只有 `text_groupwise_oof` 是可引用泛化口径**；`physio_current_split` 为次级",
        "（n=157 极小，CI 必然极宽，引用处必须同句标注 n）；两个 transfer 单元为压力测试",
        "（兄弟泄漏 / 跨数据集下界），**不得**作外迁引用。",
        "",
        "## 校准指标",
        "",
        "| 单元 | Brier | ECE | MCE | 校准斜率 | 校准截距 | 台账 |",
        "|---|---|---|---|---|---|---|",
    ]
    calib_claims = {
        "text_groupwise_oof": "C-26 / C-27 / C-28",
        "physio_current_split": "C-29",
        "physio_kaggle": "C-30",
        "text_ood_strict": "C-31",
    }
    for unit, u in units.items():
        m = u["metrics"]
        lines.append(
            f"| `{unit}` | {m['brier']['point']:.4f} {m['brier']['ci95']} "
            f"| {m['ece']['point']:.4f} {m['ece']['ci95']} "
            f"| {m['mce']['point']:.4f} {m['mce']['ci95']} "
            f"| {u['calibration_slope']:.4f} | {u['calibration_intercept']:.4f} "
            f"| {calib_claims[unit]} |"
        )
    lines += [
        "",
        "方括号内为 95% bootstrap CI（分位法；文本按 group 重采样，其余按行，B=10000、seed=42）。",
        "**校准斜率/截距没有 CI**——每次 bootstrap 都要重跑一次优化，成本不成比例，且其",
        "解释价值在「偏离 1 的方向」而非区间宽度。",
        "",
        "## 决策曲线（DCA）阈值区间摘要",
        "",
        "| 单元 | 模型优于 treat_none | 模型优于 treat_all |",
        "|---|---|---|",
    ]
    for unit, u in units.items():
        dca = u["dca"]
        lines.append(
            f"| `{unit}` | {dca['model_beats_treat_none_ranges']} | {dca['model_beats_treat_all_ranges']} |"
        )
    lines += [
        "",
        "完整 99 点曲线见 `calibration_analysis.json` 的 `units.*.dca`。",
        "",
        "## 未做的事（记账）",
        "",
        "1. **没有做校准后处理**（Platt / isotonic 重拟合）：需要独立留出集，而生理单元",
        "   n=157、文本 OOF 已用尽，均不满足前提。本文只诊断不修复。",
        "2. **斜率/截距无 CI、DCA 无净获益 CI**（理由见上）。",
        "3. **阈值下调的收益没有实测**：只论证「方向上下调阈值值得试」，未扫描阈值。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    units = build_units()
    payload = {
        "_note": (
            "ROUND_33 (P1 校准) 四单元概率级校准分析与决策曲线。只读逐样本 csv，"
            "不跑模型、不读 metrics.json/registry 旧值。引用边界见各单元 role 字段："
            "仅 text_groupwise_oof 为可引用泛化口径，physio_current_split 为次级（小样本），"
            "两个 transfer 单元为压力测试（兄弟泄漏 / 跨数据集下界），不得作外迁引用。"
        ),
        "method": {
            "brier": "mean((p - y)^2)",
            "ece": f"等宽 {N_BINS} 箱 Σ |B_k|/n · |acc_k - conf_k|",
            "mce": f"max_k |acc_k - conf_k|（{N_BINS} 等宽箱，空箱不计）",
            "calibration_slope_intercept": "Platt 缩放 y ~ logit(p)，Newton-Raphson 100 步 tol 1e-12（无正则 MLE）",
            "dca": "net_benefit(t) = TP/n - (FP/n)·(t/(1-t))；阈值 0.01..0.99 步长 0.01",
            "bootstrap": f"分位 CI，B={BOOTSTRAP_B}, seed={BOOTSTRAP_SEED}；文本按 group 重采样（与 v1_30 同源同 seed），其余按行",
            "not_estimated": "calibration slope/intercept 未给 CI（计算成本；其解释价值主要在偏离 1 的方向）",
        },
        "units": units,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(_render_report(units), encoding="utf-8")

    lines = [
        "[calibration]",
        f"  text_groupwise_oof  n={units['text_groupwise_oof']['n']} "
        f"Brier={units['text_groupwise_oof']['metrics']['brier']['point']:.4f} "
        f"ECE={units['text_groupwise_oof']['metrics']['ece']['point']:.4f} "
        f"slope={units['text_groupwise_oof']['calibration_slope']:.3f}",
        f"  physio_current_split n={units['physio_current_split']['n']} "
        f"Brier={units['physio_current_split']['metrics']['brier']['point']:.4f} "
        f"ECE={units['physio_current_split']['metrics']['ece']['point']:.4f}",
        f"  text_ood_strict      n={units['text_ood_strict']['n']} "
        f"Brier={units['text_ood_strict']['metrics']['brier']['point']:.4f}",
        f"  physio_kaggle        n={units['physio_kaggle']['n']} "
        f"Brier={units['physio_kaggle']['metrics']['brier']['point']:.4f}",
        f"  -> {OUT_JSON.relative_to(BACKEND.parent)}",
        f"  -> {REPORT_MD.relative_to(BACKEND.parent)}",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
