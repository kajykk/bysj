"""ROUND_36（P1 漏报安全网）：双阈值规则评估的测试接入。

职责边界：
1. **纯函数定义**（手算样例，**必须覆盖 FP>0**——DCA 那轮的教训：惩罚项在 FP=0 时
   符号翻转测不出来，同理漏报统计在 sn_caught=0 时也测不出问题）；
2. **结构恒等式**：burden = P(p≥t_low)、net_recall = 1 − FN率。这是本轮最重要的
   方法学发现（双阈值与单阈值下调成本恒等），必须被测试钉死；
3. **工作点选择标准**：先定后扫、不可达时如实报告、并列时按预设规则打破；
4. **产物自洽 + 口径边界**：json 存在、sha 对得上、恒等式字段与曲线自洽；
5. **闸门 rc=0**（子进程，真复算权威在 verify_thesis_numbers.py）。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
V136 = BACKEND / "scripts" / "modeling" / "eval" / "v1_36"
SN_JSON = V136 / "safety_net_analysis.json"
VERIFY = BACKEND / "scripts" / "modeling" / "eval" / "verify_thesis_numbers.py"

sys.path.insert(0, str(V136))
from safety_net_lib import (  # noqa: E402
    DEFAULT_T_HIGH_GRID,
    DEFAULT_T_LOW_GRID,
    TARGET_NET_RECALL,
    apply_safety_net,
    pick_operating_point,
    single_threshold_metrics,
    sweep_safety_net,
    sweep_single,
)


# ────────────────────── 1. 纯函数定义（手算样例） ──────────────────────


def test_apply_safety_net_hand_computed_with_fp_and_sn() -> None:
    """手算样例，且 FP>0、sn_caught>0 都覆盖到。

    y = [1, 1, 0, 0, 0, 0]
    p = [0.9, 0.3, 0.15, 0.1, 0.05, 0.02]，t_low=0.05, t_high=0.35
      alert = p>=0.35  ⇒ [T,F,F,F,F,F] ⇒ TP=1 FP=0
      sn    = 0.05<=p<0.35 ⇒ [F,T,T,T,T,F] ⇒ 4 个，其中阳性 1（p=0.3,y=1）
      p<t_low ⇒ [F,F,F,F,F,T] ⇒ y=0 ⇒ TN=1
      net_recall = (1+1)/2 = 1.0；review_burden = (1+0+4)/6 = 5/6
    """
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    p = np.array([0.9, 0.3, 0.15, 0.1, 0.05, 0.02])
    m = apply_safety_net(y, p, 0.05, 0.35)
    assert (m["tp"], m["fp"], m["sn_total"], m["sn_caught"], m["fn"], m["tn"]) == (1, 0, 4, 1, 0, 1)
    assert m["net_recall"] == pytest.approx(1.0, abs=1e-12)
    assert m["review_burden"] == pytest.approx(5.0 / 6.0, abs=1e-12)
    assert m["alert_precision"] == pytest.approx(1.0, abs=1e-12)
    assert m["sn_precision"] == pytest.approx(0.25, abs=1e-12)


def test_apply_safety_net_counts_partition() -> None:
    """六个计数必须恰好划分全部样本（不多不少）。"""
    y = np.array([1.0, 0.0, 1.0, 0.0, 1.0])
    p = np.array([0.9, 0.7, 0.4, 0.2, 0.05])
    for t_low, t_high in ((0.1, 0.5), (0.05, 0.35), (0.3, 0.8)):
        m = apply_safety_net(y, p, t_low, t_high)
        assert m["tp"] + m["fp"] + m["sn_total"] + m["fn"] + m["tn"] == m["n"]
        assert m["tp"] + m["sn_caught"] + m["fn"] == m["n_pos"]
        assert m["fp"] + (m["sn_total"] - m["sn_caught"]) + m["tn"] == m["n_neg"]


def test_apply_safety_net_rejects_degenerate_thresholds() -> None:
    y = np.array([1.0, 0.0])
    p = np.array([0.9, 0.1])
    # t_low == t_high 退化成单阈值 ⇒ 必须拒绝（调用方应改用 single_threshold_metrics）
    with pytest.raises(ValueError):
        apply_safety_net(y, p, 0.3, 0.3)
    with pytest.raises(ValueError):
        apply_safety_net(y, p, 0.4, 0.3)
    with pytest.raises(ValueError):
        apply_safety_net(y, p, 0.0, 0.3)
    with pytest.raises(ValueError):
        apply_safety_net(y, p, 0.3, 1.0)


def test_single_threshold_metrics_hand_computed() -> None:
    y = np.array([1.0, 1.0, 0.0, 0.0])
    p = np.array([0.9, 0.8, 0.2, 0.1])
    m = single_threshold_metrics(y, p, 0.5)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (2, 0, 0, 2)
    assert m["recall"] == pytest.approx(1.0)
    assert m["precision"] == pytest.approx(1.0)
    assert m["f1"] == pytest.approx(1.0)
    assert m["alert_rate"] == pytest.approx(0.5)


# ────────────────────── 2. 结构恒等式（本轮核心方法学发现） ──────────────────────


def test_burden_identity_holds_across_grid() -> None:
    """burden == P(p >= t_low)：t_high 完全不参与负担。"""
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    p = np.array([0.9, 0.3, 0.15, 0.1, 0.05, 0.02, 0.55])
    for t_low in (0.02, 0.05, 0.1, 0.2):
        for t_high in (0.3, 0.5, 0.9):
            m = apply_safety_net(y, p, t_low, t_high)
            expected = float((p >= t_low).mean())
            assert m["review_burden"] == pytest.approx(expected, abs=1e-12), (
                f"t=({t_low},{t_high}) burden 恒等式被破坏"
            )


def test_net_recall_identity_holds_across_grid() -> None:
    """net_recall == 1 − P(阳性且 p<t_low)/P(阳性)。"""
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    p = np.array([0.9, 0.3, 0.15, 0.1, 0.05, 0.02, 0.55])
    pos = y == 1.0
    for t_low in (0.02, 0.05, 0.1, 0.2):
        for t_high in (0.3, 0.5, 0.9):
            m = apply_safety_net(y, p, t_low, t_high)
            expected = 1.0 - float(((p < t_low) & pos).sum() / pos.sum())
            assert m["net_recall"] == pytest.approx(expected, abs=1e-12)


def test_double_threshold_cost_equals_single_threshold_at_t_low() -> None:
    """成本等价：双阈值的 burden == 单阈值下调到 t_low 的 alert_rate。

    这是「双阈值不省钱、只提高预警精确率」的机器化判据。
    """
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0])
    p = np.array([0.9, 0.3, 0.15, 0.1, 0.05, 0.02, 0.55, 0.42])
    for t_low in (0.05, 0.15, 0.3):
        sn = apply_safety_net(y, p, t_low, 0.9)
        single = single_threshold_metrics(y, p, t_low)
        assert sn["review_burden"] == pytest.approx(single["alert_rate"], abs=1e-12)
        assert sn["net_recall"] == pytest.approx(single["recall"], abs=1e-12)


def test_t_high_only_reallocates_between_alert_and_review() -> None:
    """固定 t_low，只改 t_high ⇒ 漏报率与负担不变，只有预警/复核分配变。"""
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    p = np.array([0.9, 0.3, 0.15, 0.1, 0.05, 0.02, 0.55])
    a = apply_safety_net(y, p, 0.05, 0.3)
    b = apply_safety_net(y, p, 0.05, 0.9)
    assert a["net_recall"] == b["net_recall"]
    assert a["review_burden"] == b["review_burden"]
    # t_high 越高，直接预警越少、送复核越多（方向别写反）
    assert a["tp"] + a["fp"] > b["tp"] + b["fp"]
    assert a["sn_total"] < b["sn_total"]


# ────────────────────── 3. 工作点选择标准 ──────────────────────


def test_pick_operating_point_respects_preset_target() -> None:
    """选出的工作点必须满足预设目标（净 Recall ≥ target）。"""
    rng = np.random.RandomState(5)
    p = rng.uniform(0.02, 0.98, 2000)
    y = (rng.uniform(size=2000) < p).astype(float)
    op = pick_operating_point(y, p)
    assert op["feasible"] is True
    assert op["operating_point"]["net_recall"] >= TARGET_NET_RECALL


def test_pick_operating_point_minimizes_burden_among_feasible() -> None:
    """在满足目标的配置里必须取负担最小者（防「挑好看不挑省」）。"""
    rng = np.random.RandomState(5)
    p = rng.uniform(0.02, 0.98, 1500)
    y = (rng.uniform(size=1500) < p).astype(float)
    op = pick_operating_point(y, p)
    assert op["feasible"] is True
    feasible = [
        m for m in sweep_safety_net(y, p, DEFAULT_T_HIGH_GRID, DEFAULT_T_LOW_GRID)
        if m["net_recall"] >= TARGET_NET_RECALL
    ]
    assert op["n_feasible"] == len(feasible)
    assert op["operating_point"]["review_burden"] == pytest.approx(
        min(m["review_burden"] for m in feasible), abs=1e-12
    )


def test_pick_operating_point_reports_infeasible_honestly() -> None:
    """目标不可达时必须如实报告 feasible=False，不偷偷放宽标准。

    同时钉死 NaN 逃逸：无阳性时 net_recall 为 NaN，`NaN < target` 是 False
    会让 NaN 配置混进可行集（ROUND_36 实测踩过，lib 已改用 `not (x >= target)`）。
    """
    y = np.zeros(10)
    p = np.full(10, 0.5)  # 全阴性 ⇒ 任何配置的净 Recall 都是 NaN/0
    op = pick_operating_point(y, p)
    assert op["feasible"] is False
    assert op["n_feasible"] == 0
    assert "不可达" in op["reason"]


def test_pick_operating_point_is_deterministic() -> None:
    rng = np.random.RandomState(9)
    p = rng.uniform(0.02, 0.98, 800)
    y = (rng.uniform(size=800) < p).astype(float)
    a = pick_operating_point(y, p)
    b = pick_operating_point(y, p)
    assert a == b


# ────────────────────── 4. 产物自洽 + 口径边界 ──────────────────────


def _payload() -> dict:
    assert SN_JSON.exists(), f"缺少 {SN_JSON}（先跑 v1_36/safety_net_analysis.py）"
    return json.loads(SN_JSON.read_text(encoding="utf-8"))


def test_safety_net_json_data_matches_csv() -> None:
    payload = _payload()
    rows = (
        BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
    ).read_text(encoding="utf-8").strip().splitlines()[1:]
    assert payload["data"]["n"] == len(rows)
    assert payload["data"]["n_groups"] == len({r.split(",")[1] for r in rows})
    # 行尾不敏感哈希（与 v1_30/v1_33 一致）
    actual = hashlib.sha256(
        (BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv")
        .read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    assert payload["data"]["source_sha256"] == actual


def test_safety_net_json_uses_posix_source_path() -> None:
    """ROUND_33 的教训：Windows 的 str(Path) 会发反斜杠，Linux CI 读不到。"""
    src = _payload()["data"]["source"]
    assert "\\" not in src, f"source 必须是 posix 分隔符：{src!r}"
    assert src.endswith("groupwise_oof_predictions.csv")


def test_safety_net_json_structural_identity_self_consistent() -> None:
    """产物里的恒等式字段必须自洽（burden / net_recall 两侧相等）。"""
    payload = _payload()
    ident = payload["structural_identity"]
    assert ident["burden_equals_P_p_ge_t_low"] == pytest.approx(ident["burden_reported"], abs=1e-6)
    assert ident["net_recall_equals_1_minus_fn_rate"] == pytest.approx(
        ident["net_recall_reported"], abs=1e-6
    )
    cost = payload["cost_equivalence"]
    assert cost["same_burden"] is True
    single = cost["single_threshold_at_t_low"]
    assert single["alert_rate"] == pytest.approx(ident["burden_reported"], abs=1e-6)


def test_safety_net_json_operating_point_matches_recomputed() -> None:
    """工作点必须能由 csv + 预设标准独立复算出来（不只信 json）。"""
    payload = _payload()
    rows = (
        BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
    ).read_text(encoding="utf-8").strip().splitlines()[1:]
    y = np.array([float(r.split(",")[0]) for r in rows])
    p = np.array([float(r.split(",")[2]) for r in rows])
    op = pick_operating_point(y, p, DEFAULT_T_HIGH_GRID, DEFAULT_T_LOW_GRID, TARGET_NET_RECALL)
    assert payload["operating_point"]["feasible"] == op["feasible"]
    if op["feasible"]:
        pt = op["operating_point"]
        assert payload["operating_point"]["operating_point"]["t_low"] == pt["t_low"]
        assert payload["operating_point"]["operating_point"]["t_high"] == pt["t_high"]
        assert payload["operating_point"]["operating_point"]["net_recall"] == pytest.approx(
            pt["net_recall"], abs=1e-6
        )
        assert payload["operating_point"]["operating_point"]["review_burden"] == pytest.approx(
            pt["review_burden"], abs=1e-6
        )


def test_safety_net_json_sweep_grids_complete() -> None:
    payload = _payload()
    n_expected = sum(
        1
        for t_high in DEFAULT_T_HIGH_GRID
        for t_low in DEFAULT_T_LOW_GRID
        if 0.0 < t_low < t_high < 1.0
    )
    assert len(payload["safety_net_sweep"]) == n_expected
    assert len(payload["single_threshold_sweep"]) == 91  # 0.05 .. 0.95 步长 0.01


def test_safety_net_sn_precision_below_prevalence_is_reported() -> None:
    """本轮负面发现必须留在产物里：安全网区间未富集阳性。"""
    payload = _payload()
    pt = payload["operating_point"]["operating_point"]
    assert pt["sn_precision"] < payload["data"]["positive_rate"], (
        "安全网区间阳性率若高于基准率，报告里『无判别力』的结论需重写"
    )


# ────────────────────── 5. 闸门 rc=0 ──────────────────────


def test_verify_thesis_numbers_gate_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFY)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(BACKEND),
    )
    assert proc.returncode == 0, f"verify_thesis_numbers.py 未通过：\n{proc.stdout}\n{proc.stderr}"
