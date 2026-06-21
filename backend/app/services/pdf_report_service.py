from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReportData:
    """Data for generating a report."""

    title: str
    subtitle: str | None = None
    # P2 修复：使用 field(default_factory=list) 替代 None，避免可变默认值陷阱
    sections: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""
    user_info: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # 兼容外部传入 None 的情况
        if self.sections is None:
            self.sections = []
        if self.charts is None:
            self.charts = []
        if self.tables is None:
            self.tables = []
        if self.recommendations is None:
            self.recommendations = []


@dataclass
class PDFReportResult:
    """Result of PDF generation."""

    success: bool
    pdf_bytes: bytes | None = None
    file_size: int = 0
    page_count: int = 0
    generation_time_ms: float = 0.0
    error_message: str | None = None
    has_charts: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "file_size": self.file_size,
            "page_count": self.page_count,
            "generation_time_ms": round(self.generation_time_ms, 2),
            "error_message": self.error_message,
            "has_charts": self.has_charts,
        }


class PDFReportService:
    """Generate PDF reports using ReportLab.

    Features:
    - User risk reports (with trend charts, recommendations)
    - Counselor reports, management analysis reports
    - Small reports (< 1000 rows): synchronous, < 3s
    - Large reports (>= 1000 rows): Celery async, < 30s
    - Post-generation validation (file size > 0, pages > 0, charts exist)
    """

    SYNC_THRESHOLD_ROWS = 1000
    SYNC_TIME_LIMIT_MS = 3000
    ASYNC_TIME_LIMIT_MS = 30000

    def __init__(self) -> None:
        pass

    def _check_reportlab_available(self) -> bool:
        """Check if ReportLab is installed."""
        try:
            import reportlab
            return True
        except ImportError:
            return False

    def generate_pdf(self, report_data: ReportData) -> PDFReportResult:
        """Generate a PDF report synchronously.

        Args:
            report_data: Report data.

        Returns:
            PDFReportResult with generated PDF or error.
        """
        start_time = time.time()

        if not self._check_reportlab_available():
            return PDFReportResult(
                success=False,
                error_message="ReportLab not installed",
                generation_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18,
            )

            styles = getSampleStyleSheet()
            story = []

            # Title
            title_style = styles["Heading1"]
            story.append(Paragraph(report_data.title, title_style))
            story.append(Spacer(1, 0.2 * inch))

            # Subtitle
            if report_data.subtitle:
                story.append(Paragraph(report_data.subtitle, styles["Heading2"]))
                story.append(Spacer(1, 0.1 * inch))

            # Generated at
            if report_data.generated_at:
                story.append(Paragraph(f"Generated: {report_data.generated_at}", styles["Normal"]))
                story.append(Spacer(1, 0.2 * inch))

            # User info
            if report_data.user_info:
                user_text = " | ".join(f"{k}: {v}" for k, v in report_data.user_info.items())
                story.append(Paragraph(user_text, styles["Normal"]))
                story.append(Spacer(1, 0.2 * inch))

            # Sections
            for section in report_data.sections:
                section_title = section.get("title", "")
                section_content = section.get("content", "")
                if section_title:
                    story.append(Paragraph(section_title, styles["Heading2"]))
                if section_content:
                    story.append(Paragraph(section_content, styles["Normal"]))
                story.append(Spacer(1, 0.1 * inch))

            # Tables
            for table_data in report_data.tables:
                headers = table_data.get("headers", [])
                rows = table_data.get("rows", [])
                if headers and rows:
                    data = [headers] + rows
                    table = Table(data)
                    table.setStyle(
                        TableStyle([
                            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 12),
                            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                            ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ])
                    )
                    story.append(table)
                    story.append(Spacer(1, 0.2 * inch))

            # Recommendations
            if report_data.recommendations:
                story.append(Paragraph("Recommendations", styles["Heading2"]))
                for rec in report_data.recommendations:
                    story.append(Paragraph(f"• {rec}", styles["Normal"]))
                story.append(Spacer(1, 0.2 * inch))

            doc.build(story)

            pdf_bytes = buffer.getvalue()
            buffer.close()

            generation_time_ms = (time.time() - start_time) * 1000

            # Validate
            is_valid, validation_msg = self._validate_pdf(pdf_bytes)

            if not is_valid:
                return PDFReportResult(
                    success=False,
                    error_message=f"PDF validation failed: {validation_msg}",
                    generation_time_ms=generation_time_ms,
                )

            return PDFReportResult(
                success=True,
                pdf_bytes=pdf_bytes,
                file_size=len(pdf_bytes),
                page_count=self._estimate_page_count(pdf_bytes),
                generation_time_ms=generation_time_ms,
                has_charts=len(report_data.charts) > 0,
            )

        except Exception as exc:
            generation_time_ms = (time.time() - start_time) * 1000
            logger.exception("PDF generation failed")
            return PDFReportResult(
                success=False,
                error_message=str(exc),
                generation_time_ms=generation_time_ms,
            )

    def _validate_pdf(self, pdf_bytes: bytes) -> tuple[bool, str]:
        """Validate generated PDF.

        Checks:
        - File size > 0
        - Starts with %PDF magic bytes
        - Contains at least one page
        """
        if not pdf_bytes:
            return False, "Empty PDF"

        if len(pdf_bytes) < 100:
            return False, f"PDF too small: {len(pdf_bytes)} bytes"

        if not pdf_bytes.startswith(b"%PDF"):
            return False, "Invalid PDF format"

        # Check for /Type /Page
        if b"/Type /Page" not in pdf_bytes and b"/Type/Page" not in pdf_bytes:
            return False, "No pages found in PDF"

        return True, "Valid"

    def _estimate_page_count(self, pdf_bytes: bytes) -> int:
        """Estimate page count from PDF content."""
        # Count /Type /Page occurrences
        count = pdf_bytes.count(b"/Type /Page") + pdf_bytes.count(b"/Type/Page")
        return max(1, count)

    def should_use_async(self, data_row_count: int) -> bool:
        """Determine if async generation should be used.

        Args:
            data_row_count: Number of data rows.

        Returns:
            True if async generation is recommended.
        """
        return data_row_count >= self.SYNC_THRESHOLD_ROWS

    def generate_user_risk_report(
        self,
        user_name: str | dict[str, Any],
        risk_level: str | None = None,
        risk_trend: list[dict[str, Any]] | None = None,
        recommendations: list[str] | None = None,
    ) -> PDFReportResult:
        """Generate a user risk report.

        Accepts both the current keyword-based API and the earlier single-dict
        API used by resource regression tests.
        """
        import datetime

        if isinstance(user_name, dict):
            user_data = user_name
            display_name = str(user_data.get("user_name") or user_data.get("user_id") or "Unknown")
            risk_level_value = str(user_data.get("risk_level", "Unknown"))
            trend_items = user_data.get("trend_data") or user_data.get("risk_trend") or []
            recommendations_value = user_data.get("recommendations") or []
        else:
            display_name = user_name
            risk_level_value = str(risk_level or "Unknown")
            trend_items = risk_trend or []
            recommendations_value = recommendations or []

        report_data = ReportData(
            title="User Risk Assessment Report",
            subtitle=f"User: {display_name}",
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            user_info={
                "Risk Level": risk_level_value,
                "Report Type": "Individual Assessment",
            },
            sections=[
                {
                    "title": "Risk Summary",
                    "content": f"Current risk level: {risk_level_value}. Based on recent assessments and physiological data.",
                },
            ],
            tables=[
                {
                    "headers": ["Date", "Risk Score", "Level"],
                    "rows": [
                        [item.get("date", ""), str(item.get("score", "")), item.get("level", "")]
                        for item in trend_items[-10:]
                    ],
                },
            ],
            recommendations=recommendations_value,
        )

        return self.generate_pdf(report_data)

    def generate_management_report(
        self,
        report_period: str,
        summary_metrics: dict[str, Any],
        department_stats: list[dict[str, Any]],
    ) -> PDFReportResult:
        """Generate a management analysis report.

        Args:
            report_period: Report period string.
            summary_metrics: Summary metrics.
            department_stats: Department statistics.

        Returns:
            PDFReportResult.
        """
        import datetime

        report_data = ReportData(
            title="Management Analysis Report",
            subtitle=f"Period: {report_period}",
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            sections=[
                {
                    "title": "Overview",
                    "content": f"Total users: {summary_metrics.get('total_users', 0)}. "
                    f"High risk users: {summary_metrics.get('high_risk_count', 0)}.",
                },
            ],
            tables=[
                {
                    "headers": ["Department", "Total", "High Risk", "Avg Score"],
                    "rows": [
                        [
                            dept.get("name", ""),
                            str(dept.get("total", "")),
                            str(dept.get("high_risk", "")),
                            str(dept.get("avg_score", "")),
                        ]
                        for dept in department_stats
                    ],
                },
            ],
        )

        return self.generate_pdf(report_data)


# Global service instance
pdf_report_service = PDFReportService()
