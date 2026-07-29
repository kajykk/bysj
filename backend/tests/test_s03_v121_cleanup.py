"""S-03 (V4 ML 优化): v1.21 deprecated 模型清理验证测试。

验证要点:
1. MODEL_PATHS 和 MODEL_REGISTRY 中无 v1.21 条目
2. get_model_info() 对 v1.21 模型返回 None
3. validation_engine._VERSION_TO_MODEL_ID 不再包含 v1.21
4. 归档目录 models/_archive/structured_v1.21/ 存在
5. _run_experimental_v121 内部走 deprecated 分支返回 None 字段
6. 兼容性矩阵新增 v1.23 和 mmpsy_lite 条目
7. v1.20/v1.23/v1.25 等其他模型未受影响
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR
from app.core.model_compatibility import (
    MODEL_COMPATIBILITY_REGISTRY,
    get_model_compatibility_info,
)
from app.core.model_registry import MODEL_PATHS, MODEL_REGISTRY, get_model_info


V121_MODEL_IDS = [
    "structured_v1.21_binary_lr",
    "structured_v1.21_binary_rf",
    "structured_v1.21_multiclass_lr",
    "structured_v1.21_multiclass_rf",
    "structured_v1.21_scaler",
    "structured_v1.21_scaler_mc",
    "structured_v1.21_manifest",
]


class TestV121RegistryCleanup:
    """验证 v1.21 已从注册表中移除."""

    def test_v121_not_in_model_paths(self) -> None:
        """MODEL_PATHS 不应包含任何 v1.21 条目."""
        for v121_id in V121_MODEL_IDS:
            assert v121_id not in MODEL_PATHS, (
                f"{v121_id} 不应在 MODEL_PATHS 中 (S-03 已清理)"
            )

    def test_v121_not_in_model_registry(self) -> None:
        """MODEL_REGISTRY 不应包含任何 v1.21 模型条目."""
        for v121_id in V121_MODEL_IDS:
            assert v121_id not in MODEL_REGISTRY, (
                f"{v121_id} 不应在 MODEL_REGISTRY 中 (S-03 已清理)"
            )

    def test_get_model_info_returns_none_for_v121(self) -> None:
        """get_model_info() 对 v1.21 模型应返回 None."""
        for v121_id in V121_MODEL_IDS:
            assert get_model_info(v121_id) is None, (
                f"get_model_info({v121_id!r}) 应返回 None"
            )

    def test_registry_size_reduced(self) -> None:
        """注册表条目数应减少 7 个 (4 个模型 + 3 个辅助文件)."""
        # 清理前 33 个条目, 清理后 26 个
        assert len(MODEL_REGISTRY) == 26, (
            f"MODEL_REGISTRY 应有 26 个条目, 实际 {len(MODEL_REGISTRY)}"
        )
        assert len(MODEL_PATHS) == 26, (
            f"MODEL_PATHS 应有 26 个条目, 实际 {len(MODEL_PATHS)}"
        )


class TestV121Archived:
    """验证 v1.21 模型文件已归档."""

    def test_archive_directory_exists(self) -> None:
        """归档目录 models/_archive/structured_v1.21/ 应存在."""
        archive_dir = BACKEND_DIR / "models" / "_archive" / "structured_v1.21"
        assert archive_dir.exists(), f"归档目录不存在: {archive_dir}"
        assert archive_dir.is_dir(), f"路径不是目录: {archive_dir}"

    def test_archive_contains_v121_files(self) -> None:
        """归档目录应包含原 v1.21 模型文件."""
        archive_dir = BACKEND_DIR / "models" / "_archive" / "structured_v1.21"
        expected_files = [
            "model_binary_lr.pkl",
            "model_binary_rf.pkl",
            "model_multiclass_lr.pkl",
            "model_multiclass_rf.pkl",
            "scaler.pkl",
            "scaler_multiclass.pkl",
            "manifest.json",
        ]
        archived_files = [f.name for f in archive_dir.iterdir()]
        for expected in expected_files:
            assert expected in archived_files, (
                f"归档目录缺少文件: {expected} (实际: {archived_files})"
            )

    def test_original_v121_directory_removed(self) -> None:
        """原始 v1.21 模型目录应已移除."""
        original_dir = BACKEND_DIR / "models" / "artifacts" / "structured_v1.21"
        assert not original_dir.exists(), (
            f"原始 v1.21 目录应已移除: {original_dir}"
        )


class TestValidationEngineV121Removed:
    """验证 ValidationEngine._VERSION_TO_MODEL_ID 不再包含 v1.21."""

    def test_v121_not_in_version_map(self) -> None:
        """_VERSION_TO_MODEL_ID 不应包含 v1.21."""
        from app.services.validation_engine import ValidationEngine

        assert "v1.21" not in ValidationEngine._VERSION_TO_MODEL_ID, (
            "v1.21 不应在 _VERSION_TO_MODEL_ID 中 (S-03 已清理)"
        )

    def test_v123_and_v120_still_available(self) -> None:
        """v1.20 和 v1.23 应仍在映射中."""
        from app.services.validation_engine import ValidationEngine

        assert "v1.20" in ValidationEngine._VERSION_TO_MODEL_ID
        assert "v1.23" in ValidationEngine._VERSION_TO_MODEL_ID
        assert "v1.25" in ValidationEngine._VERSION_TO_MODEL_ID


class TestCompatibilityMatrixUpdated:
    """验证兼容性矩阵已更新 (新增 v1.23 和 mmpsy_lite, 不含 v1.21)."""

    def test_v121_not_in_compatibility_matrix(self) -> None:
        """兼容性矩阵不应包含 v1.21 条目."""
        for v121_id in V121_MODEL_IDS:
            assert v121_id not in MODEL_COMPATIBILITY_REGISTRY, (
                f"{v121_id} 不应在兼容性矩阵中"
            )

    def test_v123_compatibility_info_exists(self) -> None:
        """v1.23 应在兼容性矩阵中."""
        info = get_model_compatibility_info("structured_v1.23_external_lr")
        assert info is not None, "structured_v1.23_external_lr 兼容性信息缺失"
        assert info.format == "joblib"
        assert info.sklearn_version == "1.5.0"
        assert "pandas>=2.0.0" in info.required_dependencies

    def test_mmpsy_lite_compatibility_info_exists(self) -> None:
        """mmpsy_lite_model 应在兼容性矩阵中."""
        info = get_model_compatibility_info("mmpsy_lite_model")
        assert info is not None, "mmpsy_lite_model 兼容性信息缺失"
        assert info.format == "joblib"
        assert info.sklearn_version == "1.5.0"


class TestExperimentalV121PathReturnsNone:
    """验证 _run_experimental_v121 在 v1.21 已清理后返回 None 字段.

    清理前: get_model_info 返回 lifecycle=deprecated, 走 else 分支
    清理后: get_model_info 返回 None, 走 else 分支 (条件 `v1_21_info is not None` 失败)
    两种情况都返回 None 字段, 行为一致, 维持 PERF-P0-002 并行机制.
    """

    @pytest.mark.asyncio
    async def test_v121_path_returns_none_fields(self) -> None:
        """_run_experimental_v121 应返回 None 字段 (v1.21 已清理)."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = {}
        engine.model_load_stats = {}

        result = await engine._run_experimental_v121({}, 50.0)

        assert result["experimental_real_score"] is None
        assert result["experimental_real_level"] is None
        assert result["experimental_real_probability"] is None
        assert result["experimental_real_model"] is None


class TestOtherModelsUnaffected:
    """验证 v1.20/v1.23/v1.25 等其他模型未受 S-03 影响."""

    def test_v120_still_registered(self) -> None:
        """v1.20 模型应仍正常注册."""
        info = get_model_info("structured_logistic_regression_v1.20")
        assert info is not None
        assert info.lifecycle == "default"
        assert info.enabled is True

    def test_v123_still_registered(self) -> None:
        """v1.23 模型应仍正常注册 (S-02 升级为 default)."""
        info = get_model_info("structured_v1.23_external_lr")
        assert info is not None
        assert info.lifecycle == "default"
        assert info.enabled is True

    def test_v125_mmpsy_lite_still_registered(self) -> None:
        """v1.25 mmpsy_lite 模型应仍正常注册."""
        info = get_model_info("mmpsy_lite_model")
        assert info is not None
        assert info.lifecycle == "limited_active"
        assert info.enabled is True

    def test_physiological_v2_still_registered(self) -> None:
        """生理 v2 模型应仍正常注册 (S-01 升级为 default)."""
        info = get_model_info("physiological_model_v2_dl")
        assert info is not None
        assert info.lifecycle == "default"
        assert info.enabled is True
