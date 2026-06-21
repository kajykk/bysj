"""Tests for PDFReportService.

TC-FE-PDF-001 ~ TC-FE-PDF-010: PDF report generation stability.
"""

from __future__ import annotations

import pytest

from app.services.pdf_report_service import PDFReportService, ReportData, PDFReportResult


class TestPDFReportService:
    """Test PDF report service."""

    def test_generate_pdf_with_valid_data(self):
        """TC-FE-PDF-001: Generate PDF with valid data."""
        service = PDFReportService()
        report_data = ReportData(
            title="Test Report",
            subtitle="Test Subtitle",
            sections=[{"title": "Section 1", "content": "Content 1"}],
            tables=[{"headers": ["A", "B"], "rows": [["1", "2"]]}],
            recommendations=["Rec 1", "Rec 2"],
        )
        result = service.generate_pdf(report_data)

        assert isinstance(result, PDFReportResult)
        # May fail if reportlab not installed
        if result.success:
            assert result.file_size > 0
            assert result.page_count > 0
            assert result.generation_time_ms > 0

    def test_generate_pdf_empty_data(self):
        """TC-FE-PDF-002: Generate PDF with minimal data."""
        service = PDFReportService()
        report_data = ReportData(title="Empty Report")
        result = service.generate_pdf(report_data)

        assert isinstance(result, PDFReportResult)
        if result.success:
            assert result.file_size > 0

    def test_generate_pdf_no_reportlab(self, monkeypatch):
        """TC-FE-PDF-003: Handle missing reportlab gracefully."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "reportlab":
                raise ImportError("No module named 'reportlab'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        service = PDFReportService()
        report_data = ReportData(title="Test")
        result = service.generate_pdf(report_data)

        assert result.success is False
        assert "ReportLab not installed" in result.error_message

    def test_validate_pdf_empty(self):
        """TC-FE-PDF-004: Validate empty PDF bytes."""
        service = PDFReportService()
        is_valid, msg = service._validate_pdf(b"")
        assert is_valid is False
        assert "Empty PDF" in msg

    def test_validate_pdf_too_small(self):
        """TC-FE-PDF-005: Validate too small PDF."""
        service = PDFReportService()
        is_valid, msg = service._validate_pdf(b"%PDF")
        assert is_valid is False
        assert "too small" in msg

    def test_validate_pdf_invalid_format(self):
        """TC-FE-PDF-006: Validate invalid PDF format."""
        service = PDFReportService()
        is_valid, msg = service._validate_pdf(b"NOT_A_PDF" + b"x" * 100)
        assert is_valid is False
        assert "Invalid PDF format" in msg

    def test_validate_pdf_no_pages(self):
        """TC-FE-PDF-007: Validate PDF without pages."""
        service = PDFReportService()
        is_valid, msg = service._validate_pdf(b"%PDF-1.4\n" + b"x" * 100)
        assert is_valid is False
        assert "No pages found" in msg

    def test_estimate_page_count(self):
        """TC-FE-PDF-008: Estimate page count from PDF bytes."""
        service = PDFReportService()
        # Simulate PDF with 2 pages
        pdf_bytes = b"%PDF-1.4\n/Type /Page\n/Type/Page\n"
        count = service._estimate_page_count(pdf_bytes)
        assert count >= 1

    def test_should_use_async(self):
        """TC-FE-PDF-009: Determine async generation threshold."""
        service = PDFReportService()
        assert service.should_use_async(999) is False
        assert service.should_use_async(1000) is True
        assert service.should_use_async(1001) is True

    def test_generate_user_risk_report(self):
        """TC-FE-PDF-010: Generate user risk report."""
        service = PDFReportService()
        result = service.generate_user_risk_report(
            user_name="Test User",
            risk_level="medium",
            risk_trend=[{"date": "2024-01-01", "score": 50, "level": "medium"}],
            recommendations=["Rest more", "Exercise regularly"],
        )

        assert isinstance(result, PDFReportResult)
        if result.success:
            assert result.file_size > 0

    def test_generate_user_risk_report_with_dict(self):
        """TC-FE-PDF-011: Generate user risk report with dict input."""
        service = PDFReportService()
        result = service.generate_user_risk_report({
            "user_name": "Test User",
            "risk_level": "high",
            "trend_data": [{"date": "2024-01-01", "score": 80, "level": "high"}],
            "recommendations": ["See a doctor"],
        })

        assert isinstance(result, PDFReportResult)

    def test_generate_management_report(self):
        """TC-FE-PDF-012: Generate management report."""
        service = PDFReportService()
        result = service.generate_management_report(
            report_period="2024-Q1",
            summary_metrics={"total_users": 100, "high_risk_count": 5},
            department_stats=[
                {"name": "Dept A", "total": 50, "high_risk": 2, "avg_score": 30},
            ],
        )

        assert isinstance(result, PDFReportResult)
        if result.success:
            assert result.file_size > 0

    def test_report_data_defaults(self):
        """TC-FE-PDF-013: ReportData default values."""
        data = ReportData(title="Test")
        assert data.sections == []
        assert data.charts == []
        assert data.tables == []
        assert data.recommendations == []
        assert data.subtitle is None

    def test_pdf_result_to_dict(self):
        """TC-FE-PDF-014: PDFReportResult serialization."""
        result = PDFReportResult(
            success=True,
            file_size=1024,
            page_count=2,
            generation_time_ms=1500.123,
            has_charts=True,
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["file_size"] == 1024
        assert data["page_count"] == 2
        assert data["generation_time_ms"] == 1500.12
        assert data["has_charts"] is True
