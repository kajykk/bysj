"""P2-38 方向 B：项目级 ML 评估入口泄漏 / 选择偏差守卫。

背景（本轮实测，不是转引）：
  本仓 42 个文件、92 处 sklearn 划分/交叉验证入口。逐一实测后得到的关键结论是
  **「随机划分」本身不是普遍的泄漏源**——只有在数据存在兄弟/重复结构时才会虚高：

  | 数据 | 结构 | 划分口径 | F1 | AUC |
  |---|---|---|---|---|
  | chinese_depression_corpus_v1 | 8379 行 / 1275 组（增强变体） | random | 0.8860 | 0.9994 |
  | 同上 | 同上 | groupwise | 0.5749 | 0.8421 |
  | | | **Δ** | **+0.3111** | **+0.1573** |
  | mmpsy_structured_features | 1275 行 / 780 唯一（218 重复组，标签 100% 一致） | random | 0.8672 | 0.9996 |
  | 同上 | 同上 | groupwise | 0.8658 | 0.9996 |
  | | | **Δ** | **+0.0014** | **+0.0000** |

  后者 Δ≈0 的原因是**天花板效应**：该任务的 12 个结构化特征已近乎完美可分
  （AUC 0.9996），进一步查明 stress_level 是 phq9_score 的确定性线性变换
  （corr = 1.0，单特征 AUC = 1.0000）⇒ 这是**目标泄漏**，换任何 CV 都修不好。

因此本守卫钉死四件事：
  G1 探针有效性：合成语料上必须硬检出兄弟泄漏（正向证据，证明探针不是摆设）
  G2 目标泄漏可被检出：确定性派生特征必须被标 leaky
  G3 反弱化：纯噪声特征必须判 ok（防止 G2 退化成无脑报警）
  G4 清单覆盖棘轮：全仓扫描到的入口规模必须等于钉死基线，新增入口必须同步审计

不变量：本守卫**不改任何现役预测主路径**，也不改既有 ML 脚本口径，只做检测与记账。
"""
from __future__ import annotations

import importlib.util
import pathlib

import numpy as np
import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
TOOLS = pathlib.Path(__file__).resolve().parent / "tools"

# G4 棘轮基线：2026-10-19 实测（排除 tests/ 与 datasets/external/ 第三方副本）
#
# ⚠️ 基线口径以 **git 跟踪文件** 为准（扫描器 _iter_py_files 走 `git ls-files`）。
# 初版曾钉 42 文件 / 92 入口，那是 `rglob` 扫本机工作树的结果，其中包含
# 3 个未入库脚本（models/train_tabular_depression.py、
# models/train_text_depression_classifier.py、scripts/deep_analysis_fix.py）
# ⇒ CI 干净 checkout 只有 39 ⇒ 闸门在 CI 上必红（2026-10-19 实测）。
# 教训：断言必须钉交付形态下不变的事实，不是本机碰巧成立的状态。
BASELINE_FILES = 39
BASELINE_ENTRIES = 87

# 基线的文件级快照（用于失败时输出真实新增/移除差异，而不是把全量重列一遍）
BASELINE_FILE_SET: frozenset[str] = frozenset(
    {
        "backend/app/ml/hyperparameter_tuning.py",
        "backend/app/services/experiment_data.py",
        "backend/scripts/modeling/v1_23/01_prepare_external_dataset.py",
        "backend/scripts/modeling/v1_24/02_validate_mmpsy.py",
        "backend/scripts/modeling/v1_25/02_train_lite_model.py",
        "backend/scripts/modeling/v1_25/03_ablation_study.py",
        "backend/scripts/modeling/v1_26/00_reproduce_baseline.py",
        "backend/scripts/modeling/v1_26/01_threshold_sweep.py",
        "backend/scripts/modeling/v1_27/01_calibrate_lite_lr.py",
        "backend/scripts/modeling/v1_27/03_groupwise_leakage_free_eval.py",
        "backend/scripts/modeling/v1_27/04_retrain_bilingual_text_groupwise.py",
        "backend/scripts/modeling/verify_current_models.py",
        "scripts/data_prep/structured_feature_engineering.py",
        "scripts/deep_analysis.py",
        "scripts/eval_model.py",
        "scripts/evaluation/evaluate_model.py",
        "scripts/lib/fusion_pipeline.py",
        "scripts/m1_structured_gbdt.py",
        "scripts/m2_group_cv_eval.py",
        "scripts/m2_text_bert.py",
        "scripts/m2_text_bert_retrain.py",
        "scripts/m5_calibration_thresholds.py",
        "scripts/ml_training/data_utils.py",
        "scripts/ml_training/evaluate_models.py",
        "scripts/ml_training/train_bilingual_text.py",
        "scripts/ml_training/train_fusion.py",
        "scripts/ml_training/train_text.py",
        "scripts/multi_model_compare.py",
        "scripts/optimize_fusion_weights.py",
        "scripts/p2_bert_onnx_quantize.py",
        "scripts/p2_bert_quantization.py",
        "scripts/t1_bert_grid.py",
        "scripts/t1_group_cv_tool.py",
        "scripts/t1_sentence_embedding_eval.py",
        "scripts/train_and_eval.py",
        "scripts/train_physiological.py",
        "scripts/train_physiological_xgboost.py",
        "scripts/train_structured_fallback.py",
        "scripts/train_text_bert.py",
    }
)


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


