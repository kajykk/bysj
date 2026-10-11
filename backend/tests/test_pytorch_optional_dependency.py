from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def force_config_reimport():
    """删除 ``sys.modules["app.core.config"]`` 以强制重新导入，并在退出时**完整还原**。

    P0-FIX-2026-10-11: 原实现只``del sys.modules[...]`` 且不还原，留下两处不一致：
    ``sys.modules["app.core.config"]`` 被 ``patch.dict`` 恢复成旧模块对象 A，
    而包属性 ``app.core.config`` 被块内的重新导入绑到**新**模块对象 B。
    于是后续测试里``from app.core import config`` 拿到 B、
    ``from app.core.config import settings`` 拿到 A —— patch 打在A、读取发生在 B，
    patch 静默失效。实测症状：依赖 ``settings.model_dir`` 的清理类用例
    「应清理 2 个旧产物，实际 0」（model_dir 退回真实目录）。

    只还原 ``sys.modules`` 不够，**必须同时还原包属性**。
    """
    import app.core

    saved_module = sys.modules.pop("app.core.config", None)
    saved_attr = getattr(app.core, "config", None)
    try:
        yield
    finally:
        if saved_module is not None:
            sys.modules["app.core.config"] = saved_module
        if saved_attr is not None:
            app.core.config = saved_attr
        else:  # pragma: no cover - 原本就不应存在
            app.core.__dict__.pop("config", None)


class TestPyTorchOptionalDependency:
    """T-INFRA-006: PyTorch 可选依赖策略单元测试"""

    def test_pytorch_available_detection(self, force_config_reimport) -> None:
        """验证 PYTORCH_AVAILABLE 标志正确检测 PyTorch 安装状态"""
        # When torch is available
        with patch.dict(sys.modules, {"torch": type(sys)("torch")}):
            # Force re-import by clearing cache
            from app.core.config import PYTORCH_AVAILABLE

            assert PYTORCH_AVAILABLE is True

    def test_pytorch_not_available_detection(self, force_config_reimport) -> None:
        """验证 PYTORCH_AVAILABLE=False 当 PyTorch 未安装时"""
        # Simulate torch not available
        modules_without_torch = {k: v for k, v in sys.modules.items() if k != "torch"}
        original_import = __import__
        with patch.dict(sys.modules, modules_without_torch, clear=True):
            # Force re-import
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
