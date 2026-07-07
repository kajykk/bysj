"""T-COV: CrisisExportService 单元测试.

覆盖 app/services/crisis_export_service.py 的全部公开方法 + 私有辅助:
- _sanitize_csv_cell: None / 空串 / 危险前缀 (=, +, @, \\t, \\r, \\n) / 合法负数 / 非数字 - 开头
- _mask_user_id: 短 ID (<=2 位) / 长 ID (>2 位)
- export_crisis_events: 空结果 / 含数据 / 时间范围过滤 / CSV 注入防护 / 空字段处理 / 文件名格式

覆盖原未测行: L30-42, L49, L67-114, L119-122.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import CrisisEvent
from app.services.crisis_export_service import (
    CrisisExportService,
    _sanitize_csv_cell,
)


@pytest.fixture
def service(db_session: AsyncSession) -> CrisisExportService:
    """构造 CrisisExportService, 注入真实 db_session."""
    return CrisisExportService(db_session)


@pytest.fixture
async def seeded_crisis_events(
    db_session: AsyncSession, seeded_user_id: int
) -> list[int]:
    """插入 3 条 CrisisEvent 用于导出测试 (覆盖正常 / 已处理 / 不同用户)."""
    rows = [
        CrisisEvent(
            user_id=1,
            trigger_source="keyword",
            crisis_score=85.0,
            status="detected",
            input_summary="用户表达低落情绪",
        ),
        CrisisEvent(
            user_id=1,
            trigger_source="model",
            crisis_score=72.5,
            status="handled",
            handled_by=3,
            handled_action="已联系咨询师跟进",
        ),
        CrisisEvent(
            user_id=2,
            trigger_source="keyword",
            crisis_score=90.0,
            status="detected",
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return [r.id for r in rows]


class TestSanitizeCsvCell:
    """_sanitize_csv_cell 单元测试 (覆盖 L30-42)."""

    def test_none_returns_empty(self):
        """TC-COV-EXP-001: None 返回空串 (L30-31)."""
        assert _sanitize_csv_cell(None) == ""

    def test_empty_string_returns_empty(self):
        """TC-COV-EXP-002: 空字符串原样返回 (L33-34 短路)."""
        assert _sanitize_csv_cell("") == ""

    def test_normal_string_unchanged(self):
        """TC-COV-EXP-003: 普通字符串不加转义 (L42 兜底返回)."""
        assert _sanitize_csv_cell("hello") == "hello"

    def test_equal_prefix_escaped(self):
        """TC-COV-EXP-004: '=' 前缀公式注入被转义 (L35-36)."""
        assert _sanitize_csv_cell("=HYPERLINK('evil')") == "'=HYPERLINK('evil')"

    def test_plus_prefix_escaped(self):
        """TC-COV-EXP-005: '+' 前缀被转义 (L35-36)."""
        assert _sanitize_csv_cell("+1+0") == "'+1+0"

    def test_at_prefix_escaped(self):
        """TC-COV-EXP-006: '@' 前缀被转义 (L35-36)."""
        assert _sanitize_csv_cell("@SUM(A1)") == "'@SUM(A1)"

    def test_tab_prefix_escaped(self):
        """TC-COV-EXP-007: '\\t' 前缀被转义 (L35-36)."""
        assert _sanitize_csv_cell("\tcmd") == "'\tcmd"

    def test_newline_prefix_escaped(self):
        """TC-COV-EXP-008: '\\n' 前缀被转义 (L35-36)."""
        assert _sanitize_csv_cell("\nfoo") == "'\nfoo"

    def test_carriage_return_prefix_escaped(self):
        """TC-COV-EXP-009: '\\r' 前缀被转义 (L35-36)."""
        assert _sanitize_csv_cell("\rbar") == "'\rbar"

    def test_negative_float_not_escaped(self):
        """TC-COV-EXP-010: 合法负浮点数不转义 (L37-41 try 成功路径)."""
        assert _sanitize_csv_cell("-3.14") == "-3.14"

    def test_negative_integer_not_escaped(self):
        """TC-COV-EXP-011: 合法负整数不转义 (L37-41 try 成功路径)."""
        assert _sanitize_csv_cell("-100") == "-100"

    def test_dash_non_numeric_escaped(self):
        """TC-COV-EXP-012: '-' 开头但非合法数字时被转义 (L40-41 ValueError 分支)."""
        result = _sanitize_csv_cell("-cmd|'/c calc'!A1")
        assert result == "'-cmd|'/c calc'!A1"

    def test_numeric_value_passthrough(self):
        """TC-COV-EXP-013: 数字类型转字符串后正常处理 (L32 str() 分支)."""
        assert _sanitize_csv_cell(42) == "42"
        assert _sanitize_csv_cell(3.14) == "3.14"


class TestMaskUserId:
    """_mask_user_id 静态方法测试 (覆盖 L119-122)."""

    def test_single_digit_id_appends_mask(self):
        """TC-COV-EXP-014: 单字符 ID (len<=2) 直接追加 **** (L120-121)."""
        assert CrisisExportService._mask_user_id(1) == "1****"

    def test_two_digit_id_appends_mask(self):
        """TC-COV-EXP-015: 两字符 ID (len<=2) 直接追加 **** (L120-121)."""
        assert CrisisExportService._mask_user_id(99) == "99****"

    def test_long_id_keeps_prefix_only(self):
        """TC-COV-EXP-016: 多字符 ID (len>2) 仅保留前 2 位 (L122)."""
        assert CrisisExportService._mask_user_id(12345) == "12****"
        assert CrisisExportService._mask_user_id(9876543) == "98****"


class TestExportCrisisEvents:
    """export_crisis_events 主流程测试 (覆盖 L49, L67-114)."""

    async def test_empty_result_returns_header_only(self, service: CrisisExportService):
        """TC-COV-EXP-017: 无数据时返回仅含表头的 CSV + 正确文件名 (L67-114 happy path 空数据)."""
        start = date(2024, 1, 1)
        end = date(2024, 1, 31)
        csv_content, filename = await service.export_crisis_events(start, end)

        # 文件名格式校验
        assert filename == "crisis_events_20240101_20240131.csv"
        # 表头存在
        lines = csv_content.splitlines()
        assert len(lines) == 1
        assert "id" in lines[0]
        assert "crisis_score" in lines[0]
        assert "handled_by" in lines[0]

    async def test_export_with_data(
        self, service: CrisisExportService, seeded_crisis_events: list[int]
    ):
        """TC-COV-EXP-018: 含数据时正确导出 (含 user_id / handled_by 脱敏)."""
        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
        csv_content, filename = await service.export_crisis_events(start, end)

        # 文件名格式校验
        assert filename.startswith("crisis_events_")
        assert filename.endswith(".csv")

        # 解析 CSV 验证内容
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader)
        assert header == [
            "id",
            "user_id",
            "trigger_source",
            "crisis_score",
            "status",
            "created_at",
            "handled_by",
            "handled_action",
        ]
        rows = list(reader)
        assert len(rows) == 3

        # 校验 user_id 已脱敏 (保留前 2 位 + ****)
        for row in rows:
            assert row[1].endswith("****")

        # 校验 handled_by 已脱敏: 已处理事件应非空且以 **** 结尾
        handled_rows = [row for row in rows if row[6]]
        assert len(handled_rows) == 1
        assert handled_rows[0][6].endswith("****")

    async def test_export_filters_by_date_range(
        self,
        service: CrisisExportService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-EXP-019: 按时间范围过滤 - 仅返回区间内事件 (L72-77 查询逻辑)."""
        # 100 天前的事件 - 应被排除
        old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=100)
        old_event = CrisisEvent(
            user_id=1,
            trigger_source="keyword",
            crisis_score=50.0,
            status="detected",
            created_at=old_time,
        )
        # 今日事件 - 应被包含
        recent_event = CrisisEvent(
            user_id=1,
            trigger_source="keyword",
            crisis_score=60.0,
            status="detected",
        )
        db_session.add_all([old_event, recent_event])
        await db_session.commit()

        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
        csv_content, _ = await service.export_crisis_events(start, end)

        reader = csv.reader(io.StringIO(csv_content))
        next(reader)  # skip header
        rows = list(reader)
        assert len(rows) == 1
        # 仅保留今日事件
        assert rows[0][4] == "detected"

    async def test_export_csv_injection_sanitized(
        self,
        service: CrisisExportService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-EXP-020: 危险 trigger_source / handled_action 被 CSV 注入防护转义.

        覆盖 L93-106 写入路径中 _sanitize_csv_cell 的实际调用.
        trigger_source 列 String(20), 用短 payload (=cmd) 验证导出路径生效.
        """
        evil_event = CrisisEvent(
            user_id=1,
            trigger_source="=cmd",
            crisis_score=80.0,
            status="detected",
            handled_action="=HYPERLINK('evil')",
        )
        db_session.add(evil_event)
        await db_session.commit()

        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
        csv_content, _ = await service.export_crisis_events(start, end)

        reader = csv.reader(io.StringIO(csv_content))
        next(reader)  # skip header
        rows = list(reader)
        assert len(rows) == 1

        # trigger_source 应被转义为 '=cmd (前缀单引号)
        assert rows[0][2] == "'=cmd"
        # handled_action 应被转义为 '=HYPERLINK('evil')
        assert rows[0][7] == "'=HYPERLINK('evil')"

    async def test_export_null_fields_handled(
        self,
        service: CrisisExportService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-EXP-021: crisis_score / handled_by / handled_action 为空时正确处理.

        覆盖 L99-106 空字段兜底分支 (event.created_at if/else, handled_by if/else, handled_action or).
        """
        event = CrisisEvent(
            user_id=1,
            trigger_source="keyword",
            crisis_score=None,
            status="detected",
            handled_by=None,
            handled_action=None,
        )
        db_session.add(event)
        await db_session.commit()

        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
        csv_content, _ = await service.export_crisis_events(start, end)

        reader = csv.reader(io.StringIO(csv_content))
        next(reader)  # skip header
        rows = list(reader)
        assert len(rows) == 1
        # crisis_score / handled_by / handled_action 应为空字符串
        assert rows[0][3] == ""  # crisis_score (None -> "")
        assert rows[0][6] == ""  # handled_by (None -> if 分支 -> "")
        assert rows[0][7] == ""  # handled_action (None -> or "")

    async def test_export_filename_uses_input_dates(self, service: CrisisExportService):
        """TC-COV-EXP-022: 文件名严格使用入参 start_date / end_date (L112)."""
        csv_content, filename = await service.export_crisis_events(
            date(2023, 5, 10), date(2023, 12, 31)
        )
        assert filename == "crisis_events_20230510_20231231.csv"