@pytest.fixture(scope="module")
def probe():
    return _load("leakage_delta_probe", TOOLS / "leakage_delta_probe.py")


@pytest.fixture(scope="module")
def scanner():
    return _load("leakage_audit_scan", TOOLS / "leakage_audit_scan.py")


class TestG1ProbeEffectiveness:
    """G1：探针必须能在已知存在兄弟结构的数据上检出泄漏。"""

    def test_synthetic_sibling_leakage_detected(self, probe):
        texts, y, groups = probe._synthetic_corpus(n_groups=60, variants=6, seed=0)
        res = probe.compare_split_protocols(texts, y, groups)

        # 1) 必须是完整对照，不能退化成单臂
        assert res["random_only"] is False, "探针退化为单臂，组级口径未生效"
        assert res["groupwise"]["n_groups"] == 60, (
            f"组数不对：{res['groupwise']['n_groups']} != 60，分组逻辑被破坏"
        )

        # 2) random 口径必须显著高于 groupwise ⇒ ΔAUC 是硬指标（阈值无关）
        d_auc = res["delta"]["d_roc_auc"]
        assert d_auc is not None and d_auc >= 0.20, (
            f"探针未检出兄弟泄漏：ΔAUC={d_auc} < 0.20"
        )

        # 3) 组级口径下判别力必须崩塌（合成语料标签只绑定组身份）
        g_auc = res["groupwise"]["roc_auc"]
        assert g_auc <= 0.65, (
            f"组级口径未崩塌：AUC={g_auc} > 0.65，说明兄弟未被真正隔离"
        )

    def test_groupwise_never_exceeds_random(self, probe):
        """口径单调性：组级不可能比随机更乐观（否则说明分组没生效）。"""
        texts, y, groups = probe._synthetic_corpus(n_groups=40, variants=5, seed=7)
        res = probe.compare_split_protocols(texts, y, groups)
        assert res["random"]["roc_auc"] >= res["groupwise"]["roc_auc"] - 1e-9, (
            "组级 AUC 反而高于随机口径 ⇒ 分组未被应用"
        )


class TestG2TargetLeakageDetection:
    """G2/G3：目标泄漏检测器的双向验证。"""

    def test_deterministic_derived_feature_flagged(self, probe):
        """stress_level = phq9/27*5 这类确定性派生必须被标 leaky。"""
        rng = np.random.default_rng(11)
        n = 400
        phq9 = rng.integers(0, 28, size=n)
        y = (phq9 >= 10).astype(int)
        df = pd.DataFrame(
            {
                "phq9_score": phq9.astype(float),
                "stress_level": np.round(phq9 / 27.0 * 5.0, 4),
                "age": rng.normal(22, 3, size=n),
                "noise": rng.normal(size=n),
            }
        )
        df["y"] = y
        res = probe.detect_target_leakage(
            df, ["phq9_score", "stress_level", "age", "noise"], "y"
        )
        flagged = {r["feature"] for r in res["leaky"]}
        assert "stress_level" in flagged, f"确定性派生特征未被检出：{flagged}"
        assert "phq9_score" in flagged, f"标签原值本身未被检出：{flagged}"

    def test_reverse_signed_feature_flagged(self, probe):
        """反向单调特征（如 -phq9）也必须被检出。

        存在意义：这一条是**盲区兜底**。若没有它，把检测器里的
        `max(auc, 1-auc)` 折叠去掉（只判正向）将完全不红 ⇒
        反向泄漏会静默溜过闸门。变异脚本 M3 专门用于验证这条覆盖是活的。
        """
        rng = np.random.default_rng(17)
        n = 400
        phq9 = rng.integers(0, 28, size=n)
        y = (phq9 >= 10).astype(int)
        df = pd.DataFrame(
            {
                # 反向单调：值越大越不抑郁
                "reverse_stress": -(phq9 / 27.0 * 5.0),
                "noise": rng.normal(size=n),
            }
        )
        df["y"] = y
        res = probe.detect_target_leakage(df, ["reverse_stress", "noise"], "y")
        flagged = {r["feature"] for r in res["leaky"]}
        assert "reverse_stress" in flagged, (
            f"反向单调特征未被检出 ⇒ 存在反向泄漏盲区：{res}"
        )

    def test_pure_noise_passes(self, probe):
        """G3 反弱化：纯噪声特征必须判 ok，否则检测器是无脑报警。"""
        rng = np.random.default_rng(13)
        n = 400
        y = rng.integers(0, 2, size=n)
        df = pd.DataFrame(
            {f"noise_{i}": rng.normal(size=n) for i in range(6)}
        )
        df["y"] = y
        res = probe.detect_target_leakage(df, [f"noise_{i}" for i in range(6)], "y")
        assert res["verdict"] == "ok", (
            f"检测器对纯噪声也报警 ⇒ 无脑报警，闸门失效：{res}"
        )
        assert res["n_leaky"] == 0

    def test_real_mmpsy_stress_is_leaky(self, probe):
        """真实数据锚定：mmpsy 的 stress_level 必须被检出为泄漏。

        这条把「发现」钉成不变量：若将来有人修好或改用其它特征，
        闸门会红 ⇒ 强制重新审计而不是静默放过。
        """
        feat_path = REPO / "data" / "processed" / "mmpsy_structured_features.csv"
        raw_path = REPO / "data" / "external" / "mmpsy_scores.csv"
        if not feat_path.exists() or not raw_path.exists():
            pytest.skip("mmpsy 数据不在库内（运行时产物）")

        df = pd.read_csv(feat_path)
        raw = pd.read_csv(raw_path)
        cols = [c for c in df.columns if not c.endswith("_source")]
        df = df.copy()
        df["y"] = raw["phq9_binary"].astype(int).values

        res = probe.detect_target_leakage(df, cols, "y")
        flagged = {r["feature"] for r in res["leaky"]}
        assert "stress_level" in flagged, (
            f"真实 mmpsy 数据上 stress_level 未被检出：{res}"
        )


