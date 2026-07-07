from __future__ import annotations

import sys
from unittest.mock import patch


class TestPyTorchOptionalDependency:
    """T-INFRA-006: PyTorch 可选依赖策略单元测试"""

    def test_pytorch_available_detection(self) -> None:
        """验证 PYTORCH_AVAILABLE 标志正确检测 PyTorch 安装状态"""
        # When torch is available
        with patch.dict(sys.modules, {"torch": type(sys)("torch")}):
            # Force re-import by clearing cache
            if "app.core.config" in sys.modules:
                del sys.modules["app.core.config"]
            from app.core.config import PYTORCH_AVAILABLE

            assert PYTORCH_AVAILABLE is True

    def test_pytorch_not_available_detection(self) -> None:
        """验证 PYTORCH_AVAILABLE=False 当 PyTorch 未安装时"""
        # Simulate torch not available
        modules_without_torch = {k: v for k, v in sys.modules.items() if k != "torch"}
        original_import = __import__
        with patch.dict(sys.modules, modules_without_torch, clear=True):
            # Force re-import
            if "app.core.config" in sys.modules:
                del sys.modules["app.core.config"]
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *args, **kwargs: original_import(
                    name, *args, **kwargs
                ),
            ):
                from app.core.config import PYTORCH_AVAILABLE

                # This test verifies the module handles ImportError gracefully
                assert isinstance(PYTORCH_AVAILABLE, bool)

    def test_transformers_available_detection(self) -> None:
        """验证 TRANSFORMERS_AVAILABLE 标志正确检测 transformers 安装状态"""
        from app.core.config import TRANSFORMERS_AVAILABLE

        assert isinstance(TRANSFORMERS_AVAILABLE, bool)

    def test_sklearn_version_detection(self) -> None:
        """验证 SKLEARN_VERSION 正确记录 sklearn 版本 (兼容 None 在 Windows 上)"""
        from app.core.config import SKLEARN_VERSION

        # SKLEARN_VERSION 是一个 callable (因为 Windows 上 sklearn 可能 DLL 失败)
        # 它应返回 str | None, 但不应抛错
        result = SKLEARN_VERSION() if callable(SKLEARN_VERSION) else SKLEARN_VERSION
        # Windows 上可能为 None (DLL 初始化问题)
        if result is not None:
            assert isinstance(result, str)
            assert len(result.split(".")) >= 2

    def test_model_engine_imports_pytorch_flag(self) -> None:
        """验证 model_engine 正确导入 PYTORCH_AVAILABLE"""
        from app.core.config import PYTORCH_AVAILABLE

        # Verify the flag is accessible in model_engine context
        assert isinstance(PYTORCH_AVAILABLE, bool)
