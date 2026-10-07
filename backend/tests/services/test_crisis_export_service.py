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


# ═══════════════════════════════════════════════════════════════════════
# 租户范围（AUDIT-2026-10-08）
#
# 与 P1-3/P1-4/P1-5 那三处不同：本端点的默认跨租户是**有意设计** —— 它受
# ``require_platform_admin()`` 保护（用户须属 DEFAULT_TENANT_ID，租户 B 的
# admin 被 403 拦住），平台管理员需要跨租户危机总览做升级处置。
# 因此这里不测「默认必须单租户」，而测两件事：
#   1. 默认仍是全量（防止有人误把平台能力改窄）
#   2. 传入 tenant_id 时确实收窄（新增能力真的生效）
# ═══════════════════════════════════════════════════════════════════════


class TestExportTenantScope:
    """导出范围的默认全量 + 按需收窄。"""

    @staticmethod
    def _rows(csv_content: str) -> list[list[str]]:
        """剥掉表头，返回数据行。"""
        reader = csv.reader(io.StringIO(csv_content))
        return list(reader)[1:]

    async def test_default_exports_all_tenants(self, service, db_session, seeded_user_id):
        """省略 tenant_id 时导出全部租户 —— 平台监管的有意设计，不得被改窄。"""
        from app.core.pii_crypto import compute_blind_index
        from app.core.security import get_password_hash
        from app.models.user import User

        # 造一个租户 2 的用户 + 其危机事件
        pwd = get_password_hash("testpass123")
        email = "t2@test.com"
        other = User(
            id=100,
            username="t2_user",
            email=email,
            email_hash=compute_blind_index(email, "email"),
            password_hash=pwd,
            role="user",
            status="active",
            tenant_id=2,
        )
        db_session.add(other)
        await db_session.flush()
        db_session.add(
            CrisisEvent(
                user_id=100,
                trigger_source="keyword",
                crisis_score=60.0,
                status="detected",
            )
        )
        await db_session.commit()

        csv_content, _ = await service.export_crisis_events(date(2020, 1, 1), date(2099, 1, 1))
        rows = self._rows(csv_content)
        # 租户 1（seeded_user_id=1 及 user 2）+ 租户 2（user 100）都在
        masked = {r[1] for r in rows}
        assert "10****" in masked, f"默认导出应含租户 2 的用户，实际 {masked}"

    async def test_tenant_id_narrows_scope(self, service, db_session, seeded_user_id):
        """传入 tenant_id 时只导出该租户 —— 新增的收窄能力必须真的生效。"""
        from app.core.pii_crypto import compute_blind_index
        from app.core.security import get_password_hash
        from app.models.user import User

        pwd = get_password_hash("testpass123")
        email = "t2b@test.com"
        db_session.add(
            User(
                id=101,
                username="t2_user_b",
                email=email,
                email_hash=compute_blind_index(email, "email"),
                password_hash=pwd,
                role="user",
                status="active",
                tenant_id=2,
            )
        )
        await db_session.flush()
        db_session.add(
            CrisisEvent(
                user_id=101,
                trigger_source="keyword",
                crisis_score=55.0,
                status="detected",
            )
        )
        await db_session.commit()

        # 收窄到租户 1
        csv1, _ = await service.export_crisis_events(
            date(2020, 1, 1), date(2099, 1, 1), tenant_id=1
        )
        masked1 = {r[1] for r in self._rows(csv1)}
        assert "10****" not in masked1, f"收窄到租户 1 后仍含租户 2 数据：{masked1}"

        # 收窄到租户 2
        csv2, _ = await service.export_crisis_events(
            date(2020, 1, 1), date(2099, 1, 1), tenant_id=2
        )
        masked2 = {r[1] for r in self._rows(csv2)}
        assert "10****" in masked2, f"收窄到租户 2 应含其数据：{masked2}"

    async def test_backward_compatible_two_arg_call(self, service, seeded_crisis_events):
        """旧调用方用两个位置参数调用仍然可用（tenant_id 默认 None）。"""
        csv_content, filename = await service.export_crisis_events(
            date(2020, 1, 1), date(2099, 1, 1)
        )
        assert csv_content
        assert filename.startswith("crisis_events_")
