"""
ROUND_29 (T3)：scaler 一致性闸门——永久防 D-R26-1（P0）复发。

背景（D-R26-1）
--------------
artifact `scaler.json` 曾与仓内任何数据版本都不匹配（sleep_quality 均值
5.4279 超出 1-5 量表；overall_activity 错配约 5 倍）⇒ 生产路径 test recall
仅 0.6000（每 10 个阳性漏约 4 个）。ROUND_29 按 T1 判定走**路径 B 端到端
重训**（`scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py）：
cleaner/scaler 只在 train 719 行上拟合、模型经该 scaler 训练
（co-consistent by construction）。

为什么是「可复现性主闸门 + 域合理性 + 结构层」而不是一层
--------------------------------------------------------
域合理性检查**单独不够**：overall_activity 错配 5 倍（均值 460098）仍落在
合法域 [0, 1.44e8] 内——域检抓不到它（这正是 D-R26-1 藏身的原因）。
因此三层各有分工：

- **第一层（主闸门 · 可复现性）**：同切分（`split_indices`, seed=42）、
  同管线（生产 cleaner + `engineer_features`）在 train 719 行上重拟合
  `SimpleStandardScaler`，断言部署 `scaler.json` 逐特征
  `allclose(rtol=1e-3, atol=1e-4)`。它直接钉死「部署 scaler 就是当前训练
  切分拟合的那个」——换数据版本重训、手工编辑 scaler、回退错配工件，
  任何 D-R26-1 式复发都在此变红。
- **第二层（域合理性）**：13 特征硬合法域表（物理界 / 公式 clip / 量表界，
  每条附来源，见 FEATURE_DOMAINS）+ scale>0。数学依据：有界随机变量的
  std ≤ (b−a)/2（Popoviciu）⇒ scale ∈ (0, (high−low)/2]。专抓
  sleep_quality 5.4279 这类连合法域都编不圆的参数。
- **结构层**：len==13、顺序对 `feature_names.json`、`n_features_in`==13。

CI 边界（诚实记账）
------------------
artifact（`models/artifacts/physiological_optimized/*.json`）与数据集
（`datasets/.../depresjon_physiological.csv`）都**不在版本库**（ROUND_26
确立的分层：CI 只能复算到 csv/json 层）。因此：
- 工件缺失 ⇒ 整个模块按 data-machine-only gate 显式 skip（reason 注明，不静默）；
- 工件在、数据集不在 ⇒ 只跳第一层；第二/结构层照常跑（只读工件本身）。
- 第一层在数据机器的实测 max diff 记录在
  `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md`。

变异见证：`backend/tests/tools/mutate_p2_56_round29.py`
（overall_activity 均值→460098 第一层红；sleep_quality 均值→5.428 /
scale→2.5924 第二层红；结构与存档回退臂；末臂 GREEN）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
ARTIFACTS_DIR = BACKEND / "models" / "artifacts" / "physiological_optimized"
SCALER_JSON = ARTIFACTS_DIR / "scaler.json"
FEATURE_NAMES_JSON = ARTIFACTS_DIR / "feature_names.json"
MODEL_JSON = ARTIFACTS_DIR / "model.json"
BROKEN_ARCHIVE = ARTIFACTS_DIR / "scaler.json.broken_round29"
EVAL01 = BACKEND / "scripts" / "modeling" / "eval" / "v1_29" / "01_reproducible_eval.py"
# 数据集在仓库根（app/ml/data_loader.py 的 _PROJECT_ROOT 口径），且被 .gitignore 整体忽略
DEPRESJON_CSV = (
    REPO / "datasets" / "physiological" / "external" / "depresjon_processed"
    / "depresjon_physiological.csv"
)

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.scaler import SimpleStandardScaler  # noqa: E402
from app.utils.checksum import _compute_sha256  # noqa: E402

# 13 特征硬合法域表（feature_names.json 的顺序）。
# 每条界的来源只能是三类：物理界 / 公式 clip / 量表界——**不拟合数据**
# （拟合出来的界是循环论证：它会把错配的数据版本也判合法）。
# 派生公式见 app/ml/feature_engineering.py（compute_* 六个函数）。
FEATURE_DOMAINS: dict[str, tuple[float, float, str]] = {
    # 原始特征：物理/生理界
    "sleep_hours": (0.0, 24.0, "物理界：一天的小时数"),
    "sleep_quality": (1.0, 5.0, "1-5 Likert 量表界（D-R26-1 的 5.4279 越界即由此抓）"),
    "exercise_minutes": (0.0, 1440.0, "物理界：一天最多 1440 分钟"),
    "heart_rate": (30.0, 220.0, "生理界：静息~极量运动心率 bpm"),
    "systolic_bp": (60.0, 260.0, "生理界：收缩压 mmHg"),
    "diastolic_bp": (30.0, 160.0, "生理界：舒张压 mmHg"),
    "steps": (0.0, 100000.0, "物理界：日步数（10 万步/天已远超可穿戴研究合理值）"),
    # 派生特征：公式 clip 界（engineer_features 里显式 clip 到的区间）
    "sleep_efficiency": (0.0, 10.0, "公式 clip：quality/(hours+1e-6) → [0,10]"),
    "activity_intensity": (0.0, 10000.0, "公式 clip：steps/exercise_minutes → [0,10000]"),
    "cardiovascular_risk": (0.5, 3.0, "公式 clip：systolic/(diastolic+1e-6) → [0.5,3]"),
    # 派生特征：公式无 clip，按输入物理界推导
    "hr_sleep_interaction": (
        -420.0, 2200.0,
        "公式：heart_rate x (10 - sleep_hours) 无 clip；按输入界 hr∈[30,220]、"
        "hours∈[0,24] 推得 [30x(10-24), 220x10]",
    ),
    # 派生特征：公式无 clip；域内错配 5 倍（460098）仍合法 ⇒ 域检盲区，
    # 由第一层可复现性闸门兜底（steps≤1e5 x exercise≤1440 = 1.44e8）
    "overall_activity": (0.0, 1.44e8, "公式：steps x exercise_minutes 无 clip；输入界乘积"),
    "bp_category": (0.0, 2.0, "JNC7 三档分类：0/1/2"),
}

# data-machine-only gate：CI 干净 checkout 无 artifacts ⇒ 整模块 skip。
# 这是**明确的降级声明**（不是「CI 已覆盖」），机器见证即本 pytestmark 的 reason。
pytestmark = pytest.mark.skipif(
    not (MODEL_JSON.exists() and SCALER_JSON.exists() and FEATURE_NAMES_JSON.exists()),
    reason=(
        "data-machine-only gate：生理模型 artifacts 不在版本库"
        "（CI 干净 checkout 整模块 skip；见 docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md）"
    ),
)


def _load_eval01():
    """把评估壳 01 当模块导入（main 有 __main__ 保护，无副作用）。"""
    spec = importlib.util.spec_from_file_location("eval01_p2_56", EVAL01)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_scaler_json() -> dict:
    return json.loads(SCALER_JSON.read_text(encoding="utf-8"))


def _read_feature_names() -> list[str]:
    names = json.loads(FEATURE_NAMES_JSON.read_text(encoding="utf-8"))
    assert isinstance(names, list) and all(isinstance(n, str) for n in names)
    return names


class TestScalerStructure:
    """结构层：13 维、顺序、域表覆盖。"""

    def test_feature_count_and_order(self) -> None:
        data = _read_scaler_json()
        feats = _read_feature_names()
        assert len(data["mean"]) == 13, f"mean 长度 {len(data['mean'])} != 13"
        assert len(data["scale"]) == 13, f"scale 长度 {len(data['scale'])} != 13"
        assert data["n_features_in"] == 13, f"n_features_in={data['n_features_in']} != 13"
        assert len(feats) == 13, f"feature_names 长度 {len(feats)} != 13"
        # 域表必须覆盖且顺序一致——顺序漂移会让 mean/scale 对错特征
        assert list(FEATURE_DOMAINS) == feats, (
            "FEATURE_DOMAINS 与 feature_names.json 顺序不一致：\n"
            f"  域表   : {list(FEATURE_DOMAINS)}\n  feature: {feats}"
        )


class TestScalerDomainSanity:
    """第二层：硬合法域 + scale 正性 + Popoviciu 上界。"""

    def test_domains_and_positive_scale(self) -> None:
        data = _read_scaler_json()
        feats = _read_feature_names()
        violations: list[str] = []
        for i, name in enumerate(feats):
            low, high, _src = FEATURE_DOMAINS[name]
            mean = float(data["mean"][i])
            scale = float(data["scale"][i])
            if not np.isfinite(mean) or not np.isfinite(scale):
                violations.append(f"{name}: mean={mean} scale={scale} 含非有限值")
                continue
            if not (low <= mean <= high):
                violations.append(f"{name}: mean={mean:.6f} 越界 [{low}, {high}]")
            if not (scale > 0):
                violations.append(f"{name}: scale={scale} 非正")
            elif scale > (high - low) / 2:
                violations.append(
                    f"{name}: scale={scale:.6f} 超过 Popoviciu 上界 "
                    f"(high-low)/2={(high - low) / 2:.6f}——有界变量不可能有这么大标准差"
                )
        assert not violations, "部署 scaler 违反域合法性：\n" + "\n".join(violations)


class TestScalerReproducesTrainFit:
    """第一层（主闸门）：部署 scaler == 同切分同管线的 train-only 重拟合。"""

    @pytest.mark.skipif(
        not DEPRESJON_CSV.exists(),
        reason="数据集不在版本库（.gitignore）；第一层只在数据机器跑（ROUND_26 分层）",
    )
    def test_deployed_scaler_equals_train_only_refit(self) -> None:
        from app.ml.data_loader import load_depresjon_data
        from app.ml.model_loader import load_cleaner, load_feature_names

        e01 = _load_eval01()

        df = load_depresjon_data()
        y = df["depression_label"].values.astype(np.int64)
        tri, vai, tei = e01.split_indices(y)
        assert (len(tri), len(vai), len(tei)) == (719, 153, 157), (
            f"切分尺寸异常：{len(tri)}/{len(vai)}/{len(tei)}"
        )
        assert not set(int(i) for i in tri) & set(int(i) for i in tei), "train/test 有交集"

        cleaner = load_cleaner()
        feats = load_feature_names()
        assert len(feats) == 13

        # train-only 重拟合（与 04 重训脚本同一口径：同一 cleaner、同一特征管线）
        X_train = e01.build_features(df, tri, cleaner, feats)
        refit = SimpleStandardScaler().fit(X_train)

        deployed = SimpleStandardScaler.from_dict(_read_scaler_json())
        assert deployed.n_features_in_ == 13

        diff_mean = np.abs(deployed.mean_ - refit.mean_)
        diff_scale = np.abs(deployed.scale_ - refit.scale_)
        max_mean = float(diff_mean.max())
        max_scale = float(diff_scale.max())
        assert np.allclose(deployed.mean_, refit.mean_, rtol=1e-3, atol=1e-4), (
            "部署 scaler 的 mean 与 train-only 重拟合不一致（D-R26-1 复发）——"
            f"max|diff|={max_mean:.3e}；逐特征：\n"
            + "\n".join(
                f"  {n}: deployed={deployed.mean_[i]:.6f} refit={refit.mean_[i]:.6f}"
                for i, n in enumerate(feats)
                if diff_mean[i] > 1e-4
            )
        )
        assert np.allclose(deployed.scale_, refit.scale_, rtol=1e-3, atol=1e-4), (
            "部署 scaler 的 scale 与 train-only 重拟合不一致（D-R26-1 复发）——"
            f"max|diff|={max_scale:.3e}；逐特征：\n"
            + "\n".join(
                f"  {n}: deployed={deployed.scale_[i]:.6f} refit={refit.scale_[i]:.6f}"
                for i, n in enumerate(feats)
                if diff_scale[i] > 1e-4
            )
        )
        print(
            f"[p2_56 第一层] 部署 scaler == train-only 重拟合："
            f"max|mean diff|={max_mean:.3e}, max|scale diff|={max_scale:.3e}"
        )


class TestScalerIntegrity:
    """侧车完整性：scaler.json 与其 .sha256 相符（防「改内容不改校验」之外的缺失/陈旧）。"""

    def test_sidecar_matches_file(self) -> None:
        sidecar = SCALER_JSON.with_suffix(SCALER_JSON.suffix + ".sha256")
        assert sidecar.exists(), f"缺少侧车 {sidecar.name}（load_scaler 的 require_checksum 会拒绝加载）"
        recorded = sidecar.read_text(encoding="utf-8").strip().split()[0]
        actual = _compute_sha256(SCALER_JSON)
        assert recorded == actual, (
            f"侧车与文件不符：{recorded[:16]}... vs {actual[:16]}...——"
            "scaler.json 被改动后未更新校验"
        )


class TestFixIsInPlace:
    """修复确已落地：部署 scaler 不是修复前存档的那个。"""

    @pytest.mark.skipif(
        not BROKEN_ARCHIVE.exists(),
        reason="无修复前存档（非数据机器，或存档已被清理）",
    )
    def test_deployed_scaler_is_not_broken_archive(self) -> None:
        broken = json.loads(BROKEN_ARCHIVE.read_text(encoding="utf-8"))
        deployed = _read_scaler_json()
        assert deployed["mean"] != broken["mean"] or deployed["scale"] != broken["scale"], (
            "部署 scaler 与修复前存档 scaler.json.broken_round29 完全相同——"
            "修复未落地，或错把坏工件放回了生产目录"
        )