class TestG4InventoryCoverageRatchet:
    """G4：清单覆盖棘轮——新增划分入口必须同步进审计清单。"""

    def test_scanner_sees_full_inventory(self, scanner):
        findings: list[dict] = []
        for p in scanner._iter_py_files():
            findings += scanner.scan_file(p)
        findings = [f for f in findings if not f["in_test"]]

        files = {f["file"] for f in findings}
        if len(files) != BASELINE_FILES:
            # 输出真实差异，而不是把全部文件列一遍（初版的 files - set() 是空集，毫无诊断价值）
            added = sorted(files - BASELINE_FILE_SET)
            removed = sorted(BASELINE_FILE_SET - files)
            raise AssertionError(
                f"ML 划分入口涉及文件数 {len(files)} != 基线 {BASELINE_FILES}。"
                f"新增: {added}；移除: {removed} —— "
                "必须同步 docs/ML_LEAKAGE_AUDIT.md 并更新 BASELINE_FILES"
            )
        assert len(findings) == BASELINE_ENTRIES, (
            f"ML 划分入口总数 {len(findings)} != 基线 {BASELINE_ENTRIES}；"
            "新增/删除入口必须同步审计清单"
        )

    def test_scanner_sources_from_git_tracked_files(self):
        """扫描器必须以 `git ls-files` 为事实源，不得用 rglob 扫工作树。

        存在意义：初版用 `rglob` 扫工作树，把本机 3 个未入库 .py 混入候选
        （42 文件），而 CI 干净 checkout 只有 39 ⇒ 清单棘轮在 CI 上必红。
        本条把「只扫交付形态」钉成源码级不变量（AST 断言，非文本匹配）。
        变异 M5 专门用于验证这条覆盖是活的。
        """
        import ast

        src = (TOOLS / "leakage_audit_scan.py").read_text(encoding="utf-8")
        tree = ast.parse(src)

        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_iter_py_files":
                target = node
                break
        assert target is not None, "_iter_py_files 函数不存在"

        constants = {
            n.value
            for n in ast.walk(target)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        assert "ls-files" in constants, (
            f"_iter_py_files 未调用 git ls-files；当前字符串常量: {sorted(constants)}"
        )
        rglob_calls = [
            n.attr
            for n in ast.walk(target)
            if isinstance(n, ast.Attribute) and n.attr == "rglob"
        ]
        assert rglob_calls == [], (
            f"_iter_py_files 仍在使用 rglob（会把未入库文件混入 ⇒ CI 必红）: {rglob_calls}"
        )

    def test_every_entry_has_a_risk_label(self, scanner):
        """每条入口必须落在某个已知风险类里，不容许未分类盲区。"""
        known = {
            "ok",
            "group_aware_without_groups",
            "random_split_no_groups",
            "threshold_picking",
        }
        findings: list[dict] = []
        for p in scanner._iter_py_files():
            findings += scanner.scan_file(p)
        findings = [f for f in findings if not f["in_test"]]
        unknown = {f["risk"] for f in findings} - known
        assert unknown == set(), f"存在未分类风险标签：{unknown}"
