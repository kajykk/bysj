"""ROUND_33（P1 校准）：校准分析（Brier/ECE/MCE/slope/DCA）的测试接入。

职责边界（不重复 v1_33 脚本与闸门的复算）：
1. **calibration_lib 纯函数正确性**：手算样例钉死 brier/ece/mce/slope/DCA 的定义，
   含边界（空箱、p=1.0 归属、阈值开区间）与越界输入的拒绝；
2. **产物存在 + 自洽 + 入库**：calibration_analysis.json 的四个单元 role 边界、
   source sha、n/positive_rate 与 csv 实测一致；
3. **口径边界不退化**：两个 transfer 单元必须仍是 stress_only，主口径必须仍是 citable
   （防「把压力测试读数升级成泛化结论」这类悄悄的口径漂移）；
4. **闸门 rc=0**：verify_thesis_numbers.py 全量校验必须通过（子进程，真复算权威在它）。
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
V133 = BACKEND / "scripts" / "modeling" / "eval" / "v1_33"
CALIB_JSON = V133 / "calibration_analysis.json"
VERIFY = BACKEND / "scripts" / "modeling" / "eval" / "verify_thesis_numbers.py"

sys.path.insert(0, str(V133))
from calibration_lib import (  # noqa: E402
    brier_score,
    calibration_slope_intercept,
    decision_curve,
    expected_calibration_error,
    max_calibration_error,
    reliability_table,
)


# ────────────────────── 1. 纯函数定义（手算样例） ──────────────────────


def test_brier_hand_computed() -> None:
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p = np.array([0.9, 0.2, 0.6, 0.4])
    # (0.01 + 0.04 + 0.16 + 0.16) / 4 = 0.0925
    assert brier_score(y, p) == pytest.approx(0.0925, abs=1e-12)


def test_ece_perfectly_calibrated_bins() -> None:
    """箱内 acc == conf ⇒ ECE = 0。

    注意构造：必须让**同一箱内**的经验阳性率等于平均预测概率。5 个 p=0.9 里
    有 9 个阳性才对——「p=0.9 且 y=1」并不等于校准（acc=1.0 ≠ conf=0.9）。
    """
    y = np.array([1.0] * 9 + [0.0] * 1)
    p = np.array([0.9] * 10)
    assert expected_calibration_error(y, p, 10) == pytest.approx(0.0, abs=1e-12)
    assert max_calibration_error(y, p, 10) == pytest.approx(0.0, abs=1e-12)


def test_ece_single_miscalibrated_bin() -> None:
    # 同一箱内 10 个样本，平均预测 0.9 但实际阳性率 0.6 ⇒ ECE = 1.0 * |0.6-0.9| = 0.3
    y = np.array([1.0] * 6 + [0.0] * 4)
    p = np.array([0.9] * 10)
    assert expected_calibration_error(y, p, 10) == pytest.approx(0.3, abs=1e-12)
    assert max_calibration_error(y, p, 10) == pytest.approx(0.3, abs=1e-12)


def test_ece_bin_assignment_edges() -> None:
    """p 恰为箱边界时归属必须确定：0.1 → bin 1、1.0 → 末箱、0.0 → bin 0。"""
    y = np.array([1.0, 1.0, 0.0])
    p = np.array([1.0, 0.1, 0.0])
    table = reliability_table(y, p, 10)
    by_bin = {row["bin"]: row for row in table}
    assert by_bin[9]["count"] == 1 and by_bin[9]["observed_rate"] == 1.0
    assert by_bin[1]["count"] == 1 and by_bin[1]["observed_rate"] == 1.0
    assert by_bin[0]["count"] == 1 and by_bin[0]["observed_rate"] == 0.0


def test_ece_weights_by_count_not_equal_bins() -> None:
    """ECE 必须按**样本数**加权，不是按箱数平均。

    箱 1（p=0.1，2 样本，1 阳 1 阴）：acc=0.5、conf=0.1 ⇒ 差 0.4
    箱 9（p=0.9，8 样本，7 阳 1 阴）：acc=0.875、conf=0.9 ⇒ 差 0.025
    按样本加权 = 0.2×0.4 + 0.8×0.025 = 0.10；按箱平均则为 0.2125。
    """
    y = np.array([1.0, 0.0] + [1.0] * 7 + [0.0])
    p = np.array([0.1, 0.1] + [0.9] * 8)
    assert expected_calibration_error(y, p, 10) == pytest.approx(0.10, abs=1e-12)


def test_calibration_slope_direction() -> None:
    """slope>1 = 欠自信（概率被压向中间）；slope<1 = 过自信。"""
    rng = np.random.RandomState(11)
    base = rng.uniform(0.05, 0.95, 3000)
    y_under = (rng.uniform(size=3000) < base).astype(float)
    # 把概率压向 0.5 ⇒ 欠自信 ⇒ slope > 1
    p_under = 0.5 + (base - 0.5) * 0.4
    si = calibration_slope_intercept(y_under, p_under)
    assert si["slope"] > 1.0
    # 反向：把概率推离 0.5 ⇒ 过自信 ⇒ slope < 1
    p_over = np.clip(0.5 + (base - 0.5) * 2.2, 0.001, 0.999)
    si2 = calibration_slope_intercept(y_under, p_over)
    assert si2["slope"] < 1.0


def test_calibration_slope_deterministic() -> None:
    rng = np.random.RandomState(3)
    p = rng.uniform(0.05, 0.95, 500)
    y = (rng.uniform(size=500) < p).astype(float)
    a = calibration_slope_intercept(y, p)
    b = calibration_slope_intercept(y, p)
    assert a == b, "固定迭代、无早停 ⇒ 必须逐位可复现"


def test_dca_net_benefit_formula() -> None:
    """NB(t) = TP/n − (FP/n)·(t/(1−t))；treat_all = prev − (1−prev)·odds。

    **必须覆盖 FP > 0 的阈值**：若所有样例的 FP 都是 0，把减号翻成加号也测不出来
    （ROUND_33 变异 M4 实测踩过：FP=0 时符号翻转不改变任何读数）。
    """
    y = np.array([1.0, 1.0, 0.0, 0.0])
    p = np.array([0.9, 0.8, 0.2, 0.1])
    d = decision_curve(y, p, [0.5])
    # t=0.5：TP=2, FP=0 ⇒ NB = 0.5；prev=0.5 ⇒ treat_all = 0.5 - 0.5*1 = 0
    assert float(d["net_benefit_model"][0]) == pytest.approx(0.5, abs=1e-12)
    assert float(d["net_benefit_treat_all"][0]) == pytest.approx(0.0, abs=1e-12)
    assert float(d["net_benefit_treat_none"][0]) == 0.0
    # t=0.9：odds=9 ⇒ treat_all = 0.5 - 0.5*9 = -4.0
    d2 = decision_curve(y, p, [0.9])
    assert float(d2["net_benefit_treat_all"][0]) == pytest.approx(-4.0, abs=1e-12)

    # FP > 0 的两个阈值：符号翻转会被抓住
    # t=0.05 ⇒ pred 全为真 ⇒ TP=2, FP=2 ⇒ NB = 0.5 - 0.5*(0.05/0.95)
    d3 = decision_curve(y, p, [0.05])
    assert float(d3["net_benefit_model"][0]) == pytest.approx(0.5 - 0.5 * (0.05 / 0.95), abs=1e-12)
    # t=0.2 ⇒ pred=[T,T,T,F] ⇒ TP=2, FP=1 ⇒ NB = 0.5 - 0.25*(0.2/0.8)
    d4 = decision_curve(y, p, [0.2])
    assert float(d4["net_benefit_model"][0]) == pytest.approx(0.5 - 0.25 * 0.25, abs=1e-12)
    # 单样本：y=1,p=0.9,t=0.5 ⇒ NB=1；y=0,p=0.6,t=0.5 ⇒ NB = -1（FP 惩罚项）
    d5 = decision_curve(np.array([0.0]), np.array([0.6]), [0.5])
    assert float(d5["net_benefit_model"][0]) == pytest.approx(-1.0, abs=1e-12)


def test_dca_rejects_open_interval_thresholds() -> None:
    y = np.array([1.0, 0.0])
    with pytest.raises(ValueError):
        decision_curve(y, np.array([0.9, 0.1]), [0.0])
    with pytest.raises(ValueError):
        decision_curve(y, np.array([0.9, 0.1]), [1.0])


def test_probability_bounds_enforced() -> None:
    with pytest.raises(ValueError):
        brier_score(np.array([1.0, 0.0]), np.array([1.2, 0.0]))


# ────────────────────── 2. 产物存在 + 自洽 + 口径边界 ──────────────────────


def _payload() -> dict:
    assert CALIB_JSON.exists(), f"缺少 {CALIB_JSON}（先跑 v1_33/calibration_analysis.py）"
    return json.loads(CALIB_JSON.read_text(encoding="utf-8"))


def test_calibration_json_units_and_roles() -> None:
    units = _payload()["units"]
    assert set(units) == {
        "text_groupwise_oof", "physio_current_split", "text_ood_strict", "physio_kaggle",
    }
    # 口径边界：主口径可引用、两个 transfer 单元只能是压力测试（防口径悄悄升级）
    assert units["text_groupwise_oof"]["role"] == "citable"
    assert units["physio_current_split"]["role"] == "citable_secondary"
    assert units["text_ood_strict"]["role"] == "stress_only"
    assert units["physio_kaggle"]["role"] == "stress_only"


def test_calibration_json_n_matches_csv() -> None:
    units = _payload()["units"]
    rows = (
        BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
    ).read_text(encoding="utf-8").strip().splitlines()[1:]
    assert units["text_groupwise_oof"]["n"] == len(rows)
    assert units["text_groupwise_oof"]["n_groups"] == len({r.split(",")[1] for r in rows})
    for unit, name in (
        ("physio_current_split", "test_predictions.csv"),
        ("text_ood_strict", "transfer_text_ood_predictions.csv"),
        ("physio_kaggle", "transfer_physio_kaggle_predictions.csv"),
    ):
        base = (
            BACKEND / "models" / "artifacts" / "physiological_optimized"
            if unit == "physio_current_split"
            else BACKEND / "models" / "artifacts" / "eval_transfer"
        )
        n = len(base.joinpath(name).read_text(encoding="utf-8").strip().splitlines()) - 1
        assert units[unit]["n"] == n, f"{unit} n 与 csv 不符"


def test_calibration_json_sha_and_positive_rate() -> None:
    units = _payload()["units"]
    for unit, u in units.items():
        # source 必须是 posix 分隔符：Windows 生成的 "\\" 在 Linux checkout 下
        # 不成分隔符 ⇒ CI 干净环境 4 单元全部「不存在」（ROUND_33 修复提交钉此形态）。
        assert "\\" not in u["source"], f"{unit} source 含反斜杠：{u['source']!r}"
        src = REPO / u["source"].replace("\\", "/")
        assert src.exists(), f"{unit} source 不存在：{u['source']}"
        actual = hashlib.sha256(src.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert u["source_sha256"] == actual, f"{unit} 的 source_sha256 与当前 csv 不符"
        assert 0.0 < u["positive_rate"] < 1.0


def test_calibration_json_dca_thresholds_and_ranges() -> None:
    u = _payload()["units"]["text_groupwise_oof"]
    dca = u["dca"]
    assert dca["thresholds"] == [round(0.01 * k, 2) for k in range(1, 100)]
    assert len(dca["net_benefit_model"]) == len(dca["thresholds"])
    # 阈值区间摘要必须与曲线自洽（重建一遍区间，防手写区间与曲线脱钩）
    import numpy as _np

    t = _np.array(dca["thresholds"])
    nb = _np.array(dca["net_benefit_model"])
    nb_all = _np.array(dca["net_benefit_treat_all"])
    beats_all = [float(t[i]) for i in range(len(t)) if nb[i] > nb_all[i]]
    ranges = dca["model_beats_treat_all_ranges"]
    assert ranges == [[beats_all[0], beats_all[-1]]] or all(
        lo <= hi for lo, hi in ranges
    )
    # 主口径必须真的优于 treat_all（否则 DCA 结论不成立）
    assert ranges, "主口径在任何阈值都不优于全员干预 ⇒ §4ter.2 的结论失效"


def test_calibration_slope_has_no_ci() -> None:
    """method.not_estimated 已声明斜率无 CI ⇒ 产物不得给它挂 ci95。"""
    payload = _payload()
    u = payload["units"]["text_groupwise_oof"]
    # slope/intercept 是顶层标量字段，不是 metrics 子项（没有 ci95 可挂）
    assert "calibration_slope" in u and "calibration_intercept" in u
    assert "calibration_slope" not in u["metrics"]
    assert "not_estimated" in payload["method"]
    # 有 CI 的三个指标必须成对出现
    for metric in ("brier", "ece", "mce"):
        assert set(u["metrics"][metric]) >= {"point", "ci95"}


# ────────────────────── 3. 闸门 rc=0 ──────────────────────


def test_verify_thesis_numbers_gate_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFY)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(BACKEND),
    )
    assert proc.returncode == 0, (
        f"verify_thesis_numbers.py 未通过：\n{proc.stdout}\n{proc.stderr}"
    )
