"""Tests for STAB-P2-005: 覆盖率门禁分阶段提升策略.

验证 pytest.ini 中覆盖率门禁配置正确, 且分阶段提升策略已文档化.
实际阈值提升需在完整测试套件确认覆盖率后逐步进行.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PYTEST_INI = Path(__file__).resolve().parent.parent / "pytest.ini"


class TestCoverageThresholdConfig:
    """Test coverage threshold configuration in pytest.ini."""

    def test_pytest_ini_exists(self) -> None:
        """pytest.ini should exist."""
        assert _PYTEST_INI.exists(), f"pytest.ini should exist: {_PYTEST_INI}"

    def test_current_threshold_is_configured(self) -> None:
        """pytest.ini should have --cov-fail-under configured."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        assert "--cov-fail-under" in content, (
            "pytest.ini should have --cov-fail-under setting"
        )

    def test_current_threshold_at_least_40(self) -> None:
        """Current coverage threshold should be at least 40% (P0 baseline)."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        match = re.search(r"--cov-fail-under=(\d+)", content)
        assert match, "Should find --cov-fail-under=N in pytest.ini"
        threshold = int(match.group(1))
        assert threshold >= 40, (
            f"Coverage threshold should be >= 40 (P0 baseline), got {threshold}"
        )

    def test_phased_plan_documented(self) -> None:
        """Phased coverage improvement plan should be documented."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        # Should mention phased targets
        assert "60" in content, "Should document Phase 3 target (60%)"
        assert "70" in content, "Should document Phase 5-7 target (70%)"

    def test_stab_p2_005_referenced(self) -> None:
        """STAB-P2-005 task should be referenced in pytest.ini comments."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        assert "STAB-P2-005" in content, (
            "pytest.ini should reference STAB-P2-005 for traceability"
        )

    def test_coverage_reports_configured(self) -> None:
        """Coverage reports (term, html, xml) should be configured."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        assert "--cov-report=term-missing" in content, (
            "Should have term-missing coverage report"
        )
        assert "--cov-report=html" in content, "Should have HTML coverage report"
        assert "--cov-report=xml" in content, "Should have XML coverage report"

    def test_cov_target_is_app(self) -> None:
        """Coverage should target the 'app' package."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        assert "--cov=app" in content, "Coverage should target the 'app' package"


class TestPhasedPlanStructure:
    """Test the phased coverage improvement plan structure (STAB-P2-005)."""

    def test_plan_has_p0_baseline(self) -> None:
        """Plan should document P0 baseline (40%)."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        assert "P0" in content or "基线" in content, (
            "Plan should reference P0 baseline"
        )

    def test_plan_has_multiple_phases(self) -> None:
        """Plan should have multiple phases with increasing thresholds."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        # Should mention at least 3 different threshold values
        thresholds = re.findall(r"(?:cov-fail-under=|under=)(\d+)", content)
        # Also check for plan mentions like "Phase 1-2: ... 50"
        plan_thresholds = re.findall(r"(\d+)\s*\(", content)
        all_thresholds = thresholds + plan_thresholds
        unique_thresholds = set(int(t) for t in all_thresholds if t.isdigit())
        assert len(unique_thresholds) >= 3, (
            f"Plan should have at least 3 threshold stages, "
            f"found: {unique_thresholds}"
        )

    def test_plan_thresholds_are_increasing(self) -> None:
        """Plan thresholds should be monotonically increasing."""
        content = _PYTEST_INI.read_text(encoding="utf-8")
        # Extract all threshold numbers from plan comments
        plan_lines = [
            line for line in content.split("\n")
            if "cov-fail-under" in line and ("Phase" in line or "P0" in line)
        ]
        thresholds = []
        for line in plan_lines:
            match = re.search(r"cov-fail-under=(\d+)", line)
            if match:
                thresholds.append(int(match.group(1)))
        # Verify increasing (if we found at least 2)
        if len(thresholds) >= 2:
            for i in range(1, len(thresholds)):
                assert thresholds[i] > thresholds[i - 1], (
                    f"Thresholds should increase: {thresholds[i-1]} -> {thresholds[i]}"
                )
