from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExcelExportResult:
    """Result of Excel export."""

    success: bool
    excel_bytes: bytes | None = None
    file_size: int = 0
    row_count: int = 0
    column_count: int = 0
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "file_size": self.file_size,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "error_message": self.error_message,
        }


class ExcelExportService:
    """Export data to Excel (.xlsx) using openpyxl.

    Features:
    - Support 10000+ rows export
    - Column filtering and filtering conditions
    - Streaming write to prevent memory overflow
    """

    BATCH_SIZE = 1000

    def __init__(self) -> None:
        pass

    def export_to_excel(self, data: list[dict[str, Any]], filename: str | None = None) -> ExcelExportResult:
        """Backward-compatible Excel export wrapper used by performance tests."""
        return self.export(data=data)

    def _check_openpyxl_available(self) -> bool:
        """Check if openpyxl is installed."""
        try:
            import openpyxl
            return True
        except ImportError:
            return False

    def export(
        self,
        data: list[dict[str, Any]],
        columns: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> ExcelExportResult:
        """Export data to Excel.

        Args:
            data: List of dictionaries with data.
            columns: List of columns to include. If None, use all keys from first row.
            filters: Dictionary of column -> value to filter by.

        Returns:
            ExcelExportResult with generated Excel file or error.
        """
        if not self._check_openpyxl_available():
            return ExcelExportResult(
                success=False,
                error_message="openpyxl not installed",
            )

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font

            if not data:
                return ExcelExportResult(
                    success=False,
                    error_message="No data to export",
                )

            # Determine columns
            if columns is None:
                columns = list(data[0].keys())

            # Apply filters
            filtered_data = self._apply_filters(data, filters)

            # Create workbook
            wb = Workbook(write_only=True)
            ws = wb.create_sheet(title="Data")

            # Write header
            ws.append(columns)

            # Write data in batches
            row_count = 0
            for i in range(0, len(filtered_data), self.BATCH_SIZE):
                batch = filtered_data[i : i + self.BATCH_SIZE]
                for row in batch:
                    row_values = [self._format_value(row.get(col)) for col in columns]
                    ws.append(row_values)
                    row_count += 1

            # Save to buffer
            buffer = io.BytesIO()
            wb.save(buffer)
            excel_bytes = buffer.getvalue()
            buffer.close()

            return ExcelExportResult(
                success=True,
                excel_bytes=excel_bytes,
                file_size=len(excel_bytes),
                row_count=row_count,
                column_count=len(columns),
            )

        except Exception as exc:
            logger.exception("Excel export failed")
            return ExcelExportResult(
                success=False,
                error_message=str(exc),
            )

    def _apply_filters(
        self,
        data: list[dict[str, Any]],
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Apply filters to data.

        Args:
            data: Original data.
            filters: Dictionary of column -> value to filter by.

        Returns:
            Filtered data.
        """
        if not filters:
            return data

        filtered = []
        for row in data:
            match = True
            for col, value in filters.items():
                if col in row and row[col] != value:
                    match = False
                    break
            if match:
                filtered.append(row)

        return filtered

    def _format_value(self, value: Any) -> str:
        """Format a value for Excel output.

        FE-003 修复：对以 =, +, -, @, \\t, \\r 开头的字符串进行转义，
        防止 Excel 公式注入攻击（CSV/Formula Injection）。

        Args:
            value: Value to format.

        Returns:
            Formatted and sanitized string.
        """
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (list, dict)):
            import json

            return self._sanitize_cell_value(json.dumps(value, ensure_ascii=False))
        return self._sanitize_cell_value(str(value))

    @staticmethod
    def _sanitize_cell_value(value: str) -> str:
        """FE-003 修复：转义 Excel 公式注入危险字符。

        当单元格值以 ``=``、``+``、``-``、``@``、``\\t``、``\\r`` 开头时，
        Excel 会将其解释为公式，可能导致公式注入攻击（如 ``=HYPERLINK(...)``、
        ``=cmd|'/c calc'!A1``）。通过在前面添加单引号 ``'`` 强制 Excel 将其
        作为文本处理（单引号在 Excel 中不会显示）。

        对于 ``-`` 开头的值，仅当其不是合法数字时才转义（避免影响负数导出）。
        """
        if not value:
            return value
        # 危险前缀字符
        dangerous_prefixes = ("=", "+", "@", "\t", "\r")
        if value.startswith(dangerous_prefixes):
            return "'" + value
        # 对 "-" 开头的值：仅当不是合法数字时才转义
        if value.startswith("-"):
            try:
                float(value)
            except ValueError:
                return "'" + value
        return value

    def export_large_dataset(
        self,
        data_generator,
        columns: list[str],
        filters: dict[str, Any] | None = None,
    ) -> ExcelExportResult:
        """Export large dataset using generator for memory efficiency.

        Args:
            data_generator: Generator yielding dictionaries.
            columns: List of columns to include.
            filters: Dictionary of column -> value to filter by.

        Returns:
            ExcelExportResult.
        """
        if not self._check_openpyxl_available():
            return ExcelExportResult(
                success=False,
                error_message="openpyxl not installed",
            )

        try:
            from openpyxl import Workbook

            wb = Workbook(write_only=True)
            ws = wb.create_sheet(title="Data")

            # Write header
            ws.append(columns)

            row_count = 0
            for row in data_generator:
                if filters and not self._row_matches_filters(row, filters):
                    continue

                row_values = [self._format_value(row.get(col)) for col in columns]
                ws.append(row_values)
                row_count += 1

            buffer = io.BytesIO()
            wb.save(buffer)
            excel_bytes = buffer.getvalue()
            buffer.close()

            return ExcelExportResult(
                success=True,
                excel_bytes=excel_bytes,
                file_size=len(excel_bytes),
                row_count=row_count,
                column_count=len(columns),
            )

        except Exception as exc:
            logger.exception("Large Excel export failed")
            return ExcelExportResult(
                success=False,
                error_message=str(exc),
            )

    def _row_matches_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Check if a row matches all filters.

        Args:
            row: Data row.
            filters: Filters to apply.

        Returns:
            True if row matches all filters.
        """
        for col, value in filters.items():
            if col in row and row[col] != value:
                return False
        return True


# Global service instance
excel_export_service = ExcelExportService()
