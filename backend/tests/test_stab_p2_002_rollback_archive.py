"""Tests for STAB-P2-002: v1.15 ROLLBACK_PLAN archived as superseded.

Verifies that the v1.15 rollback plan is properly annotated as superseded
and points to the newer v1.28 rollback plan.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# Path to the v1.15 rollback plan (relative to backend/tests/)
# __file__ = backend/tests/test_stab_p2_002_rollback_archive.py
# parent = tests/, parent.parent = backend/, parent.parent.parent = project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_V115_ROLLBACK_PLAN = (
    _PROJECT_ROOT
    / "docs"
    / "planning"
    / "v1.15-launch-readiness"
    / "ROLLBACK_PLAN.md"
)

# Path to the v1.28 rollback plan (the replacement)
_V128_ROLLBACK_PLAN = (
    _PROJECT_ROOT
    / "docs"
    / "planning"
    / "v1.28-final-delivery"
    / "ROLLBACK_PLAN.md"
)


class TestV115RollbackPlanArchived:
    """Test that v1.15 ROLLBACK_PLAN is properly archived (STAB-P2-002)."""

    def test_v115_rollback_plan_exists(self) -> None:
        """v1.15 ROLLBACK_PLAN.md should still exist (archived, not deleted)."""
        assert _V115_ROLLBACK_PLAN.exists(), (
            f"v1.15 ROLLBACK_PLAN should exist as archived doc: {_V115_ROLLBACK_PLAN}"
        )

    def test_v115_rollback_plan_marked_superseded(self) -> None:
        """v1.15 ROLLBACK_PLAN should be marked as Superseded."""
        content = _V115_ROLLBACK_PLAN.read_text(encoding="utf-8")
        assert "Superseded" in content, (
            "v1.15 ROLLBACK_PLAN should contain 'Superseded' status annotation"
        )

    def test_v115_rollback_plan_draft_crossed_out(self) -> None:
        """The original 'Draft' status should be crossed out (~~Draft~~)."""
        content = _V115_ROLLBACK_PLAN.read_text(encoding="utf-8")
        assert "~~Draft~~" in content, (
            "Original 'Draft' status should be crossed out with ~~Draft~~"
        )

    def test_v115_rollback_plan_has_archive_notice(self) -> None:
        """v1.15 ROLLBACK_PLAN should have an ARCHIVED notice."""
        content = _V115_ROLLBACK_PLAN.read_text(encoding="utf-8")
        assert "ARCHIVED" in content, (
            "v1.15 ROLLBACK_PLAN should contain 'ARCHIVED' notice"
        )

    def test_v115_rollback_plan_references_v128_replacement(self) -> None:
        """v1.15 ROLLBACK_PLAN should reference the v1.28 replacement document."""
        content = _V115_ROLLBACK_PLAN.read_text(encoding="utf-8")
        assert "v1.28" in content, (
            "v1.15 ROLLBACK_PLAN should reference v1.28 as replacement"
        )
        assert "ROLLBACK_PLAN.md" in content, (
            "v1.15 ROLLBACK_PLAN should link to v1.28 ROLLBACK_PLAN.md"
        )

    def test_v128_replacement_exists(self) -> None:
        """The referenced v1.28 ROLLBACK_PLAN should exist."""
        assert _V128_ROLLBACK_PLAN.exists(), (
            f"v1.28 ROLLBACK_PLAN (replacement) should exist: {_V128_ROLLBACK_PLAN}"
        )

    def test_v115_rollback_plan_has_stab_p2_002_reference(self) -> None:
        """v1.15 ROLLBACK_PLAN should reference STAB-P2-002 task ID."""
        content = _V115_ROLLBACK_PLAN.read_text(encoding="utf-8")
        assert "STAB-P2-002" in content, (
            "v1.15 ROLLBACK_PLAN should reference STAB-P2-002 task ID for traceability"
        )

    def test_v115_rollback_plan_has_archive_date(self) -> None:
        """v1.15 ROLLBACK_PLAN should have an archive date."""
        content = _V115_ROLLBACK_PLAN.read_text(encoding="utf-8")
        assert "2026-07-12" in content, (
            "v1.15 ROLLBACK_PLAN should have archive date 2026-07-12"
        )
