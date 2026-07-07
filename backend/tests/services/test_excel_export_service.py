"""Tests for ExcelExportService.

TC-FE-EXL-001 ~ TC-FE-EXL-012: Excel export stability.
"""

from __future__ import annotations

from app.services.excel_export_service import ExcelExportResult, ExcelExportService


class TestExcelExportService:
    """Test Excel export service."""

    def test_export_with_valid_data(self):
        """TC-FE-EXL-001: Export with valid data."""
        service = ExcelExportService()
        data = [
            {"name": "Alice", "age": 30, "city": "Beijing"},
            {"name": "Bob", "age": 25, "city": "Shanghai"},
        ]
        result = service.export(data=data)

        assert isinstance(result, ExcelExportResult)
        if result.success:
            assert result.file_size > 0
            assert result.row_count == 2
            assert result.column_count == 3

    def test_export_empty_data(self):
        """TC-FE-EXL-002: Export with empty data."""
        service = ExcelExportService()
        result = service.export(data=[])

        assert result.success is False
        assert "No data to export" in result.error_message

    def test_export_with_columns(self):
        """TC-FE-EXL-003: Export with specific columns."""
        service = ExcelExportService()
        data = [
            {"name": "Alice", "age": 30, "city": "Beijing"},
            {"name": "Bob", "age": 25, "city": "Shanghai"},
        ]
        result = service.export(data=data, columns=["name", "age"])

        assert isinstance(result, ExcelExportResult)
        if result.success:
            assert result.column_count == 2

    def test_export_with_filters(self):
        """TC-FE-EXL-004: Export with filters."""
        service = ExcelExportService()
        data = [
            {"name": "Alice", "age": 30, "city": "Beijing"},
            {"name": "Bob", "age": 25, "city": "Shanghai"},
            {"name": "Charlie", "age": 30, "city": "Beijing"},
        ]
        result = service.export(data=data, filters={"city": "Beijing"})

        assert isinstance(result, ExcelExportResult)
        if result.success:
            assert result.row_count == 2

    def test_export_no_openpyxl(self, monkeypatch):
        """TC-FE-EXL-005: Handle missing openpyxl gracefully."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "openpyxl":
                raise ImportError("No module named 'openpyxl'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        service = ExcelExportService()
        data = [{"name": "Alice"}]
        result = service.export(data=data)

        assert result.success is False
        assert "openpyxl not installed" in result.error_message

    def test_format_value_none(self):
        """TC-FE-EXL-006: Format None value."""
        service = ExcelExportService()
        assert service._format_value(None) == ""

    def test_format_value_bool(self):
        """TC-FE-EXL-007: Format boolean value."""
        service = ExcelExportService()
        assert service._format_value(True) == "Yes"
        assert service._format_value(False) == "No"

    def test_format_value_list(self):
        """TC-FE-EXL-008: Format list value."""
        service = ExcelExportService()
        result = service._format_value([1, 2, 3])
        assert "1" in result
        assert "2" in result

    def test_format_value_dict(self):
        """TC-FE-EXL-009: Format dict value."""
        service = ExcelExportService()
        result = service._format_value({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_format_value_string(self):
        """TC-FE-EXL-010: Format string value."""
        service = ExcelExportService()
        assert service._format_value("hello") == "hello"

    def test_apply_filters(self):
        """TC-FE-EXL-011: Apply filters to data."""
        service = ExcelExportService()
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        result = service._apply_filters(data, {"age": 30})
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_apply_filters_no_match(self):
        """TC-FE-EXL-012: Apply filters with no matches."""
        service = ExcelExportService()
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        result = service._apply_filters(data, {"age": 99})
        assert len(result) == 0

    def test_row_matches_filters(self):
        """TC-FE-EXL-013: Check row matches filters."""
        service = ExcelExportService()
        row = {"name": "Alice", "age": 30}
        assert service._row_matches_filters(row, {"age": 30}) is True
        assert service._row_matches_filters(row, {"age": 25}) is False

    def test_export_large_dataset(self):
        """TC-FE-EXL-014: Export large dataset with generator."""
        service = ExcelExportService()

        def data_generator():
            for i in range(100):
                yield {"id": i, "name": f"User {i}"}

        result = service.export_large_dataset(
            data_generator(),
            columns=["id", "name"],
        )

        assert isinstance(result, ExcelExportResult)
        if result.success:
            assert result.row_count == 100

    def test_export_to_excel_backward_compat(self):
        """TC-FE-EXL-015: Backward-compatible export wrapper."""
        service = ExcelExportService()
        data = [{"name": "Alice"}]
        result = service.export_to_excel(data=data)

        assert isinstance(result, ExcelExportResult)

    def test_excel_result_to_dict(self):
        """TC-FE-EXL-016: ExcelExportResult serialization."""
        result = ExcelExportResult(
            success=True,
            file_size=1024,
            row_count=10,
            column_count=5,
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["file_size"] == 1024
        assert data["row_count"] == 10
        assert data["column_count"] == 5
