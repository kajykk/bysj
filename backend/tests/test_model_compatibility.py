from __future__ import annotations

import hashlib
import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.model_compatibility import (
    TARGET_SKLEARN_VERSION,
    check_sklearn_version,
    load_model_with_compatibility_check,
    verify_model_compatibility,
)


def _write_sha256_checksum(model_path: Path) -> None:
    """为测试模型文件生成 .sha256 校验文件 (ISS-007 兼容性修复).

    safe_joblib_load 在 require_hash=True 时要求 expected_hash 或 .sha256
    校验文件，否则抛出 ValueError。本辅助函数计算模型文件 SHA256 并写入
    旁路校验文件，模拟生产环境部署产物。
    """
    sha = hashlib.sha256(model_path.read_bytes())
    checksum_path = model_path.with_suffix(model_path.suffix + ".sha256")
    checksum_path.write_text(sha.hexdigest(), encoding="utf-8")


class TestModelCompatibility:
    """T-INFRA-005: sklearn 版本兼容性单元测试"""

    def test_check_sklearn_version_match(self) -> None:
        """验证 sklearn 版本匹配时返回 True"""
        with patch("sklearn.__version__", TARGET_SKLEARN_VERSION):
            is_compat, message = check_sklearn_version()
            assert is_compat is True
            assert TARGET_SKLEARN_VERSION in message

    def test_check_sklearn_version_mismatch(self) -> None:
        """验证 sklearn 版本不匹配时返回 False"""
        with patch("sklearn.__version__", "1.2.0"):
            is_compat, message = check_sklearn_version()
            assert is_compat is False
            assert "mismatch" in message
            assert "1.2.0" in message
            assert TARGET_SKLEARN_VERSION in message

    def test_check_sklearn_version_not_installed(self) -> None:
        """验证 sklearn 未安装时返回 False"""
        with patch.dict(sys.modules, {"sklearn": None}):
            is_compat, message = check_sklearn_version()
            assert is_compat is False
            assert "not installed" in message

    def test_verify_model_compatibility_success(self) -> None:
        """验证模型兼容性检查通过"""
        mock_model = MagicMock()
        mock_model.named_steps = {}

        with patch("sklearn.__version__", TARGET_SKLEARN_VERSION):
            is_compat, message = verify_model_compatibility(mock_model)
            assert is_compat is True
            assert "verified" in message

    def test_verify_model_compatibility_version_mismatch(self) -> None:
        """验证模型兼容性检查失败时返回警告"""
        mock_model = MagicMock()
        mock_model.named_steps = {}

        with patch("sklearn.__version__", "1.2.0"):
            is_compat, message = verify_model_compatibility(mock_model)
            assert is_compat is False
            assert "mismatch" in message

    def test_load_model_with_compatibility_check_success(self, tmp_path: Path) -> None:
        """验证兼容性检查通过时正常加载模型"""
        model_path = tmp_path / "test_model.pkl"
        mock_model = {"test": "model"}

        import joblib

        joblib.dump(mock_model, model_path)
        # ISS-007 修复后 load_model_with_compatibility_check 强制 require_hash=True，
        # 需提供 .sha256 校验文件以满足 safe_joblib_load 的完整性校验。
        _write_sha256_checksum(model_path)

        with patch("sklearn.__version__", TARGET_SKLEARN_VERSION):
            loaded = load_model_with_compatibility_check(model_path)
            assert loaded == mock_model

    def test_load_model_with_compatibility_check_warning(self, tmp_path: Path) -> None:
        """验证版本不匹配时发出警告"""
        model_path = tmp_path / "test_model.pkl"
        mock_model = {"test": "model"}

        import joblib

        joblib.dump(mock_model, model_path)
        # ISS-007 修复后 load_model_with_compatibility_check 强制 require_hash=True，
        # 需提供 .sha256 校验文件以满足 safe_joblib_load 的完整性校验。
        _write_sha256_checksum(model_path)

        with patch("sklearn.__version__", "1.2.0"):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                loaded = load_model_with_compatibility_check(model_path)
                assert loaded == mock_model
                assert len(w) >= 1
                assert any("version" in str(warning.message).lower() for warning in w)

    def test_target_version_constant(self) -> None:
        """验证目标版本号常量"""
        assert TARGET_SKLEARN_VERSION == "1.5.0"
        assert isinstance(TARGET_SKLEARN_VERSION, str)
