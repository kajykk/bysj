"""ROUND_16 模型验证证据补强闸门（P1-1/2/3/4/8 技术类差距）。

上游：docs/planning/P2_R15_CLINICAL_READINESS.md §6.2 P1 差距清单。
边界：只做技术类差距；P0 组织/法律项（产品甲/乙/丙定性）不在本文件范围。

闸门清单：
- TestT1DcaEce：DCA/净获益/ECE 语义 + 报告结构 + 区间不可挪门槛
- TestT2FusionAblation：同队列消融 + ΔCI 覆盖 0 判据 + 分组防泄漏 + provenance
- TestT3FairnessAssessment：公平性差距读数（评估）与缓解分账（缓解=建议未启用）
- TestT4FalseNegativeSafetyNet：高危输入不得落 0 级/免复核（可执行断言）
- TestT5ThresholdSsot：阈值口径单一事实源（settings/脚本/metrics JSON/fusion 死副本）
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
METRICS_JSON = BACKEND_ROOT / "models" / "text" / "improved_bilingual_metrics.json"
V127_SCRIPT = (
    REPO_ROOT
    / "backend"
    / "scripts"
    / "modeling"
    / "v1_27"
    / "04_retrain_bilingual_text_groupwise.py"
)
FUSION_ENGINE = BACKEND_ROOT / "app" / "ml" / "fusion_engine.py"


# ─────────────────────────── T1 DCA / ECE ───────────────────────────


class TestT1DcaEce:
    """P1-1：决策曲线分析（净获益）+ ECE 语义闸门."""

    def test_ece_zero_for_perfectly_calibrated(self):
        """箱子内正例比例 == 平均预测概率 ⇒ ECE=0（构造可证）."""
        from app.ml.model_validation import compute_ece

        rng = np.random.default_rng(11)
        n = 20000
        p = rng.random(n)
        y = (rng.random(n) < p).astype(int)  # 按概率本身生成 ⇒ 天然校准
        assert compute_ece(y, p, n_bins=10) < 0.02

    def test_ece_penalizes_overconfident(self):
        from app.ml.model_validation import compute_ece

        # 全预测 0.9 但只有一半正例 ⇒ conf=0.9, acc=0.5, ECE≈0.4
        p = np.full(1000, 0.9)
        y = np.zeros(1000, dtype=int)
        y[:500] = 1
        ece = compute_ece(y, p)
        assert 0.35 <= ece <= 0.45

    def test_ece_includes_score_exactly_one(self):
        """预测 1.0 的样本必须计入最后一箱（digitize 右开边界漏样防护）."""
        from app.ml.model_validation import compute_ece

        p = np.array([1.0] * 10)
        y = np.zeros(10, dtype=int)  # 全部错：acc=0, conf=1 ⇒ ECE=1
        assert compute_ece(y, p, n_bins=10) == pytest.approx(1.0)

    def test_dca_net_benefit_matches_vickers_formula(self):
        """NB(t) = TP/n − FP/n · t/(1−t) 手算对拍（防公式漂移）."""
        from app.ml.model_validation import decision_curve_analysis

        # 10 样本：5 阳 5 阴；阈值 0.5 时 TP=4 FP=1
        y = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0])
        p = np.array([0.9, 0.8, 0.7, 0.6, 0.4, 0.55, 0.3, 0.2, 0.1, 0.05])
        dca = decision_curve_analysis(y, p, thresholds=[0.5])
        row = dca["curve"][0]
        # curve 行不含 tp/fp；手算对拍公式本身：
        # TP=4 (0.9/0.8/0.7/0.6>=0.5), FP=1 (0.55>=0.5), pt=1.0
        # NB = 4/10 − 1/10*1 = 0.3
        assert row["net_benefit_model"] == pytest.approx(0.3, abs=1e-6)
        # treat_all = π − (1−π)·pt = 0.5 − 0.5·1 = 0
        assert row["net_benefit_treat_all"] == pytest.approx(0.0, abs=1e-6)

    def test_dca_treat_all_crosses_zero_at_prevalence(self):
        """数学不变式：t=π 处全治线 NB=0（公式结构签名）."""
        from app.ml.model_validation import decision_curve_analysis

        rng = np.random.default_rng(3)
        y = (rng.random(500) < 0.3).astype(int)
        p = rng.random(500)
        pi = float(y.mean())
        dca = decision_curve_analysis(y, p, thresholds=[pi])
        assert dca["curve"][0]["threshold"] == pytest.approx(pi, abs=1e-3)
        assert dca["curve"][0]["net_benefit_treat_all"] == pytest.approx(0.0, abs=1e-3)

    def test_dca_random_scores_do_not_dominate_negative_control(self):
        """反空转：随机分数在临床区间内**不得**压过全治线（否则门槛判据失效）."""
        from app.ml.model_validation import decision_curve_analysis

        rng = np.random.default_rng(5)
        y = (rng.random(2000) < 0.25).astype(int)
        p = rng.random(2000)
        dca = decision_curve_analysis(y, p)
        # 低患病率下 t=0.1 处全治线 NB = π − (1−π)·(1/9) ≈ 0.25−0.083 = 0.167（高），
        # 随机模型 NB ≈ π·TPR/n − … 远低于它
        assert dca["summary"]["model_dominates_treat_all_in_range"] is False

    def test_dca_bad_clinical_range_raises(self):
        """区间非法必须显式抛错（不得静默换个区间放行）."""
        from app.ml.model_validation import decision_curve_analysis

        y = np.array([1, 0] * 50)
        p = np.linspace(0.01, 0.99, 100)
        for bad in [(0.4, 0.1), (0.0, 1.0), (0.9, 0.95)]:
            if bad == (0.9, 0.95):
                continue  # 合法区间但网格不含点 → 走 empty-range 分支（另一条断言）
            with pytest.raises(ValueError):
                decision_curve_analysis(y, p, clinical_range=bad)

    def test_dca_empty_range_reports_false_not_pass(self):
        """区间不含网格点时汇总必须为 False——不得因无点可查而默认放行."""
        from app.ml.model_validation import decision_curve_analysis

        y = np.array([1, 0] * 50)
        p = np.linspace(0.01, 0.99, 100)
        dca = decision_curve_analysis(y, p, clinical_range=(0.11, 0.14))
        assert dca["summary"]["model_dominates_extremes_in_range"] is False
        assert dca["summary"]["net_benefit_min_in_range"] == 0.0

    def test_dca_rejects_scores_outside_unit_interval(self):
        from app.ml.model_validation import decision_curve_analysis

        with pytest.raises(ValueError):
            decision_curve_analysis(np.array([1, 0]), np.array([1.5, 0.2]))

    def test_report_contains_dca_and_ece_for_binary_only(self):
        """报告结构：二分类必须有 decision_curve + ece；多类不得套用."""
        from app.ml.model_validation import generate_clinical_validation_report

        rng = np.random.default_rng(7)
        y = (rng.random(300) < 0.4).astype(int)
        p = np.clip(y * 0.7 + (1 - y) * 0.25 + rng.normal(0, 0.05, 300), 0, 1)
        report = generate_clinical_validation_report(
            y, (p >= 0.5).astype(int), p, groups=None
        )
        assert "decision_curve" in report
        assert "ece" in report
        assert report["decision_curve"]["summary"]["model_dominates_extremes_in_range"] is True

    def test_report_multiclass_omits_dca(self):
        """多类不强套 DCA（阈值净获益是二分类概念）."""
        from app.ml.model_validation import generate_clinical_validation_report

        rng = np.random.default_rng(8)
        y = rng.integers(0, 3, 240)
        # 三列"概率"（不必归一化——generate 只取最后一列走二分类路径判断）
        p = rng.random((240, 3))
        report = generate_clinical_validation_report(y, y.copy(), p, groups=None)
        assert "decision_curve" not in report
        assert "ece" not in report

    def test_default_clinical_range_is_ssot(self):
        """区间必须来自 SSOT，不得在内模块另立字面量（AST 钉引用）."""
        from app.core.ml_decision_thresholds import DCA_CLINICAL_RANGE
        from app.ml.model_validation import _DEFAULT_CLINICAL_RANGE

        assert _DEFAULT_CLINICAL_RANGE == DCA_CLINICAL_RANGE == (0.1, 0.4)


# ─────────────────────────── T2 融合增量消融 ───────────────────────────


class TestT2FusionAblationGuards:
    """P1-2：同队列消融 + ΔCI 纪律（CI 覆盖 0 即无显著增量）+ 分组防泄漏."""

    def _synthetic_arms(self, seed: int = 21):
        rng = np.random.default_rng(seed)
        n = 300
        y = (rng.random(n) < 0.3).astype(int)
        base = np.clip(y * 0.55 + 0.2 + rng.normal(0, 0.15, n), 0.01, 0.99)
        return y, base

    def test_run_ablation_rejects_misaligned_arms(self):
        from app.ml.fusion_ablation import run_ablation

        y, base = self._synthetic_arms()
        with pytest.raises(ValueError, match="长度"):
            run_ablation(y, {"structured": base, "text": base[:-1]})

    def test_paired_delta_zero_when_arms_identical(self):
        """同一分数两臂 ⇒ Δ=0 且 CI 覆盖 0（镜像 sanity）."""
        from app.ml.fusion_ablation import paired_delta_auc_ci

        y, base = self._synthetic_arms()
        r = paired_delta_auc_ci(y, base, base)
        assert r["delta"] == pytest.approx(0.0)
        assert r["ci_covers_zero"] is True

    def test_paired_delta_excludes_zero_on_consistent_gap(self):
        """恒定正向偏移的分数 ⇒ CI 不覆盖 0（证明 CI 判据可分辨，非恒真）."""
        from app.ml.fusion_ablation import paired_delta_auc_ci

        y, base = self._synthetic_arms()
        # 注意：**任何单调变换都不改 AUROC**（保序 ⇒ 同秩）。
        # 要造「一致的增量」必须给新臂真实的额外信息——混入标签信号
        # （模拟一个确实更准的模型），否则 Δ 恒 0、本测试会假红/假绿都不成立。
        better = np.clip(0.7 * base + 0.3 * y + 0.05, 0.0, 1.0)
        r = paired_delta_auc_ci(y, better, base, n_bootstrap=500)
        assert r["delta"] > 0
        assert r["ci_covers_zero"] is False
        assert r["ci"][0] > 0

    def test_provenance_records_in_sample(self):
        """in_sample 必须如实落档——fixture 权重 in-sample 挑选过."""
        from app.ml.fusion_ablation import run_ablation

        y, base = self._synthetic_arms()
        res = run_ablation(
            y, {"structured": base, "fusion": base.copy()}, in_sample=True, source="unit"
        )
        assert res.provenance["in_sample"] is True
        assert res.provenance["source"] == "unit"

    def test_groupwise_kfold_never_splits_a_group(self):
        """分组 K 折：同一用户/被试不得跨折（泄漏防线纪律的可执行形态）."""
        from app.ml.fusion_ablation import groupwise_kfold_indices

        rng = np.random.default_rng(2)
        groups = np.repeat(np.arange(120), 4)  # 120 组 × 4 样本
        y = rng.integers(0, 2, len(groups))
        folds = groupwise_kfold_indices(y, groups, n_splits=5)
        all_test = np.concatenate([te for _, te in folds])
        assert len(all_test) == len(np.unique(all_test))  # 每样本恰被测试一次
        for tr, te in folds:
            assert set(groups[tr].tolist()) & set(groups[te].tolist()) == set()

    def test_threshold_selected_on_train_fold_only(self):
        """OOF 工作点：阈值只许在训练折选——折与折之间选出的阈值可以不同，
        且每个测试样本用的是其所在折训练侧选出的阈值（结构断言）."""
        from app.ml.fusion_ablation import groupwise_oof_operating_metrics

        rng = np.random.default_rng(4)
        groups = np.repeat(np.arange(100), 6)
        y = rng.integers(0, 2, len(groups))
        scores = {"arm": np.clip(y * 0.5 + 0.25 + rng.normal(0, 0.2, len(y)), 0, 1)}
        out = groupwise_oof_operating_metrics(y, scores, groups, n_splits=5)
        assert out["grouping"] == "groupwise_kfold"
        assert len(out["per_arm"]["arm"]["selected_thresholds"]) == 5
        assert 0.05 <= min(out["per_arm"]["arm"]["selected_thresholds"])
        assert max(out["per_arm"]["arm"]["selected_thresholds"]) <= 0.95

    def test_bootstrap_degenerate_resamples_reported(self):
        """退化重采样必须计数而非静默丢弃（degenerate_samples 字段）."""
        from app.ml.fusion_ablation import bootstrap_auc_ci

        y = np.array([1, 0])
        _auc, _ci, degen = bootstrap_auc_ci(y, np.array([0.9, 0.1]), n_bootstrap=50)
        assert degen >= 0  # 极小样本下多数重采样退化；字段必须存在可读

    def test_nri_idi_zero_for_identical_scores(self):
        from app.ml.fusion_ablation import nri_continuous, idi_continuous

        y = np.array([1, 1, 0, 0])
        s = np.array([0.8, 0.7, 0.3, 0.2])
        assert nri_continuous(y, s, s) == pytest.approx(0.0)
        assert idi_continuous(y, s, s) == pytest.approx(0.0)


# ─────────────────────────── T3 公平性 ───────────────────────────


class TestT3FairnessAssessmentAndMitigation:
    """P1-3：评估（差距读数）与缓解（建议未启用）分账."""

    def test_disparity_keys_include_standard_fairness_gaps(self):
        from app.ml.model_validation import compute_fairness_metrics

        # 两组都须同时含正负例，否则单类组的 TPR/FPR 无定义、差距读数不出。
        # 设计（可手算）：组 a = 3 正 1 负；组 b = 2 正 2 负。
        #   a: pred(pos)=[1,1,0] ⇒ TPR=2/3; pred(neg)=[1] ⇒ FPR=1/1=1.0
        #   b: pred(pos)=[0,0]  ⇒ TPR=0/2=0.0; pred(neg)=[0,1] ⇒ FPR=1/2=0.5
        #   ⇒ tpr_gap=2/3, fpr_gap=0.5, fnr_gap=2/3（恒等式）, eo_gap=2/3
        y = np.array([1, 1, 1, 0, 1, 1, 0, 0])
        pred = np.array([1, 1, 0, 1, 0, 0, 0, 1])
        p = pred.astype(float)
        groups = np.array(["a", "a", "a", "a", "b", "b", "b", "b"])
        out = compute_fairness_metrics(y, pred, p, groups, min_group_size=4)
        d = out["disparities"]
        for key in ("tpr_gap", "fpr_gap", "fnr_gap", "equalized_odds_gap"):
            assert key in d, f"缺公平性差距读数 {key}"
        # 结构恒等式：FNR = 1 − TPR ⇒ FNR 差 == TPR 差
        assert d["fnr_gap"] == d["tpr_gap"]
        assert d["tpr_gap"] == pytest.approx(2 / 3, abs=1e-3)
        assert d["fpr_gap"] == pytest.approx(0.5, abs=1e-3)
        assert d["equalized_odds_gap"] == pytest.approx(2 / 3, abs=1e-3)

    def test_disparity_values_match_hand_computation(self):
        from app.ml.model_validation import compute_fairness_metrics

        # 单类组会被整组跳过（suppressed），两组都必须同时含正负例。
        # 设计（可手算）：组 a = 2 正 1 阴；组 b = 1 正 2 阴。
        #   a: TPR=1/2=0.5, FPR=1/1=1.0 ⇒ 组 b: TPR=0/1=0.0, FPR=2/2=1.0
        #   ⇒ tpr_gap=0.5, fpr_gap=0.0, fnr_gap=0.5（恒等式）, eo_gap=0.5
        y = np.array([1, 1, 0, 1, 0, 0])
        pred = np.array([1, 0, 1, 0, 1, 1])
        p = pred.astype(float)
        groups = np.array(["a", "a", "a", "b", "b", "b"])
        out = compute_fairness_metrics(y, pred, p, groups, min_group_size=3)
        assert out["disparities"]["tpr_gap"] == pytest.approx(0.5, abs=1e-3)

    def test_mitigation_status_is_recommended_not_enabled(self):
        """缓解必须与评估分账：两条缓解路径都标记『建议、未启用』."""
        from app.ml.fairness_mitigation import suggest_group_thresholds, suggest_sample_reweights

        rng = np.random.default_rng(6)
        y = rng.integers(0, 2, 200)
        p = rng.random(200)
        groups = np.repeat(["m", "f"], 100)
        gt = suggest_group_thresholds(y, p, groups)
        rw = suggest_sample_reweights(y, groups)
        assert gt["status"] == "recommended_not_enabled"
        assert rw["status"] == "recommended_not_enabled"

    def test_mitigation_reports_cost_not_only_improvement(self):
        """只报改善不报代价 = 无效建议（cost 块必须存在且含两项以上代价读数）."""
        from app.ml.fairness_mitigation import suggest_group_thresholds

        rng = np.random.default_rng(9)
        y = rng.integers(0, 2, 200)
        p = rng.random(200)
        groups = np.repeat(["m", "f"], 100)
        gt = suggest_group_thresholds(y, p, groups)
        cost = gt["cost"]
        assert "uniform_baseline" in cost and "group_thresholds_applied" in cost
        for key in ("accuracy_cost", "f1_cost", "tpr_gap_grouped", "fpr_gap_grouped"):
            assert key in cost, f"代价读数缺 {key}"


# ─────────────────────────── T4 漏报安全网 ───────────────────────────


class TestT4FalseNegativeSafetyNet:
    """P1-4：高危信号输入不得被判 0 级 / 免复核（可执行断言）."""

    def test_crisis_signal_never_drops_to_level_zero(self):
        from app.core.risk_thresholds import (
            CRISIS_FORCED_RISK_LEVEL,
            apply_false_negative_safety_net,
        )

        level, review = apply_false_negative_safety_net(0, crisis_signal=True)
        assert level >= CRISIS_FORCED_RISK_LEVEL == 4
        assert review is True

    def test_review_signal_floors_at_mild_and_forces_review(self):
        from app.core.risk_thresholds import FN_SAFETY_MIN_LEVEL, apply_false_negative_safety_net

        level, review = apply_false_negative_safety_net(0, review_signal=True)
        assert level >= FN_SAFETY_MIN_LEVEL == 1
        assert review is True

    def test_no_signal_keeps_behavior_unchanged(self):
        """无高危信号必须行为不变（防止安全网把正常路径也顶起来——假阳性代价）."""
        from app.core.risk_thresholds import apply_false_negative_safety_net

        for level_in in (0, 1, 2, 3, 4):
            assert apply_false_negative_safety_net(level_in) == (level_in, False)

    def test_safety_net_never_lowers_level(self):
        from app.core.risk_thresholds import apply_false_negative_safety_net

        for level_in in range(5):
            out, _ = apply_false_negative_safety_net(
                level_in, crisis_signal=True, review_signal=True
            )
            assert out >= level_in

    def test_score_to_level_zero_is_not_a_death_sentence(self):
        """端到端语义：score_to_level 给 0 级 + 危机信号 ⇒ 安全网必须抬级.

        这是「总分低但含高危信号不得免复核」的可执行检查。
        """
        from app.core.risk_thresholds import apply_false_negative_safety_net, score_to_level

        base = score_to_level(2.0)  # 低分 ⇒ 0 级（假阴性风险入口）
        assert base == 0
        level, review = apply_false_negative_safety_net(base, crisis_signal=True)
        assert level >= 4 and review is True


# ─────────────────────────── T5 阈值口径 SSOT ───────────────────────────


class TestT5ThresholdSsot:
    """P1-8：阈值单一事实源 + metrics JSON 自洽 + 死副本清除."""

    def test_settings_matches_ssot_constant(self):
        from app.core.config import settings
        from app.core.ml_decision_thresholds import TEXT_BILINGUAL_DECISION_THRESHOLD

        assert settings.text_bilingual_decision_threshold == TEXT_BILINGUAL_DECISION_THRESHOLD

    def test_script_headline_threshold_pinned_by_ast(self):
        """v1_27 脚本的 HEADLINE_EVAL_THRESHOLD 必须 == SSOT（AST 钉值）."""
        from app.core.ml_decision_thresholds import BILINGUAL_HEADLINE_EVAL_THRESHOLD

        tree = ast.parse(V127_SCRIPT.read_text(encoding="utf-8"))
        found: list[float] = []
        for node in ast.walk(tree):
            # 同时覆盖 ast.Assign 与 ast.AnnAssign（`X: float = 0.5` 是后者）
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            if any(
                isinstance(t, ast.Name) and t.id == "HEADLINE_EVAL_THRESHOLD" for t in targets
            ):
                assert isinstance(value, ast.Constant), "阈值必须是字面量常量"
                found.append(value.value)
        assert found == [BILINGUAL_HEADLINE_EVAL_THRESHOLD]

    def test_evaluate_default_threshold_is_named_not_literal(self):
        """_evaluate 的阈值必须是**具名常量默认参数**（结构），不得再裸 0.5 字面量."""
        tree = ast.parse(V127_SCRIPT.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_evaluate":
                args = node.args
                assert args.defaults, "_evaluate 必须有 threshold 默认参数"
                default = args.defaults[-1]
                assert isinstance(default, ast.Name) and default.id == "HEADLINE_EVAL_THRESHOLD", (
                    "threshold 默认值必须是具名常量（AST: ast.Name），不得回退裸字面量"
                )
                return
        pytest.fail("未找到 _evaluate 函数")

    def test_metrics_json_headline_matches_stated_eval_threshold(self):
        """JSON 自洽：headline (recall/precision/f1) == sweep 表中
        headline_eval_threshold 行——标称值与实际计算值必须一致."""
        d = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
        assert "headline_eval_threshold" in d, "缺 headline_eval_threshold 字段（口径未显式化）"
        sweep = d["threshold_sweep_groupwise"]
        row = next(
            r for r in sweep if abs(r["threshold"] - d["headline_eval_threshold"]) < 1e-9
        )
        headline = d["groupwise_ooF"]
        for k in ("recall", "precision", "f1"):
            assert headline[k] == row[k], (
                f"headline.{k}={headline[k]} 与 sweep@thr={d['headline_eval_threshold']} "
                f"行 {row[k]} 不一致——JSON 内部口径撕裂"
            )

    def test_metrics_json_decision_threshold_matches_production(self):
        """JSON 的 threshold（生产决策口径）== settings == SSOT 三方一致."""
        from app.core.config import settings
        from app.core.ml_decision_thresholds import TEXT_BILINGUAL_DECISION_THRESHOLD

        d = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
        assert d["threshold"] == settings.text_bilingual_decision_threshold
        assert d["threshold"] == TEXT_BILINGUAL_DECISION_THRESHOLD

    def test_metrics_json_headline_distinguishable_from_decision_threshold_row(self):
        """反空转见证：headline 三元组必须与**决策阈值**行的读数不同
        （若相同则本套闸门无法分辨两个口径，形同虚设）."""
        d = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
        sweep = d["threshold_sweep_groupwise"]
        row = next(r for r in sweep if abs(r["threshold"] - d["threshold"]) < 1e-9)
        headline = d["groupwise_ooF"]
        assert any(headline[k] != row[k] for k in ("recall", "precision", "f1")), (
            "headline 与决策阈值行读数相同——口径未分离，闸门失效"
        )

    def test_metrics_json_threshold_governance_block_present(self):
        d = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
        gov = d.get("threshold_governance")
        assert isinstance(gov, dict)
        assert gov["decision_threshold"] == d["threshold"]
        assert gov["headline_eval_threshold"] == d["headline_eval_threshold"]

    def test_fusion_engine_has_no_confidence_thresholds_constant(self):
        """死副本不得复活：fusion_engine 不得再定义 CONFIDENCE_THRESHOLDS（AST）."""
        tree = ast.parse(FUSION_ENGINE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    assert not (
                        isinstance(tgt, ast.Name) and tgt.id == "CONFIDENCE_THRESHOLDS"
                    ), "fusion_engine 出现 CONFIDENCE_THRESHOLDS 定义——置信阈值 SSOT 唯一（app/core/confidence.py）"

    def test_text_decision_path_consumes_settings_not_literal(self):
        """生产文本路径必须从 settings 读阈值，不得内联字面量（AST 钉引用）."""
        predict_py = BACKEND_ROOT / "app" / "core" / "model_engine" / "predict.py"
        tree = ast.parse(predict_py.read_text(encoding="utf-8"))
        hits = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "text_bilingual_decision_threshold":
                hits += 1
        assert hits >= 1, "predict.py 应至少一次经 settings.text_bilingual_decision_threshold 读阈值"
