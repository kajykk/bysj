"""MAINT-P2-003: import-linter 配置正确性测试.

验证:
1. pyproject.toml 含 [tool.importlinter] 配置节
2. forbidden contract 配置完整 (source/forbidden/ignore_imports)
3. app/core/__init__.py 显式存在 (让 app.core 成为常规包供 grimp 识别)
4. model_engine.py 顶层不再导入 app.ml (已改为 __init__ 内延迟导入)
5. lint-imports 命令执行成功 (契约保持)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
PYPROJECT = BACKEND_DIR / "pyproject.toml"


def _read_pyproject() -> str:
    if not PYPROJECT.exists():
        pytest.skip("pyproject.toml not found")
    return PYPROJECT.read_text(encoding="utf-8")


class TestImportLinterConfig:
    """验证 pyproject.toml 中 import-linter 配置."""

    def test_pyproject_has_importlinter_section(self) -> None:
        content = _read_pyproject()
        assert "[tool.importlinter]" in content, (
            "pyproject.toml 缺少 [tool.importlinter] 配置节"
        )

    def test_root_packages_configured(self) -> None:
        content = _read_pyproject()
        assert 'root_packages = ["app"]' in content, (
            "root_packages 必须配置为 ['app']"
        )

    def test_forbidden_contract_exists(self) -> None:
        content = _read_pyproject()
        assert 'type = "forbidden"' in content, "缺少 forbidden 类型契约"
        assert "Core layer must not depend on ml/services layers" in content

    def test_forbidden_contract_source_and_target(self) -> None:
        content = _read_pyproject()
        assert 'source_modules = ["app.core"]' in content
        assert "app.ml" in content and "app.services" in content

    def test_ignore_imports_covers_known_tech_debt(self) -> None:
        """6 处已知技术债必须显式豁免, 否则 lint-imports 会失败."""
        content = _read_pyproject()
        expected_pairs = [
            ("app.core.model_engine", "app.ml.fusion_engine"),
            ("app.core.model_engine", "app.ml.fusion_priority_engine"),
            ("app.core.model_engine", "app.ml.text_analyzer"),
            ("app.core.model_engine_predict", "app.ml.model_loader"),
            ("app.core.model_engine_predict", "app.ml.data_cleaner"),
            ("app.core.model_engine_predict", "app.ml.feature_engineering"),
        ]
        for src, dst in expected_pairs:
            pair = f"{src} -> {dst}"
            assert pair in content, f"缺少 ignore_imports 豁免: {pair}"


class TestCorePackageInit:
    """app.core 必须是常规包 (有 __init__.py), grimp 才能识别."""

    def test_core_init_py_exists(self) -> None:
        init_path = BACKEND_DIR / "app" / "core" / "__init__.py"
        assert init_path.exists(), (
            "app/core/__init__.py 必须存在 (让 app.core 成为常规包供 import-linter 识别)"
        )

    def test_api_init_py_exists(self) -> None:
        init_path = BACKEND_DIR / "app" / "api" / "__init__.py"
        assert init_path.exists(), "app/api/__init__.py 必须存在"


class TestModelEngineLazyImport:
    """model_engine.py 顶层不应导入 app.ml (已改为 __init__ 内延迟导入)."""

    @staticmethod
    def _read_active_top_level(source: str) -> str:
        """提取顶层活跃代码 (排除注释行与空行)."""
        lines: list[str] = []
        for line in source.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            lines.append(line)
        return "\n".join(lines)

    def test_model_engine_no_top_level_app_ml_import(self) -> None:
        path = BACKEND_DIR / "app" / "core" / "model_engine.py"
        source = path.read_text(encoding="utf-8")
        active = self._read_active_top_level(source)

        # 模块顶层 (非函数体内) 不应出现 from app.ml.xxx import
        # 简化检查: 顶层 import 语句不应包含 app.ml
        # 通过检查所有未缩进的 import 行
        bad_lines: list[str] = []
        for line in active.split("\n"):
            if not line.startswith((" ", "\t")):  # 仅顶层 (未缩进)
                if "from app.ml" in line or "import app.ml" in line:
                    bad_lines.append(line)
        assert not bad_lines, (
            "model_engine.py 顶层仍存在 app.ml 导入 (应改为函数内延迟导入): "
            + " | ".join(bad_lines)
        )

    def test_model_engine_lazy_imports_in_init(self) -> None:
        """__init__ 内部应有 app.ml 延迟导入."""
        path = BACKEND_DIR / "app" / "core" / "model_engine.py"
        source = path.read_text(encoding="utf-8")
        # __init__ 方法内应有这三个延迟导入
        assert "from app.ml.fusion_engine import FusionEngine" in source
        assert "from app.ml.fusion_priority_engine import FusionPriorityEngine" in source
        assert "from app.ml.text_analyzer import TextAnalyzer" in source


class TestLintImportsExecution:
    """端到端: lint-imports 命令应成功执行 (exit code 0)."""

    def test_lint_imports_passes(self) -> None:
        # import-linter 通过 lint-imports 入口点执行, 而非 python -m importlinter
        # (后者报 'No module named importlinter.__main__')
        try:
            result = subprocess.run(
                ["lint-imports"],
                cwd=BACKEND_DIR,
                capture_output=True,
                text=True,
                timeout=120,
                shell=True,
            )
        except FileNotFoundError as exc:
            pytest.skip(f"lint-imports 未安装: {exc}")

        assert result.returncode == 0, (
            f"lint-imports 失败 (exit={result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-2000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )
        # 成功时输出包含 "Contracts: X kept, 0 broken"
        assert "0 broken" in result.stdout, (
            f"契约存在 broken:\n{result.stdout[-1500:]}"
        )
