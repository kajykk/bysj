"""Tests for training artifact registration + inference chain switching."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.core.model_registry import resolve_model_path
from app.core.model_registry_v2 import (
    ModelRegistryV2,
    ModelStatus,
    ModelType,
    activate_training_model,
    register_training_artifact,
)


class TestTrainingArtifactRegistry:
    """训练产物注册与推理链切换测试."""

    def setup_method(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.registry_path = self.temp_dir / "registry.json"
        self.registry = ModelRegistryV2(registry_path=str(self.registry_path))
        self._reg_patch = patch(
            "app.core.model_registry_v2.get_registry", return_value=self.registry
        )
        self._reg_patch.start()

    def teardown_method(self) -> None:
        self._reg_patch.stop()

    def test_register_training_artifact(self) -> None:
        """注册训练产物为 CANDIDATE."""
        artifact = self.temp_dir / "trained" / "run_1"
        artifact.mkdir(parents=True)
        record = register_training_artifact(
            model_id="run_1",
            artifact_path=str(artifact),
            version="v1",
            metrics={"f1": 0.82, "auc": 0.91},
            training_config={"epochs": 5, "learning_rate": 2e-5},
        )
        assert record.status == ModelStatus.CANDIDATE
        assert record.metrics["f1"] == 0.82
        assert record.training_config["epochs"] == 5

    def test_activate_training_model_to_production(self) -> None:
        """CANDIDATE -> STAGING -> PRODUCTION 逐级提升."""
        artifact = self.temp_dir / "trained" / "run_2"
        artifact.mkdir(parents=True)
        register_training_artifact(
            model_id="run_2",
            artifact_path=str(artifact),
            version="v1",
            metrics={"f1": 0.85},
        )
        record = activate_training_model("run_2")
        assert record is not None
        assert record.status == ModelStatus.PRODUCTION

    def test_activate_unknown_model_returns_none(self) -> None:
        """不存在的模型激活返回 None."""
        assert activate_training_model("no_such_model") is None

    def test_activate_already_production_is_idempotent(self) -> None:
        artifact = self.temp_dir / "trained" / "run_3"
        artifact.mkdir(parents=True)
        self.registry.register_model(
            model_id="run_3",
            name="run_3",
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.PRODUCTION,
            artifact_path=str(artifact),
        )
        record = activate_training_model("run_3")
        assert record is not None
        assert record.status == ModelStatus.PRODUCTION

    def test_resolve_model_path_switches_to_production_artifact(self) -> None:
        """PRODUCTION 产物存在时, 同名 model_id 解析到产物路径."""
        artifact = self.temp_dir / "trained" / "run_4"
        artifact.mkdir(parents=True)
        self.registry.register_model(
            model_id="run_4",
            name="run_4",
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.PRODUCTION,
            artifact_path=str(artifact),
        )
        resolved = resolve_model_path("run_4")
        assert str(Path(resolved).resolve()) == str(artifact.resolve())

    def test_resolve_model_path_ignores_candidate_artifact(self) -> None:
        """CANDIDATE 产物不切换推理路径 (回退静态注册表)."""
        artifact = self.temp_dir / "trained" / "run_5"
        artifact.mkdir(parents=True)
        self.registry.register_model(
            model_id="mmpsy_lite_model",
            name="mmpsy_lite_model",
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.CANDIDATE,
            artifact_path=str(artifact),
        )
        resolved = resolve_model_path("mmpsy_lite_model")
        assert "v1.25_mmpsy_lite" in resolved

    def test_resolve_model_path_fallback_when_artifact_missing(self) -> None:
        """PRODUCTION 记录但产物目录不存在时回退静态路径."""
        self.registry.register_model(
            model_id="mmpsy_lite_model",
            name="mmpsy_lite_model",
            version="v1",
            model_type=ModelType.LOGISTIC_REGRESSION,
            status=ModelStatus.PRODUCTION,
            artifact_path=str(self.temp_dir / "does_not_exist"),
        )
        resolved = resolve_model_path("mmpsy_lite_model")
        assert "v1.25_mmpsy_lite" in resolved


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
