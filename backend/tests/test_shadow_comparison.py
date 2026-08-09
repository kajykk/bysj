"""Tests for training artifact shadow comparison (R1)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest

from app.core.model_registry_v2 import (
    ModelRegistryV2,
    ModelStatus,
    ModelType,
)
from app.services.shadow_comparison_service import ShadowComparisonService


class TestShadowComparisonStats:
    """影子对拍统计与激活守卫测试."""

    def setup_method(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        registry_path = self.temp_dir / "registry.json"
        self.registry = ModelRegistryV2(registry_path=str(registry_path))
        self._reg_patch = patch(
            "app.core.model_registry_v2.get_registry", return_value=self.registry
        )
        self._reg_patch.start()
        self.service = ShadowComparisonService()

    def teardown_method(self) -> None:
        self._reg_patch.stop()

    def _seed_candidate(self, model_id: str, artifact: Path | None = None) -> None:
        self.registry.register_model(
            model_id=model_id,
            name=model_id,
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.CANDIDATE,
            artifact_path=str(artifact) if artifact else "",
        )

    # ── 统计记录 ──

    def test_record_agreement_and_disagreement(self) -> None:
        self.service._record(
            "m1", {"prediction": 1, "probability": 0.8}, cand_pred=1, cand_prob=0.7
        )
        self.service._record(
            "m1", {"prediction": 0, "probability": 0.2}, cand_pred=1, cand_prob=0.6
        )
        stats = self.service.get_stats("m1")
        assert stats["total"] == 2
        assert stats["agreement"] == 1
        assert stats["disagreement"] == 1
        assert stats["agreement_rate"] == 0.5
        assert stats["max_prob_diff"] == 0.4  # max(0.1, 0.4)

    def test_insufficient_samples_allowed(self) -> None:
        """样本不足时不阻塞激活 (证据不足放行)."""
        self._seed_candidate("m2")
        self.service._record("m2", {"prediction": 1, "probability": 0.9}, 1, 0.9)
        ok, reason = self.service.is_shadow_acceptable("m2")
        assert ok is True
        assert "insufficient" in reason

    def test_low_agreement_rejected(self) -> None:
        """一致率低于阈值时拒绝激活."""
        import app.core.config as config_mod

        original = config_mod.settings.shadow_production_min_agreement
        config_mod.settings.shadow_production_min_agreement = 0.75
        try:
            self._seed_candidate("m1")
            # 20 样本, 一致率 0.5
            for i in range(20):
                self.service._record("m1", {"prediction": 1}, i % 2, None)
            ok, reason = self.service.is_shadow_acceptable("m1")
            assert ok is False
            assert "below threshold" in reason
        finally:
            config_mod.settings.shadow_production_min_agreement = original

    def test_high_agreement_allowed(self) -> None:
        self._seed_candidate("m1")
        for _ in range(25):
            self.service._record("m1", {"prediction": 1, "probability": 0.9}, 1, 0.9)
        ok, reason = self.service.is_shadow_acceptable("m1")
        assert ok is True
        assert reason == "shadow_ok"

    def test_force_override(self) -> None:
        import app.core.config as config_mod

        original = config_mod.settings.shadow_production_min_agreement
        config_mod.settings.shadow_production_min_agreement = 0.95
        try:
            self._seed_candidate("m1")
            for i in range(25):
                self.service._record("m1", {"prediction": 1}, i % 2, None)
            ok, reason = self.service.is_shadow_acceptable("m1", force=True)
            assert ok is True
            assert reason == "force_override"
        finally:
            config_mod.settings.shadow_production_min_agreement = original

    def test_commit_shadow_stats_writes_registry_metrics(self) -> None:
        self._seed_candidate("m1")
        self.service._record("m1", {"prediction": 1, "probability": 0.8}, 1, 0.8)
        self.service._record("m1", {"prediction": 1, "probability": 0.8}, 1, 0.8)
        self.service.commit_shadow_stats("m1")
        record = self.registry.get_model("m1")
        assert record is not None
        assert record.metrics["shadow_total"] == 2.0
        assert record.metrics["shadow_agreement_rate"] == 1.0

    def test_commit_shadow_stats_missing_model_returns_none(self) -> None:
        assert self.service.commit_shadow_stats("no_such") is None

    # ── fire_shadow_check 集成 ──

    def test_fire_shadow_skips_when_no_candidate(self) -> None:
        """无候选记录时静默跳过, 不抛异常."""
        self.service.fire_shadow_check("no_such", {"x": 1}, {"prediction": 1})
        assert self.service.get_stats("no_such")["total"] == 0

    def test_fire_shadow_skips_when_production_fallback(self) -> None:
        """生产使用 heuristic fallback 时不对拍."""
        self._seed_candidate("m2")
        self.service.fire_shadow_check(
            "m2", {}, {"prediction": 1, "model_used": "structured_heuristic_fallback"}
        )
        assert self.service.get_stats("m2")["total"] == 0

    @pytest.mark.asyncio
    async def test_shadow_check_runs_candidate_comparison(self) -> None:
        """候选为 CANDIDATE 且产物可加载时执行对拍."""
        import joblib
        import pandas as pd
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        artifact = self.temp_dir / "candidate"
        artifact.mkdir()
        pipe = Pipeline(
            [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=100))]
        )
        X = pd.DataFrame(
            {
                "f1": [0.0, 1.0, 0.5, 0.7] * 10,
                "f2": [1.0, 0.0, 0.4, 0.8] * 10,
            }
        )
        y = [0, 1, 0, 1] * 10
        pipe.fit(X, y)
        pkl_path = artifact / "physiological_model.pkl"
        joblib.dump(pipe, pkl_path)
        import hashlib

        (artifact / "physiological_model.pkl.sha256").write_text(
            hashlib.sha256(pkl_path.read_bytes()).hexdigest(), encoding="utf-8"
        )

        self._seed_candidate("cand1", artifact)

        await self.service._shadow_check(
            "cand1",
            {"f1": 0.6, "f2": 0.3},
            {"prediction": 1, "probability": 0.99},
        )
        stats = self.service.get_stats("cand1")
        assert stats["total"] == 1

    def test_reset_stats(self) -> None:
        self.service._record("m1", {"prediction": 1}, 1, None)
        self.service.reset_stats("m1")
        assert self.service.get_stats("m1")["total"] == 0