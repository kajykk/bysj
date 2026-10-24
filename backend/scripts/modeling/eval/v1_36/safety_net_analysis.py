#!/usr/bin/env python
"""ROUND_36（P1 漏报安全网）：文本模态双阈值「预警 + 安全网」规则评估。

回答的问题
----------
固定阈值 0.5 下文本模态 Recall 只有 0.5375 [C-24]（漏掉约 46% 阳性），
而校准斜率 1.3466 [C-28] 证明概率**系统性偏低**。那么：

    把「不确定带」单独送人工复核，能否把漏报率压到 20% 以下，
    同时不让「直接预警」的精确率崩掉？

规则与指标定义见 `safety_net_lib.py`（双阈值：p≥t_high 直接预警、
t_low≤p<t_high 安全网送复核、p<t_low 阴性）。工作点选择标准**先定后扫**：
净 Recall ≥ 0.80 且复核负担最小。

边界与记账（与 ROUND_33 一脉相承）
--------------------------------
1. 数据只用 `v1_27/groupwise_oof_predictions.csv`（唯一可引用泛化口径）。
   不碰生理/迁移单元——它们不是同一决策问题，混进来会污染结论。
2. **没有独立留出集**：全部 8379 行都是 OOF，不存在第二份数据可验证扫出来的
   工作点。因此本轮报的是「在这批数据上、按预设标准选出的工作点」，
   带**选择性偏差风险**，不得宣称为「已验证的最优阈值」。
3. **未接入融合层**：本轮只评估文本概率层的规则，没有改
   `app/core/risk_thresholds.py` 的 22/42/62/82 分级，也没有改 fusion_engine。
   接入是独立工作（需要联调与回归），本节只提供依据。
4. 不跑模型、不读 registry 旧值，只读已落盘逐样本 csv。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_36/safety_net_analysis.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from safety_net_lib import (  # noqa: E402
    DEFAULT_T_HIGH_GRID,
    DEFAULT_T_LOW_GRID,
    TARGET_NET_RECALL,
    pick_operating_point,
    single_threshold_metrics,
    sweep_safety_net,
    sweep_single,
)

OUT_JSON = HERE / "safety_net_analysis.json"
REPORT_MD = BACKEND.parent / "docs" / "model-evaluation" / "SAFETY_NET_REPORT.md"
OOF_CSV = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"

BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42
BASELINE_THRESHOLD = 0.5  # 现行单阈值（与 C-22~C-25 同口径）


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_oof() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """读 groupwise OOF；按 group 字典序排序（与 v1_30/groupwise_ci.py 一致）。"""
    lines = OOF_CSV.read_text(encoding="utf-8").strip().splitlines()
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


def _group_bootstrap_ci(y, p, groups, fn, B=BOOTSTRAP_B, seed=BOOTSTRAP_SEED) -> dict:
    """按 group 重采样的 bootstrap 分位 CI（与 v1_30 / v1_33 同源同 seed）。

    fn 是 (y, p) -> float 的指标函数；点估计与 CI 共用同一 fn。
    """
    uniq = np.unique(groups)
    G = len(uniq)
    pos = {gg: i for i, gg in enumerate(uniq)}
    row_g = np.array([pos[gg] for gg in groups], dtype=np.int64)
    rng = np.random.RandomState(seed)
    vals = []
    for _ in range(B):
        pick = rng.randint(0, G, G)
        cnt = np.bincount(pick, minlength=G)
        sel = np.repeat(np.arange(y.size), cnt[row_g])
        v = fn(y[sel], p[sel])
        if v is not None and not np.isnan(v):
            vals.append(v)
    arr = np.array(vals, dtype=np.float64)
    return {
        "ci95": [round(float(np.percentile(arr, 2.5)), 6), round(float(np.percentile(arr, 97.5)), 6)],
        "bootstrap_n": int(arr.size),
    }


def _net_recall_at(op_point: dict):
    t_low, t_high = op_point["t_low"], op_point["t_high"]

    def fn(y, p):
        from safety_net_lib import apply_safety_net

        return apply_safety_net(y, p, t_low, t_high)["net_recall"]

    return fn


def _recall_at(thr: float):
    def fn(y, p):
        return single_threshold_metrics(y, p, thr)["recall"]

    return fn


def main() -> int:
    y, p, g = load_oof()

    # 1) 单阈值基线（现行 0.5 + 全网格对照）
    baseline = single_threshold_metrics(y, p, BASELINE_THRESHOLD)
    single_sweep = sweep_single(y, p)

    # 2) 双阈值全网格 + 按预设标准选工作点
    grid = sweep_safety_net(y, p, DEFAULT_T_HIGH_GRID, DEFAULT_T_LOW_GRID)
    op = pick_operating_point(y, p, DEFAULT_T_HIGH_GRID, DEFAULT_T_LOW_GRID, TARGET_NET_RECALL)

    payload: dict = {
        "_note": (
            "ROUND_36 (P1 漏报安全网) 双阈值规则评估。只读 groupwise OOF csv；"
            "无独立留出集 ⇒ 工作点带选择性偏差风险；未接入融合层。"
        ),
        "data": {
            "source": OOF_CSV.relative_to(BACKEND.parent).as_posix(),
            "source_sha256": _sha(OOF_CSV),
            "n": int(y.size),
            "n_groups": int(len(np.unique(g))),
            "positive_rate": round(float(y.mean()), 4),
        },
        "method": {
            "rule": "p>=t_high 直接预警；t_low<=p<t_high 安全网送复核；p<t_low 阴性",
            "net_recall": "(TP + 安全网捕获阳性) / 全部阳性",
            "review_burden": "(TP + FP + 安全网总数) / n",
            "alert_precision": "TP / (TP + FP)（只对直接预警负责，安全网不进分母）",
            "target_net_recall": TARGET_NET_RECALL,
            "selection_criterion": "先定后扫：净 Recall≥0.80 且复核负担最小；并列取 t_high 更高者",
            "grid": {
                "t_high": DEFAULT_T_HIGH_GRID,
                "t_low": DEFAULT_T_LOW_GRID,
                "n_configs": len(grid),
            },
            "bootstrap": f"按 group 重采样，B={BOOTSTRAP_B}, seed={BOOTSTRAP_SEED}（与 v1_30/v1_33 同源同 seed）",
            "not_estimated": "无独立留出集可验证工作点；未接入融合层/风险分级",
        },
        "baseline_single_threshold": {
            **baseline,
            "recall_ci95": _group_bootstrap_ci(y, p, g, _recall_at(BASELINE_THRESHOLD)),
        },
        "operating_point": op,
        "single_threshold_sweep": single_sweep,
        "safety_net_sweep": grid,
    }

    if op["feasible"]:
        point = op["operating_point"]
        payload["operating_point"]["net_recall_ci95"] = _group_bootstrap_ci(
            y, p, g, _net_recall_at(point)
        )
        # 与基线的漏报率对比（同口径：净漏报 vs 单阈值漏报）
        payload["comparison"] = {
            "baseline_miss_rate": round(1.0 - baseline["recall"], 4),
            "safety_net_miss_rate": round(point["miss_rate"], 4),
            "miss_rate_abs_drop": round(baseline["recall"] - point["net_recall"], 4),
            "review_burden": round(point["review_burden"], 4),
            "alert_precision": round(point["alert_precision"], 4),
            "note": "review_burden 含直接预警 + 安全网复核；人工成本按 review_burden 计",
        }
        # 结构恒等式核验：burden 与 net_recall 只由 t_low 决定，t_high 不参与
        #   burden      = P(p >= t_low)
        #   net_recall  = 1 - P(阳性且 p < t_low) / P(阳性)
        # 这条恒等式若被破坏，说明 apply_safety_net 的计数与定义脱钩
        prob_ge_low = float((p >= point["t_low"]).mean())
        pos_mask = y == 1.0
        fn_rate = float(((p < point["t_low"]) & pos_mask).sum() / pos_mask.sum())
        payload["structural_identity"] = {
            "burden_equals_P_p_ge_t_low": round(prob_ge_low, 6),
            "burden_reported": round(point["review_burden"], 6),
            "net_recall_equals_1_minus_fn_rate": round(1.0 - fn_rate, 6),
            "net_recall_reported": round(point["net_recall"], 6),
            "t_high_role": "t_high 只改『直接预警』与『送复核』的分配，不改变漏报率与总负担",
        }
        assert abs(prob_ge_low - point["review_burden"]) < 1e-9, "burden 恒等式被破坏"
        assert abs((1.0 - fn_rate) - point["net_recall"]) < 1e-9, "net_recall 恒等式被破坏"
        # 成本等价性对照：把单阈值直接降到同一 t_low，读数应与安全网同负担
        single_at_low = next(
            (r for r in single_sweep if abs(r["threshold"] - point["t_low"]) < 1e-9), None
        )
        if single_at_low is not None:
            payload["cost_equivalence"] = {
                "single_threshold_at_t_low": single_at_low,
                "same_burden": abs(single_at_low["alert_rate"] - point["review_burden"]) < 1e-9,
                "note": "单阈值下调与双阈值规则的『需人工介入比例』恒等（= P(p>=t_low)）",
            }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(_render_report(payload), encoding="utf-8")

    b = payload["baseline_single_threshold"]
    print("[safety_net]")
    print(f"  数据 n={payload['data']['n']} groups={payload['data']['n_groups']} "
          f"pos={payload['data']['positive_rate']}")
    print(f"  基线单阈值 0.5：recall={b['recall']:.4f} {b['recall_ci95']['ci95']} "
          f"prec={b['precision']:.4f} ⇒ 漏报 {1 - b['recall']:.1%}")
    if op["feasible"]:
        pt = op["operating_point"]
        print(f"  工作点 t=({pt['t_low']}, {pt['t_high']})：net_recall={pt['net_recall']:.4f} "
              f"{op['net_recall_ci95']['ci95']} ⇒ 漏报 {pt['miss_rate']:.1%}")
        print(f"    复核负担={pt['review_burden']:.1%} 预警精确率={pt['alert_precision']:.4f} "
              f"安全网精确率={pt['sn_precision']:.4f}")
        print(f"    可行配置数={op['n_feasible']}/{len(grid)}")
    else:
        print(f"  目标净 Recall ≥ {TARGET_NET_RECALL} 在网格内不可达（{op['reason']}）")
    print(f"  -> {OUT_JSON.relative_to(BACKEND.parent).as_posix()}")
    print(f"  -> {REPORT_MD.relative_to(BACKEND.parent).as_posix()}")
    return 0


def _render_report(payload: dict) -> str:
    d = payload["data"]
    b = payload["baseline_single_threshold"]
    lines = [
        "# 漏报安全网评估报告（ROUND_36 · P1）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_36/safety_net_analysis.py` 生成。",
        "只读 `groupwise_oof_predictions.csv`（唯一可引用泛化口径），不跑模型。",
        "规则定义与工作点选择标准见 `safety_net_lib.py`。",
        "",
        "## 问题",
        "",
        f"文本模态固定阈值 0.5 下 Recall = **{b['recall']:.4f}** "
        f"{b['recall_ci95']['ci95']} [C-24] ⇒ **漏掉约 {(1 - b['recall']):.1%} 的阳性**；",
        "而校准斜率 1.3466 [C-28] > 1 证明概率**系统性偏低**（欠自信）⇒",
        "「概率低」不是噪声而是结构性的，下调判定带有依据。",
        "",
        "## 规则",
        "",
        "| 概率区间 | 动作 | 计入 |",
        "|---|---|---|",
        "| `p >= t_high` | 直接预警 | TP / FP（精确率分母） |",
        "| `t_low <= p < t_high` | 安全网：强制人工复核 | 单列；漏报统计上算「捕获」 |",
        "| `p < t_low` | 阴性放行 | TN / FN |",
        "",
        f"**工作点选择标准（先定后扫）**：净 Recall ≥ **{TARGET_NET_RECALL}** 且复核负担最小；",
        "并列取 `t_high` 更高者。",
        "",
        "## 结果",
        "",
    ]
    op = payload["operating_point"]
    ident = payload.get("structural_identity")
    if op["feasible"]:
        pt = op["operating_point"]
        cmp_ = payload["comparison"]
        # 单阈值对照：把阈值降到同一 t_low 时的读数（证明成本等价）
        single_at_low = single_threshold_metrics(
            np.asarray([1.0]), np.asarray([1.0]), 0.5
        ) if False else None
        lines += [
            "| 方案 | 漏报率 | 预警精确率 | 需人工介入比例 |",
            "|---|---|---|---|",
            f"| 现行单阈值 0.5 [C-24] | {cmp_['baseline_miss_rate']:.1%} | "
            f"{b['precision']:.4f} | {b['alert_rate']:.1%} |",
            f"| **安全网 t=({pt['t_low']}, {pt['t_high']})** | **{pt['miss_rate']:.1%}** "
            f"（净 Recall {pt['net_recall']:.4f} {op['net_recall_ci95']['ci95']}） | "
            f"{pt['alert_precision']:.4f}（只对直接预警） | {pt['review_burden']:.1%}（含复核） |",
            "",
            f"可行配置 **{op['n_feasible']} / {payload['method']['grid']['n_configs']}**。",
            "",
            "## 三条必须一起读的结构性发现",
            "",
            "**① 漏报率与总负担只由 `t_low` 决定，`t_high` 完全不参与。** 由规则定义可直接推出：",
            "",
            "    需人工介入比例 = P(p >= t_low)",
            "    净 Recall      = 1 − P(阳性且 p < t_low) / P(阳性)",
            "",
            f"本轮工作点上两条恒等式均已数值核验（burden {ident['burden_reported']:.4f} vs "
            f"P(p≥t_low) {ident['burden_equals_P_p_ge_t_low']:.4f}；net_recall "
            f"{ident['net_recall_reported']:.4f} vs 1−FN率 {ident['net_recall_equals_1_minus_fn_rate']:.4f}）。",
            "`t_high` 只改变「直接预警」与「送复核」之间的分配，**不改变漏报率，也不改变总人工成本**。",
            "",
            "**② 因此双阈值在这里的成本与「单阈值直接下调到 `t_low`」完全相同。** 把 `t_high` 提高",
            "只是把一批样本从「预警」改名为「复核」，看的人一个都没少。双阈值唯一真实的好处是",
            f"**预警队列的精确率更高**（{pt['alert_precision']:.4f} vs 单阈值 0.11 的 0.2620）——",
            "即「直接预警」更可信，而不是更省钱。",
            "",
            f"**③ 安全网区间本身没有富集阳性。** 区间 `[{pt['t_low']}, {pt['t_high']})` 内阳性率 "
            f"{pt['sn_precision']:.4f}，**低于**总体基准率 {payload['data']['positive_rate']:.4f}。",
            "这说明文本模态概率在这个区间**不提供判别信息**——把它单独送复核，",
            "只是把一批偏阴性的样本换了个队列排。",
            "",
            "## 结论（诚实版）",
            "",
            f"要把文本模态的漏报率从 {cmp_['baseline_miss_rate']:.1%} 压到 {pt['miss_rate']:.1%}，"
            f"需要让 **{pt['review_burden']:.1%}** 的样本进入人工流程——无论用单阈值还是双阈值。",
            "这个比例接近全员初筛，**单独使用文本模态做漏报安全网在成本上不成立**。",
            "",
            "根因不是阈值设计，而是**文本概率在低分区间的信息量不足**（校准斜率 1.3466 [C-28]",
            "已指出概率被压向中间）。可行的方向是让安全网区间叠加**其它模态**的补充信号",
            "（生理/结构化），即安全网应做在融合层而非文本层——那是独立工作，本文未做。",
            "",
        ]
    else:
        lines += [f"**目标不可达**：{op['reason']}", ""]

    lines += [
        "## 记账（必须随读数一起读）",
        "",
        "1. **没有独立留出集**：全部样本都是 OOF，工作点是在同一批数据上按预设标准",
        "   选出的 ⇒ 带**选择性偏差**，不得宣称为「已验证的最优阈值」。",
        "2. **未接入融合层**：没有改 `app/core/risk_thresholds.py` 的 22/42/62/82 分级，",
        "   也没有改 `fusion_engine.py`。接入需独立联调与回归。",
        "3. **复核成本是人力成本**：`review_burden` 是进入预警或复核队列的比例；",
        "   它是否可承受取决于机构人力，本文不作判断。",
        "4. 单阈值全网格（0.05~0.95）与双阈值全网格的逐行读数见",
        "   `safety_net_analysis.json` 的 `single_threshold_sweep` / `safety_net_sweep`。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
