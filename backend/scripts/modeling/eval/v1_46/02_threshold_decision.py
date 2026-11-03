#!/usr/bin/env python
"""ROUND_46 P0-2: threshold decision table for the three production modalities.

Reads the model-card point estimates (01_model_cards.py) and adds operating-point
bootstrap CIs plus deployment-prevalence alert burden. No model, artifact, or
production threshold is modified; this is a read-only decision aid.

The production cuts are risk-level onsets (mild/moderate/high/critical), not
clinical diagnostic thresholds. PPV/NPV at 15% prevalence use Bayes reweighting
of the measured sensitivity/specificity; they do not assume the test prevalence
is the deployment prevalence.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_46/02_threshold_decision.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
for path in (BACKEND, HERE, PROJECT_ROOT / "scripts" / "ml_training"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from model_card_lib import bootstrap_threshold_metrics, ppv_npv_at_prevalence  # noqa: E402


def _load_model_cards_module():
    spec = importlib.util.spec_from_file_location("round46_model_cards", HERE / "01_model_cards.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MC = _load_model_cards_module()

CARDS_JSON = HERE / "model_cards.json"
OUT_JSON = HERE / "threshold_decision.json"
MIRROR_JSON = PROJECT_ROOT / "outputs" / "candidates" / "round46" / "threshold_decision.json"
REPORT_MD = PROJECT_ROOT / "outputs" / "ROUND_46_THRESHOLD_DECISION.md"

BOOTSTRAP_B = 2000
DEPLOY_PREV = 0.15
UNIT_CFG = {
    "structured_v1_23": {
        "cuts": [0.25, 0.45, 0.65, 0.85],
        "labels": ["mild", "moderate", "high", "critical"],
        "extra": [0.50],
        "role": "citable_internal_test",
    },
    "text_groupwise_oof": {
        "cuts": [0.20, 0.40, 0.60, 0.80],
        "labels": ["mild", "moderate", "high", "critical"],
        "extra": [0.50],
        "role": "citable_groupwise_oof",
    },
    "physio_v2_current_split": {
        "cuts": [0.35, 0.55, 0.75, 0.90],
        "labels": ["mild", "moderate", "high", "critical"],
        "extra": [0.50],
        "role": "citable_secondary_small_test",
    },
}


def _finite(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return _finite(obj.item())
    return obj


def _structured_arrays():
    model = MC.load_structured_model()
    test = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "v1_23_external" / "test.csv")
    features = list(model.feature_names_in_)
    y = test[MC.TARGET].to_numpy(dtype=np.int64)
    p = model.predict_proba(test[features])[:, 1]
    return y, p, None


def _text_arrays():
    _, df = MC.read_text_oof()
    return (
        df["label"].to_numpy(dtype=np.int64),
        df["p_groupwise"].to_numpy(dtype=np.float64),
        df["group"].to_numpy(),
    )


def _physio_arrays():
    path = HERE / "physio_val_test_predictions.csv"
    df = pd.read_csv(path)
    test = df[df["split"] == "test"].sort_values("row_index")
    return (
        test["y_true"].to_numpy(dtype=np.int64),
        test["y_score"].to_numpy(dtype=np.float64),
        None,
    )


ARRAY_LOADERS = {
    "structured_v1_23": _structured_arrays,
    "text_groupwise_oof": _text_arrays,
    "physio_v2_current_split": _physio_arrays,
}


def _deployment_row(point: dict) -> dict:
    sens = point["sensitivity"]
    spec = point["specificity"]
    bayes = ppv_npv_at_prevalence(sens, spec, DEPLOY_PREV)
    alert_rate = sens * DEPLOY_PREV + (1.0 - spec) * (1.0 - DEPLOY_PREV)
    tp = point["tp"]
    fp = point["fp"]
    fn = point["fn"]
    tn = point["tn"]
    n = tp + fp + fn + tn
    cut = point["threshold"]
    net_benefit = tp / n - (fp / n) * (cut / (1.0 - cut))
    return {
        "ppv_at_15pct": bayes["ppv"],
        "npv_at_15pct": bayes["npv"],
        "alert_rate_at_15pct": alert_rate,
        "alerts_per_1000_at_15pct": alert_rate * 1000.0,
        "net_benefit_at_test_prevalence": net_benefit,
    }


def build_unit(name: str, cfg: dict) -> dict:
    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    unit = cards["units"][name]
    table = unit["threshold_table"]
    y, p, groups = ARRAY_LOADERS[name]()
    all_cuts = list(cfg["cuts"]) + [c for c in cfg["extra"] if c not in cfg["cuts"]]
    ci = bootstrap_threshold_metrics(
        y, p, all_cuts, groups=groups, B=BOOTSTRAP_B, seed=42
    )
    rows = []
    level_by_cut = dict(zip(cfg["cuts"], cfg["labels"]))
    for cut in all_cuts:
        key = f"{cut:.2f}"
        point = dict(table[key])
        row = {
            "cut": cut,
            "level_onset": level_by_cut.get(cut, "binary_reference_not_a_risk_cut"),
            "production_risk_cut": cut in cfg["cuts"],
            **point,
            **_deployment_row(point),
            "bootstrap_ci95": {k: v for k, v in ci[key].items()},
        }
        rows.append(row)
    return {
        "role": cfg["role"],
        "source": unit.get("source"),
        "n": unit["card"]["n"],
        "positive_rate": unit["card"]["positive_rate"],
        "deployment_prevalence_for_bayes": DEPLOY_PREV,
        "cuts": rows,
        "operating_points": unit["operating_points"],
        "dca_summary": {
            "model_beats_treat_none_ranges": unit["dca"].get("model_beats_treat_none_ranges"),
            "model_beats_treat_all_ranges": unit["dca"].get("model_beats_treat_all_ranges"),
        },
        "bootstrap_meta": ci["_meta"],
    }


def _fmt_ci(ci: dict) -> str:
    lo, hi = ci["ci95"]
    if lo is None or hi is None:
        return "n/a"
    return f"{lo:.3f}-{hi:.3f}"


def render_report(units: dict) -> str:
    lines = [
        "# ROUND_46 阈值决策表（P0-2）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_46/02_threshold_decision.py` 生成。",
        "只读模型卡与逐样本预测，**没有修改任何生产阈值**。",
        "",
        "## 怎么读这张表",
        "",
        "- `mild / moderate / high / critical` 是生产风险等级的**起始切点**，不是临床诊断阈值。",
        "- `PPV@15%` / `NPV@15%` / `告警数/千` 用灵敏度、特异度按 15% 部署阳性率做 Bayes 重加权；",
        "  测试集阳性率（见每节 n/prev）不是部署阳性率。",
        "- 方括号为 95% bootstrap 分位 CI（B=2000，seed=42；文本按 group 重采样，其余按行）。",
        "- 净获益按测试集阳性率计算：`TP/n - FP/n · t/(1-t)`；跨阳性率比较请看 DCA 区间。",
        "",
        "## 汇总读数",
        "",
        "| 单元 | 切点 | 等级起点 | 灵敏度 [95%CI] | 特异度 [95%CI] | PPV@测试 | PPV@15% | 告警/千@15% | 净获益 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, u in units.items():
        for row in u["cuts"]:
            ci = row["bootstrap_ci95"]
            level = row["level_onset"]
            if not row["production_risk_cut"]:
                level = "0.5 二元参考"
            lines.append(
                f"| `{name}` | {row['cut']:.2f} | {level} "
                f"| {row['sensitivity']:.3f} [{_fmt_ci(ci['sensitivity'])}] "
                f"| {row['specificity']:.3f} [{_fmt_ci(ci['specificity'])}] "
                f"| {row['ppv']:.3f} | {row['ppv_at_15pct']:.3f} "
                f"| {row['alerts_per_1000_at_15pct']:.0f} "
                f"| {row['net_benefit_at_test_prevalence']:.4f} |"
            )

    lines += [
        "",
        "## 各单元明细",
        "",
    ]
    for name, u in units.items():
        op = u["operating_points"]
        lines += [
            f"### `{name}`",
            "",
            f"- n={u['n']}，测试阳性率 {u['positive_rate']:.4f}，角色 {u['role']}",
            f"- 筛检点（灵敏度≥90%）：阈值 {op.get('screening_sens90', {}).get('threshold')}，"
            f"灵敏度 {op.get('screening_sens90', {}).get('sensitivity')}，"
            f"特异度 {op.get('screening_sens90', {}).get('specificity')}",
            f"- 分诊点（PPV≥50% @15%）：阈值 {op.get('triage_ppv50_at_target', {}).get('threshold')}，"
            f"灵敏度 {op.get('triage_ppv50_at_target', {}).get('sensitivity')}，"
            f"特异度 {op.get('triage_ppv50_at_target', {}).get('specificity')}",
            "- DCA：模型优于 treat_none 的阈值区间 "
            f"{u['dca_summary']['model_beats_treat_none_ranges']}；"
            "优于 treat_all 的区间 "
            f"{u['dca_summary']['model_beats_treat_all_ranges']}",
            "",
        ]

    lines += [
        "## 建议（不改生产阈值）",
        "",
        "1. **mild 切点只适合筛检/人工复核，不适合作为自动诊断。** 三个模态在 mild 切点都接近",
        "   「宁可多报」：结构化 0.25 灵敏度约 0.96、文本 0.20 约 0.92、生理 0.35 约 0.98；",
        "   但 15% 阳性率下 PPV 只有约 0.23~0.29，意味着多数告警需要靠人工复核消化。",
        "2. **容量受限时按任务选点，而不是把 mild 切点当唯一阈值。** 若目标是筛检（少漏），",
        "   用表内 mild；若目标是分诊（少误报、高 PPV），用各单元的 `triage_ppv50_at_target` 点，",
        "   并明确接受灵敏度下降。",
        "3. **文本 0.20 的告警负担需要前端/人力容量验证。** 在 15% 阳性率下按当前灵敏度/特异度",
        "   估算，告警量仍可能超过每千人 500 条；产品上必须有人工复核与危机安全网承接。",
        "4. **本次不做任何阈值变更。** 切点调整会改变生产风险等级分布与告警量，需产品/临床",
        "   评审与回归验证，属于本轮的「建议」而非「已执行」。",
        "",
        "## 边界",
        "",
        "- 结构化与生理为单次内部切分；生理 n=157，CI 很宽，只作次级引用。",
        "- 文本为 groupwise sibling-aware OOF（n=8379 / 1277 组），是中文文本唯一可引用泛化口径；",
        "  文本级 OOF 的虚高读数不得用于本表。",
        "- PPV/NPV 的 15% 是敏感性假设，不是本仓实测部署阳性率。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    units = {name: build_unit(name, cfg) for name, cfg in UNIT_CFG.items()}
    payload = {
        "_note": (
            "ROUND_46 P0-2 threshold decision table. Read-only; no production threshold changed. "
            "Risk cuts are ordinal triage onsets, not clinical diagnostic thresholds. "
            "PPV/NPV at 15% prevalence are Bayes-reweighted from measured sensitivity/specificity."
        ),
        "deployment_prevalence_for_ppv": DEPLOY_PREV,
        "bootstrap": {"B": BOOTSTRAP_B, "seed": 42, "method": "percentile; text resamples groups"},
        "units": units,
    }
    cleaned = _finite(payload)
    OUT_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    MIRROR_JSON.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_report(units), encoding="utf-8")

    print("[threshold_decision]")
    for name, u in units.items():
        mild = u["cuts"][0]
        print(
            f"  {name:28s} n={u['n']:5d} mild={mild['cut']:.2f} "
            f"sens={mild['sensitivity']:.3f} spec={mild['specificity']:.3f} "
            f"ppv@15={mild['ppv_at_15pct']:.3f} alerts/1k@15={mild['alerts_per_1000_at_15pct']:.0f}"
        )
    print(f"  -> {OUT_JSON.relative_to(BACKEND.parent)}")
    print(f"  -> {REPORT_MD.relative_to(BACKEND.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
