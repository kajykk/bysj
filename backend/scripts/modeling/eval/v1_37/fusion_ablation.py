#!/usr/bin/env python
"""ROUND_37（P1 融合消融）：模态缺失下的融合等级翻转评估。

回答的问题
----------
生产上经常缺模态（用户只填了问卷、只上传了文本、或可穿戴没戴）。
`FusionEngine.redistribute_weights` 会把缺失模态的权重按比例分给剩余模态。
那么：**缺一个模态时，风险等级最多跳几级？在什么分数组合下跳？**

做法：在**确定性分数网格**上穷举，用**真实生产 `FusionEngine`**（默认权重 +
默认置信度加权）对每个组合算「完整三模态」与各消融配置的 risk_level，统计翻转。

边界与记账（先于指标）
----------------------
1. **输入是合成分数网格，不是真实样本**。因此本脚本验证的是**融合层规则的行为
   边界**（权重再分配 + 阈值映射），**不是模型性能**，也不能据此声称任何
   模态的「贡献度」或「重要性」——那需要三模态对齐的真实数据。
2. **三模态对齐数据在本仓不存在**：文本 OOF 8379 行来自 MMPsy 学生、生理测试集
   157 行来自 depresjon、结构化母表是 PHQ-9（且 PHQ-9 就是结构化模型的训练标签
   母体，属泄漏）。三方人群不同 ⇒ 端到端融合消融**没有数据基础**，本轮明确不做。
3. **不给 CI**：网格是确定性穷举而非抽样，分位数 CI 在此没有意义；
   报的是**全集上的精确比例**，不是估计。
4. 不写任何模型产物，不读 registry 旧值；只 import 生产融合引擎。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1__ablation.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.fusion_engine import FusionEngine  # noqa: E402

OUT_JSON = HERE / "fusion_ablation.json"
REPORT_MD = BACKEND.parent / "docs" / "model-evaluation" / "FUSION_ABLATION_REPORT.md"

GRID_STEP = 10
GRID = list(range(0, 101, GRID_STEP))  # 0,10,...,100 ⇒ 11 值
MODALITIES = ("structured", "text", "physiological")

# 消融配置：名字 ⇒ 保留的模态
ABLATIONS: dict[str, tuple[str, ...]] = {
    "full": MODALITIES,
    "drop_structured": ("text", "physiological"),
    "drop_text": ("structured", "physiological"),
    "drop_physiological": ("structured", "text"),
    "only_structured": ("structured",),
    "only_text": ("text",),
    "only_physiological": ("physiological",),
}


def _level(scores: dict[str, float], engine: FusionEngine) -> dict:
    r = engine.fuse(scores)
    return {
        "risk_score": round(float(r["risk_score"]), 4),
        "risk_level": int(r["risk_level"]),
        "confidence": round(float(r["confidence"]), 4),
        "scheme": r["fusion_scheme"],
    }


def classify(spread: float) -> str:
    """按三模态分数的极差分层：一致 / 中等分歧 / 冲突。"""
    if spread < 20:
        return "agree"
    if spread < 40:
        return "moderate"
    return "conflict"


def main() -> int:
    engine = FusionEngine()  # 生产默认权重 + 置信度加权
    rows: list[dict] = []
    for s in GRID:
        for t in GRID:
            for p in GRID:
                scores = {"structured": float(s), "text": float(t), "physiological": float(p)}
                spread = float(max(scores.values()) - min(scores.values()))
                full = _level(scores, engine)
                row = {
                    "structured": s, "text": t, "physiological": p,
                    "spread": spread, "stratum": classify(spread),
                    "full_level": full["risk_level"],
                    "full_score": full["risk_score"],
                }
                for name, keep in ABLATIONS.items():
                    if name == "full":
                        continue
                    row[f"{name}_level"] = _level({m: scores[m] for m in keep}, engine)["risk_level"]
                rows.append(row)

    n = len(rows)
    payload: dict = {
        "_note": (
            "ROUND_37 (P1 融合消融) 模态缺失下的等级翻转评估。输入是**确定性分数网格**"
            "（合成，非真实样本），验证的是融合层规则的行为边界，不是模型性能；"
            "三模态对齐数据在本仓不存在 ⇒ 端到端消融无数据基础，本轮明确不做。"
        ),
        "engine": {
            "weights": engine.weights,
            "use_confidence_weighting": engine.use_confidence_weighting,
            "use_modality_missing_handling": engine.use_modality_missing_handling,
        },
        "grid": {"step": GRID_STEP, "values": GRID, "n_combinations": n},
        "ablation_configs": {k: list(v) for k, v in ABLATIONS.items()},
    }

    # 汇总：每种消融的翻转率与 Δ 分布
    summary: dict[str, dict] = {}
    for name in ABLATIONS:
        if name == "full":
            continue
        deltas = np.array([r[f"{name}_level"] - r["full_level"] for r in rows], dtype=np.int64)
        absd = np.abs(deltas)
        by_stratum: dict[str, dict] = {}
        for stratum in ("agree", "moderate", "conflict"):
            sel = np.array([r["stratum"] == stratum for r in rows])
            if not sel.any():
                continue
            d = np.abs(deltas[sel])
            by_stratum[stratum] = {
                "n": int(sel.sum()),
                "flip_rate": round(float((d >= 1).mean()), 4),
                "max_abs_delta": int(d.max()),
                "mean_abs_delta": round(float(d.mean()), 4),
            }
        summary[name] = {
            "flip_rate": round(float((absd >= 1).mean()), 4),
            "max_abs_delta": int(absd.max()),
            "mean_abs_delta": round(float(absd.mean()), 4),
            "delta_histogram": {str(int(k)): int((deltas == k).sum()) for k in range(-4, 5)},
            "by_stratum": by_stratum,
        }
    payload["summary"] = summary

    # 翻转最严重的组合（按 |Δ| 降序，取前 10，供复算核对）
    worst = sorted(rows, key=lambda r: -max(abs(r[f"{k}_level"] - r["full_level"]) for k in summary))[:10]
    payload["worst_cases"] = [
        {
            "structured": r["structured"], "text": r["text"], "physiological": r["physiological"],
            "stratum": r["stratum"], "full_level": r["full_level"],
            **{f"{k}_level": r[f"{k}_level"] for k in summary},
        }
        for r in worst
    ]

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(_render_report(payload), encoding="utf-8")

    print("[fusion_ablation]")
    print(f"  网格 {len(GRID)}³ = {n} 组合；引擎权重 {engine.weights}")
    for name, s in summary.items():
        print(f"  {name:<18} 翻转率={s['flip_rate']:.3f} 最大|Δ|={s['max_abs_delta']} "
              f"平均|Δ|={s['mean_abs_delta']:.3f}")
    print(f"  -> {OUT_JSON.relative_to(BACKEND.parent).as_posix()}")
    print(f"  -> {REPORT_MD.relative_to(BACKEND.parent).as_posix()}")
    return 0


def _render_report(payload: dict) -> str:
    eng = payload["engine"]
    grid = payload["grid"]
    lines = [
        "# 融合层模态消融报告（ROUND_37 · P1）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_37/fusion_ablation.py` 生成。",
        "输入是**确定性分数网格**（合成），用**真实生产 `FusionEngine`** 评估模态缺失时的",
        "风险等级翻转。**验证的是融合层规则的行为边界，不是模型性能。**",
        "",
        f"- 引擎权重：structured {eng['weights']['structured']} / text {eng['weights']['text']} / "
        f"physiological {eng['weights']['physiological']}",
        f"- 置信度加权：{eng['use_confidence_weighting']}；缺失模态处理：{eng['use_modality_missing_handling']}",
        f"- 网格：三模态分数各取 {grid['values']}（步长 {grid['step']}）⇒ **{grid['n_combinations']}** 个组合，穷举无抽样",
        "",
        "## 翻转汇总",
        "",
        "| 消融配置 | 等级翻转率 | 最大 \\|Δ\\| | 平均 \\|Δ\\| |",
        "|---|---|---|---|",
    ]
    for name, s in payload["summary"].items():
        lines.append(
            f"| `{name}` | {s['flip_rate']:.3f} | {s['max_abs_delta']} | {s['mean_abs_delta']:.3f} |"
        )
    lines += [
        "",
        "## 按分歧度分层（三模态分数极差）",
        "",
        "| 消融配置 | 一致（极差<20） | 中等（20-40） | 冲突（≥40） |",
        "|---|---|---|---|",
    ]
    for name, s in payload["summary"].items():
        cells = []
        for stratum in ("agree", "moderate", "conflict"):
            b = s["by_stratum"].get(stratum)
            cells.append(f"翻转 {b['flip_rate']:.3f} / 最大 {b['max_abs_delta']}" if b else "—")
        lines.append(f"| `{name}` | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines += [
        "",
        "## 翻转最严重的组合（前 10，供复算核对）",
        "",
        "| structured | text | physiological | 分层 | 完整 | 去结构化 | 去文本 | 去生理 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in payload["worst_cases"]:
        lines.append(
            f"| {r['structured']} | {r['text']} | {r['physiological']} | {r['stratum']} | "
            f"{r['full_level']} | {r['drop_structured_level']} | {r['drop_text_level']} | "
            f"{r['drop_physiological_level']} |"
        )
    lines += [
        "",
        "## 记账（必须随读数一起读）",
        "",
        "1. **输入是合成分数网格，不是真实样本** ⇒ 本报告只说明融合层规则的行为，",
        "   **不得**用于声称任何模态的贡献度、重要性或性能。",
        "2. **三模态对齐数据在本仓不存在**（文本来自 MMPsy 学生 8379 行、生理来自",
        "   depresjon 157 行、结构化母表是 PHQ-9 且即训练标签母体），三方人群不同 ⇒",
        "   端到端融合消融没有数据基础，本轮明确不做。",
        "3. **不给 CI**：网格是确定性穷举，报的是全集精确比例而非抽样估计。",
        "4. 消融只改「参与融合的模态集合」，不改模型本身，也不改阈值表。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
