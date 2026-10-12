"""AUDIT-2026-10-13 P1 批次回归闸门：#18 / #20 / #23 / #26。

每项都按「先实测、再断言」的纪律落地，并在 docstring 里记下改前实测读数，
便于后来者判断这条闸门到底在守什么（不是守「代码里写了某个字符串」）。

- #18 ``fuse()`` 非有限值：改前实测 NaN → 100.0/4（满级危机）、-Inf → 0.0/0
  （无风险）。闸门守「拒绝参与融合」，而不是守「别返回某个数」。
- #20 上传文件响应头：闸门守「nosniff + CSP 存在」**且**「不设 attachment」
  —— 后者把「内联渲染是有意支持的用法」这个决策固化下来，防止后人照审查
  报告原文改回去、把正念音频打成下载。
- #23 GDPR 流式导出：闸门守 7 个迭代器的 SQL 真的带 ORDER BY（抓真实
  statement 编译），不是守「源码里有 order_by」。
- #26 合成数据：闸门守「默认 fail-closed」，同时保留显式放行分支。
"""

from __future__ import annotations

import contextlib
import math
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from app.core.risk_thresholds import NonFiniteRiskScoreError
from app.ml.fusion_engine import FusionEngine
from app.services.experiment_data import ExperimentDataManager
from app.models.intervention import InterventionPlan
from app.services.gdpr_service_export import ExportMixin


# ── #18：融合输入非有限值 ────────────────────────────────────────────────


class TestFusionRejectsNonFiniteScores:
    """P1-18：NaN / ±Inf 不得被裁剪成极端临床结论。"""

    @pytest.mark.parametrize(
        "bad_value",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
        ],
        ids=["nan", "inf", "-inf"],
    )
    def test_fuse_rejects_non_finite_modality_score(self, bad_value: float):
        """改前实测：NaN/+Inf → risk_score 100.0 / level 4；-Inf → 0.0 / level 0。"""
        engine = FusionEngine()
        with pytest.raises(NonFiniteRiskScoreError):
            engine.fuse({"text": bad_value, "structured": 30.0})

    def test_fuse_rejects_bool_score(self):
        """bool 是 int 子类，必须显式拦（与 ensure_finite_score 同口径）。"""
        engine = FusionEngine()
        with pytest.raises(NonFiniteRiskScoreError):
            engine.fuse({"text": True, "structured": 30.0})

    def test_fuse_still_accepts_normal_and_out_of_range_scores(self):
        """合法输入与「越界但有限」的输入都不应被误伤（后者由裁剪 + warning 处理）。"""
        engine = FusionEngine()
        normal = engine.fuse({"text": 60.0, "structured": 40.0})
        assert 0.0 <= normal["risk_score"] <= 100.0

        out_of_range = engine.fuse({"text": 5000.0, "structured": 10.0})
        assert out_of_range["risk_score"] == 100.0
        assert out_of_range["risk_level"] == 4

    def test_clamp_mechanism_that_made_nan_silently_critical(self):
        """固化改前的失效机制：NaN 比较恒 False → min(100, nan) 保留 100。

        这条不是测业务代码，是给上面几条断言提供**为什么必须提前拦**的证据：
        说明下游裁剪与 ``_score_to_level`` 的 ensure_finite_score 都拦不住 NaN。
        """
        nan = float("nan")
        # 越界告警条件对 NaN 恒为 False → 不告警
        assert not (nan < 0.0 or nan > 100.0)
        # 裁剪把 NaN 变成 100.0（满级危机）
        assert max(0.0, min(100.0, nan)) == 100.0
        # 裁剪后已是有限值 → 下游 ensure_finite_score 永远拦不到
        assert math.isfinite(max(0.0, min(100.0, nan)))


# ── #20：上传文件响应头 ──────────────────────────────────────────────────


class TestUploadSecurityHeaders:
    """P1-20：nosniff + CSP；且刻意不设 attachment（内联渲染是有意支持的）。"""

    def test_secure_file_response_sets_nosniff_and_csp(self):
        from app.api.v1.uploads import _secure_file_response

        resp = _secure_file_response(Path(__file__))
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["content-security-policy"] == "default-src 'none'; sandbox"

    def test_secure_file_response_does_not_force_attachment(self):
        """偏离审查报告的**决策闸门**：强制 attachment 会打断 <audio>/<img>。

        依据见 ``app/api/v1/uploads.py`` 模块头 15-18 行：浏览器原生标签无法带
        Authorization header，端点因此支持 ``?token=`` 供内联加载使用。
        """
        from app.api.v1.uploads import _secure_file_response

        resp = _secure_file_response(Path(__file__))
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" not in disposition


# ── #23：GDPR 流式导出的稳定排序 ─────────────────────────────────────────


