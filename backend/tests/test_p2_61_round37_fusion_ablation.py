"""ROUND_37（P1 融合消融）：模态缺失下融合等级翻转的测试接入。

职责边界：
1. **redistribute_weights 数学性质**（权重和守恒、缺失归零、全零均分、关闭开关时
   的行为）——这是消融翻转的根因，必须钉死；
2. **手算样例**：若干组合的 risk_level 与 redistribute 结果逐位对拍；
3. **产物自洽**：json 的汇总统计可由网格独立重算（不 trust json）；
4. **结构性发现**：worst case 与分层模式必须复算得出（防报告数字手写漂移）；
5. **口径边界**：产物必须自证「输入是合成网格、非真实样本」——防被当成性能证据引用。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
V137 = BACKEND / "scripts" / "modeling" / "eval" / "v1_37"
ABL_JSON = V137 / "fusion_ablation.json"

sys.path.insert(0, str(BACKEND))
from app.core.risk_thresholds import NonFiniteRiskScoreError  # noqa: E402
from app.ml.fusion_engine import DEFAULT_WEIGHTS, FusionEngine  # noqa: E402

MODALITIES = ("structured", "text", "physiological")


@pytest.fixture(scope="module")
def engine() -> FusionEngine:
    return FusionEngine()


# ────────────────────── 1. redistribute_weights 数学性质 ──────────────────────


def test_redistribute_sums_to_one(engine: FusionEngine) -> None:
    """任何可用模态子集，再分配后权重和必须为 1（否则融合总分偏置）。"""
    from itertools import combinations

    for k in range(1, 4):
        for subset in combinations(MODALITIES, k):
            w = engine.redistribute_weights(set(subset))
            assert set(w) == set(subset)
            assert sum(w.values()) == pytest.approx(1.0, abs=1e-12), f"{subset} ⇒ {w}"


def test_redistribute_drops_missing_modalities(engine: FusionEngine) -> None:
    """缺失模态的权重必须归零（不出现在结果里）。"""
    w = engine.redistribute_weights({"structured", "text"})
    assert "physiological" not in w
    assert set(w) == {"structured", "text"}


def test_redistribute_preserves_relative_ratio(engine: FusionEngine) -> None:
    """再分配只做归一化，不改变剩余模态间的相对比例。"""
    w = engine.redistribute_weights({"structured", "text"})
    # 0.55 : 0.30 归一化后仍应是 11:6
    assert w["structured"] / w["text"] == pytest.approx(0.55 / 0.30, abs=1e-12)


def test_redistribute_single_modality_gets_full_weight(engine: FusionEngine) -> None:
    """只剩一个模态时权重为 1.0 —— 这正是「低权重模态独占决策」的放大机制。"""
    for m in MODALITIES:
        w = engine.redistribute_weights({m})
        assert w == {m: 1.0}


def test_redistribute_empty_returns_empty(engine: FusionEngine) -> None:
    assert engine.redistribute_weights(set()) == {}


def test_redistribute_all_zero_weights_branch_is_unreachable() -> None:
    """**实测发现（ROUND_37）**：`redistribute_weights` 里「权重全零时均分」的分支
    在生产中**不可达**——`FusionEngine.__init__` 先做 `v / total`，total=0 时直接
    ZeroDivisionError，根本走不到 redistribute。

    这条测试钉死的是「防御性不可达」这一事实本身：该分支是死代码，任何依赖它的
    推理都不成立。若未来有人让 __init__ 容忍全零权重，此测试会转而验证均分行为。
    """
    with pytest.raises(ZeroDivisionError):
        FusionEngine(weights={"structured": 0.0, "text": 0.0, "physiological": 0.0})


def test_redistribute_disabled_switch_skips_normalization() -> None:
    """关闭缺失处理时只做过滤、不归一化（权重和 < 1，行为可预期）。"""
    e = FusionEngine(use_modality_missing_handling=False)
    w = e.redistribute_weights({"structured", "text"})
    assert w == {"structured": 0.55, "text": 0.3}


# ────────────────────── 2. 手算样例 ──────────────────────


def test_fuse_full_three_modality_hand_computed(engine: FusionEngine) -> None:
    """(80, 60, 40) 的融合分可由公式手算复现。

    conf(structured@80) = min(1, (0.5+0.5*0.6)*1.1) = 0.88
    conf(text@60)       = 0.5+0.5*0.2 = 0.6
    conf(physio@40)     = 0.5+0.5*0.2 = 0.6
    w = 0.55*0.88 / 0.3*0.6 / 0.15*0.6 ⇒ 归一化后加权和
    """
    r = engine.fuse({"structured": 80.0, "text": 60.0, "physiological": 40.0})
    conf_s = min(1.0, (0.5 + 0.5 * abs(80 - 50) / 50) * 1.1)
    conf_t = 0.5 + 0.5 * abs(60 - 50) / 50
    conf_p = 0.5 + 0.5 * abs(40 - 50) / 50
    raw = {"structured": 0.55 * conf_s, "text": 0.30 * conf_t, "physiological": 0.15 * conf_p}
    total = sum(raw.values())
    expected = sum(v * (raw[k] / total) for k, v in
                   {"structured": 80.0, "text": 60.0, "physiological": 40.0}.items())
    # 引擎的 risk_score 展示精度为 2 位小数 ⇒ 容差取半个末位
    assert r["risk_score"] == pytest.approx(expected, abs=5e-3)
    assert r["fusion_scheme"] == "full_three_modality"


def test_fuse_empty_scores_is_safe(engine: FusionEngine) -> None:
    r = engine.fuse({})
    assert r["risk_score"] == 0.0 and r["risk_level"] == 0
    assert r["fusion_scheme"] == "empty"


def test_fuse_rejects_non_finite(engine: FusionEngine) -> None:
    """NaN / Inf 必须被显式拒绝（P1-18 的 fail-closed 语义，不许静默裁剪）。"""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(NonFiniteRiskScoreError):
            engine.fuse({"structured": bad, "text": 50.0})


def test_fuse_rejects_non_numeric(engine: FusionEngine) -> None:
    # None 走类型校验 ⇒ TypeError；bool 走有限性校验 ⇒ NonFinite（两条不同代码路径）
    with pytest.raises(TypeError):
        engine.fuse({"structured": None, "text": 50.0})
    with pytest.raises(NonFiniteRiskScoreError):
        engine.fuse({"structured": True, "text": 50.0})


# ────────────────────── 3. 产物自洽（独立重算，不 trust json） ──────────────────────


def _payload() -> dict:
    assert ABL_JSON.exists(), f"缺少 {ABL_JSON}（先跑 v1_37/fusion_ablation.py）"
    return json.loads(ABL_JSON.read_text(encoding="utf-8"))


def _recompute_summary(engine: FusionEngine) -> dict:
    """用同一网格独立重算汇总（刻意不复用脚本函数）。"""
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
                full = engine.fuse(scores)["risk_level"]
                row = {"full_level": full, "spread": max(scores.values()) - min(scores.values())}
                for name, mods in keep.items():
                    row[name] = engine.fuse({m: scores[m] for m in mods})["risk_level"]
                rows.append(row)
    out = {}
    for name in keep:
        deltas = np.array([r[name] - r["full_level"] for r in rows], dtype=np.int64)
        out[name] = {
            "flip_rate": float((np.abs(deltas) >= 1).mean()),
            "max_abs_delta": int(np.abs(deltas).max()),
        }
    return out, rows


def test_ablation_json_summary_matches_recompute(engine: FusionEngine) -> None:
    truth, _ = _recompute_summary(engine)
    payload = _payload()
    for name, t in truth.items():
        s = payload["summary"][name]
        # 产物的 flip_rate 是 4 位展示精度 ⇒ 容差半个末位
        assert s["flip_rate"] == pytest.approx(t["flip_rate"], abs=5e-5), name
        assert s["max_abs_delta"] == t["max_abs_delta"], name


def test_ablation_json_grid_is_exhaustive() -> None:
    payload = _payload()
    n = payload["grid"]["n_combinations"]
    assert n == 11 ** 3 == 1331
    assert len(payload["summary"]) == 6  # 6 个消融配置（不含 full）


def test_ablation_json_worst_case_recomputable(engine: FusionEngine) -> None:
    """worst case 必须能从网格重算出来（防报告数字手写漂移）。"""
    payload = _payload()
    grid = list(range(0, 101, 10))
    worst = None
    for s in grid:
        for t in grid:
            for p in grid:
                scores = {"structured": float(s), "text": float(t), "physiological": float(p)}
                full = engine.fuse(scores)["risk_level"]
                only_p = engine.fuse({"physiological": float(p)})["risk_level"]
                d = abs(only_p - full)
                if worst is None or d > worst[0]:
                    worst = (d, s, t, p, full, only_p)
    top = payload["worst_cases"][0]
    assert top["structured"] == worst[1] and top["text"] == worst[2]
    assert top["physiological"] == worst[3]
    assert top["full_level"] == worst[4]
    assert top["only_physiological_level"] == worst[5]


def test_ablation_json_engine_matches_production_defaults(engine: FusionEngine) -> None:
    """产物里记录的引擎参数必须与生产 DEFAULT_WEIGHTS 一致（防跑了别的配置）。"""
    payload = _payload()
    assert payload["engine"]["weights"] == DEFAULT_WEIGHTS
    assert payload["engine"]["use_confidence_weighting"] is True


def test_ablation_json_declares_synthetic_input() -> None:
    """口径边界：产物必须自证输入是合成网格，防被当成性能证据引用。"""
    payload = _payload()
    note = payload["_note"]
    assert "合成" in note and "不是模型性能" in note
    assert "确定性分数网格" in note


def test_ablation_stratified_pattern_is_monotone() -> None:
    """结构性发现：分歧越大翻转越剧烈（agree < moderate < conflict 的翻转率）。"""
    payload = _payload()
    for name, s in payload["summary"].items():
        strata = s["by_stratum"]
        rates = [strata[k]["flip_rate"] for k in ("agree", "moderate", "conflict") if k in strata]
        assert rates == sorted(rates), f"{name} 的分层翻转率非单调：{rates}"


def test_ablation_report_exists_and_marks_boundary() -> None:
    report = BACKEND.parent / "docs" / "model-evaluation" / "FUSION_ABLATION_REPORT.md"
    assert report.exists(), f"缺少 {report}"
    text = report.read_text(encoding="utf-8")
    assert "合成" in text and "不是模型性能" in text
