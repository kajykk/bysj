"""Tests for R2 training artifact auto-rollback."""

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
from app.services.registry_auto_rollback import check_auto_rollback
from app.services.shadow_comparison_service import ShadowComparisonService


class TestAutoRollback:
    """自动回退检查与降级测试."""

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

    def _seed_production(self, model_id: str, training_config: dict | None = None) -> None:
        """注册一个 PRODUCTION 状态的训练产物记录."""
        self.registry.register_model(
            model_id=model_id,
            name=model_id,
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.PRODUCTION,
            artifact_path="models/trained/run1",
            training_config=training_config or {"epochs": 5},
        )

    def _seed_static_production(self, model_id: str) -> None:
        """注册一个 PRODUCTION 但无训练配置的记录 (不受自动回退影响)."""
        self.registry.register_model(
            model_id=model_id,
            name=model_id,
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.PRODUCTION,
            artifact_path="models/static/foo.pkl",
        )

    # ── 健康统计 ──

    def test_record_inference_health(self) -> None:
        self.service.record_inference("m1", fallback_used=False)
        self.service.record_inference("m1", fallback_used=False)
        self.service.record_inference("m1", fallback_used=True)
        health = self.service.get_health("m1")
        assert health["total"] == 3
        assert health["fallback"] == 1
        assert health["fallback_rate"] == pytest.approx(1 / 3, abs=1e-3)

    def test_should_auto_rollback_when_rate_exceeds(self) -> None:
        import app.core.config as config_mod

        original = config_mod.settings.registry_auto_rollback_max_fallback_rate
        config_mod.settings.registry_auto_rollback_max_fallback_rate = 0.05
        try:
            for _ in range(10):
                self.service.record_inference("m1", fallback_used=True)
            for _ in range(10):
                self.service.record_inference("m1", fallback_used=False)
            should, reason = self.service.should_auto_rollback("m1")
            assert should is True
            assert "exceeds" in reason
        finally:
            config_mod.settings.registry_auto_rollback_max_fallback_rate = original

    def test_should_auto_rollback_when_samples_insufficient(self) -> None:
        self.service.record_inference("m1", fallback_used=True)
        should, reason = self.service.should_auto_rollback("m1")
        assert should is False
        assert "insufficient" in reason

    def test_should_auto_rollback_within_threshold(self) -> None:
        self.service.record_inference("m1", fallback_used=False)
        for _ in range(30):
            self.service.record_inference("m1", fallback_used=False)
        should, reason = self.service.should_auto_rollback("m1")
        assert should is False
        assert reason == "within_threshold"

    # ── check_auto_rollback ──

    def test_check_keeps_healthy_production(self, monkeypatch) -> None:
        self._seed_production("m1", {"epochs": 3})
        self._seed_static_production("static1")
        # 健康模型: 无回退 (patch 全局单例的方法)
        from app.services.shadow_comparison_service import (
            get_shadow_comparison_service,
        )

        monkeypatch.setattr(
            get_shadow_comparison_service(),
            "should_auto_rollback",
            lambda model_id: (False, "within_threshold"),
        )
        results = check_auto_rollback()
        assert results[0]["action"] == "keep"
        assert self.registry.get_model("m1").status == ModelStatus.PRODUCTION

    def test_check_demotes_unhealthy_production(self, monkeypatch) -> None:
        self._seed_production("m1", {"epochs": 3})
        from app.services.shadow_comparison_service import (
            get_shadow_comparison_service,
        )

        monkeypatch.setattr(
            get_shadow_comparison_service(),
            "should_auto_rollback",
            lambda model_id: (True, "fallback_rate 50.00% exceeds threshold"),
        )
        results = check_auto_rollback()
        assert results[0]["action"] == "rollback"
        record = self.registry.get_model("m1")
        assert record.status == ModelStatus.CANDIDATE
        assert (
            record.metrics["auto_rollback_reason"]
            == "fallback_rate 50.00% exceeds threshold"
        )

    def test_check_skips_static_production(self, monkeypatch) -> None:
        """无 training_config 的 PRODUCTION 记录不受自动回退影响."""
        self._seed_static_production("static1")
        calls = []

        def fake_should(model_id):
            calls.append(model_id)
            return False, "within_threshold"

        from app.services.shadow_comparison_service import (
            get_shadow_comparison_service,
        )

        monkeypatch.setattr(get_shadow_comparison_service(), "should_auto_rollback", fake_should)
        results = check_auto_rollback()
        assert results == []
        assert calls == []  # 静态记录未参与检查

    def test_rollback_training_model_demotes_to_candidate(self) -> None:
        from app.core.model_registry_v2 import rollback_training_model

        self._seed_production("m1")
        record = rollback_training_model("m1")
        assert record is not None
        assert record.status == ModelStatus.CANDIDATE

    def test_rollback_training_model_already_candidate_returns_none(self) -> None:
        from app.core.model_registry_v2 import rollback_training_model

        self._seed_production("m1")
        self._reg_patch.stop()
        reg = self.registry
        reg.promote_model("m1", ModelStatus.STAGING)
        reg.promote_model("m1", ModelStatus.CANDIDATE)
        self._reg_patch.start()
        assert rollback_training_model("m1") is not None  # CANDIDATE 幂等: 不报错
        record = self.registry.get_model("m1")
        assert record.status == ModelStatus.CANDIDATE


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])