class _CapturingDB:
    """抓取 iter_* 真实下发的 statement，并返回空结果让分页循环立即结束。

    例外：``iter_intervention_tasks`` 会先查一次 ``InterventionPlan.id`` 拿
    plan_ids，空结果会让它直接 return、一次分页查询都不发。这里对**该前置
    查询**返回一个假 plan_id，保证能抓到真正的分页 statement。
    """

    def __init__(self) -> None:
        self.statements: list = []

    async def execute(self, stmt, *args, **kwargs):  # noqa: ANN002, ANN003
        self.statements.append(stmt)

        # 按「是否带分页」区分，而不是按实体类型区分：
        # ``iter_intervention_tasks`` 的前置查询（取 plan_ids）不带 LIMIT，
        # 需要返回非空才能进入真正的分页循环；所有分页查询都带 LIMIT，
        # 返回空让循环立即结束（否则会拿整数去喂 ``_plan_to_dict``）。
        rows: list = [] if "LIMIT" in str(stmt) else [1]

        class _Scalars:
            def all(self):  # noqa: ANN204
                return rows

        class _Result:
            def scalars(self):  # noqa: ANN204
                return _Scalars()

        return _Result()


class _ExportMixinHost(ExportMixin):
    """把 ExportMixin 单独挂出来，避开 GDPRService 的完整依赖。"""

    def __init__(self, db) -> None:  # noqa: ANN001
        self.db = db


@pytest.mark.asyncio
class TestGdprExportIteratorsHaveStableOrder:
    """P1-23：LIMIT/OFFSET 分页没有 ORDER BY 会漏行/重复（GDPR 合规实质缺陷）。"""

    ITERATORS = (
        "iter_emergency_contacts",
        "iter_counselor_bindings",
        "iter_risk_assessments",
        "iter_warnings",
        "iter_crisis_events",
        "iter_intervention_plans",
        "iter_intervention_tasks",
        "iter_operation_logs",
    )

    @pytest.mark.parametrize("method_name", ITERATORS)
    async def test_iterator_emits_order_by(self, method_name: str):
        db = _CapturingDB()
        host = _ExportMixinHost(db)
        method = getattr(host, method_name)

        async for _ in method(user_id=1, batch_size=200):  # noqa: B007
            pass

        assert db.statements, f"{method_name} 没有下发任何查询"

        # 只检查**真正带分页**的那些查询：``iter_intervention_tasks`` 会先发一条
        # 不带分页的前置查询（取 plan_ids），它本来就不需要 ORDER BY。
        paged = [str(s) for s in db.statements if "LIMIT" in str(s)]
        assert paged, f"{method_name} 没有下发带 LIMIT 的分页查询"

        for sql in paged:
            assert "ORDER BY" in sql, (
                f"{method_name} 的分页查询没有 ORDER BY —— OFFSET 翻页顺序不稳定，"
                f"GDPR 导出可能漏行或重复。实际 SQL: {sql}"
            )


# ── #26：禁止静默生成合成数据 ────────────────────────────────────────────


@contextlib.contextmanager
def _patched_roots(tmpdir: str):
    """把数据根目录整体重定向到临时目录，并在**整个用例期间**保持生效。

    ⚠️ 不要用「进 context → new manager → 出 context」的写法：patch 一退出，
    ``physiological_dataset_path()`` 就会解析回**真实的** ``DATA_ROOT``，
    于是断言的 ``not exists()`` 恒为真（假绿），而写文件的用例会把测试
    数据落进真实模型目录。
    """
    with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
        "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
    ):
        yield ExperimentDataManager()


class TestNoSilentSyntheticDataset:
    """P1-26：数据集缺失默认 fail-closed，不再静默造 240 行合成数据。"""

    def test_load_physiological_dataset_raises_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir, _patched_roots(
            tmpdir
        ) as manager:
            with pytest.raises(FileNotFoundError, match="拒绝静默生成合成数据"):
                manager.load_physiological_dataset("missing_phys")
            assert not manager.physiological_dataset_path("missing_phys").exists()

    def test_import_dataset_raises_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir, _patched_roots(
            tmpdir
        ) as manager:
            with pytest.raises(FileNotFoundError, match="拒绝静默生成合成数据"):
                manager.import_dataset("missing_ds", "csv", 0.7, 0.15, 0.15)
            assert not manager.dataset_path("missing_ds").exists()

    def test_explicit_allow_synthetic_still_works(self):
        """显式放行分支保留：演示/本地开发仍可造数，但会留 warning。"""
        with tempfile.TemporaryDirectory() as tmpdir, _patched_roots(
            tmpdir
        ) as manager:
            with patch("app.services.experiment_data.logger") as mock_logger:
                df = manager.load_physiological_dataset(
                    "demo_phys", allow_synthetic=True
                )
            assert not df.empty
            assert mock_logger.warning.called

    def test_existing_real_dataset_is_untouched(self):
        """真实数据集存在时行为不变（避免 fail-closed 误伤正常路径）。"""
        with tempfile.TemporaryDirectory() as tmpdir, _patched_roots(
            tmpdir
        ) as manager:
            csv_path = manager.physiological_dataset_path("real_phys")
            pd.DataFrame(
                {
                    "sleep_hours": [7.0, 6.5],
                    "sleep_quality": [3, 4],
                    "exercise_minutes": [30, 45],
                    "heart_rate": [70, 75],
                    "systolic_bp": [120, 130],
                    "diastolic_bp": [80, 85],
                    "steps": [5000, 8000],
                    "label": [0, 1],
                }
            ).to_csv(csv_path, index=False)
            df = manager.load_physiological_dataset("real_phys")
            assert len(df) == 2
