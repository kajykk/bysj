from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, time, timezone
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_query import tenant_scoped_filter
from app.models.review import CrisisEvent
from app.models.user import User

logger = logging.getLogger(__name__)

# P1-SEC-029 修复：CSV 公式注入危险前缀字符
# Excel/LibreOffice 会将以这些字符开头的单元格解释为公式
_CSV_DANGEROUS_PREFIXES = ("=", "+", "@", "\t", "\r", "\n")


def _sanitize_csv_cell(value: object) -> str:
    """P1-SEC-029 修复：转义 CSV 公式注入危险字符。

    当单元格值以 ``=``、``+``、``@``、``\\t``、``\\r``、``\\n`` 开头时，
    Excel/LibreOffice 会将其解释为公式，可能导致公式注入攻击
    （如 ``=HYPERLINK(...)``、``=cmd|'/c calc'!A1``）。
    通过在前面添加单引号 ``'`` 强制 Excel 将其作为文本处理。

    对于 ``-`` 开头的值，仅当其不是合法数字时才转义（避免影响负数导出）。
    """
    if value is None:
        return ""
    text = str(value)
    if not text:
        return text
    if text.startswith(_CSV_DANGEROUS_PREFIXES):
        return "'" + text
    if text.startswith("-"):
        try:
            float(text)
        except ValueError:
            return "'" + text
    return text


class CrisisExportService:
    """危机事件导出服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def build_filename(self, start_date: date, end_date: date) -> str:
        return f"crisis_events_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"

    async def iter_export_crisis_csv(
        self,
        start_date: date,
        end_date: date,
        tenant_id: int | None = None,
    ) -> AsyncIterator[str]:
        """ISS-110: 逐行生成 CSV 文本 (每行单独 yield), 供 StreamingResponse 流式输出.

        内存占用 O(1): 每行写入独立 io.StringIO 后立即 yield, 不累积全量字符串.

        Args:
            start_date / end_date: 导出日期范围
            tenant_id: 为 ``None``（默认）时**导出全部租户**；给定则只导出该租户。

        ⚠ 默认跨租户是**有意设计，不是漏过滤**（AUDIT-2026-10-08 澄清）：
        本服务的唯一调用方 ``GET /api/v1/admin/crisis-events/export`` 受
        ``require_platform_admin()`` 保护，该依赖在「角色 + 请求租户一致」之上
        再限定**用户必须属于 ``DEFAULT_TENANT_ID``**（见
        ``app/core/tenant_context.py:352``）。租户 B 的 admin 根本到不了这里
        （``tests/api/test_cross_tenant_security.py::TestPlatformAdminSplit``
        已断言 403）。平台管理员需要跨租户的危机总览来做升级处置，把这里改成
        强制单租户会打断该用例。

        因此正确处置不是「加死过滤」，而是把范围**显式化并可按需收窄**：
        ``tenant_id=None`` 表示平台管理员有意选择全量，且该选择会被写进审计日志。
        """
        # 查询数据
        # M-4 修复：使用 aware UTC datetime，避免与 aware 列比较时抛 TypeError 或时区偏移
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

        # M-Svc-1 修复：使用 yield_per(1000) 流式读取，避免大数据量全量加载到内存
        # H-Cov-1 修复：async session 下 yield_per 需要 stream() 而非 execute()，否则抛 AsyncMethodRequired
        # P2-31：``tenant_id=None``（默认）即"平台管理员有意全量导出"——该选择由
        # require_platform_admin 把关并写入审计日志（见方法 docstring）。用语句级
        # 豁免标记把"有意跨租户"显式化；传了 tenant_id 时下方 JOIN 提供锚点，
        # 两条路径都过执行层闸门（app/core/tenant_guard）。
        stmt = (
            select(CrisisEvent)
            .where(CrisisEvent.created_at >= start_dt)
            .where(CrisisEvent.created_at <= end_dt)
            .order_by(CrisisEvent.created_at.desc())
            .execution_options(
                yield_per=1000,
                tenant_exempt="platform_admin_crisis_export",
            )
        )

        # AUDIT-2026-10-08：按需收窄到单个租户。``crisis_events`` 表本身没有
        # tenant_id 列，租户归属只能沿 user_id 关联 users.tenant_id 推导
        # （与 CrisisEventService.get_crisis_events 同一套做法）。
        if tenant_id is not None:
            stmt = stmt.join(User, User.id == CrisisEvent.user_id).where(
                tenant_scoped_filter(User, tenant_id)
            )

        result = await self.db.stream(stmt)

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def _emit(row: list) -> str:
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(row)
            return buffer.getvalue()

        # 写入表头
        yield _emit(
            [
                "id",
                "user_id",
                "trigger_source",
                "crisis_score",
                "status",
                "created_at",
                "handled_by",
                "handled_action",
            ]
        )

        # 写入数据（脱敏 + P1-SEC-029 CSV 注入防护）- M-Svc-1 修复：流式遍历，避免 .all() 全量加载
        event_count = 0
        async for event in result.scalars():
            yield _emit(
                [
                    _sanitize_csv_cell(event.id),
                    _sanitize_csv_cell(self._mask_user_id(event.user_id)),
                    _sanitize_csv_cell(event.trigger_source),
                    _sanitize_csv_cell(event.crisis_score),
                    _sanitize_csv_cell(event.status),
                    _sanitize_csv_cell(
                        event.created_at.isoformat() if event.created_at else ""
                    ),
                    _sanitize_csv_cell(
                        self._mask_user_id(event.handled_by) if event.handled_by else ""
                    ),
                    _sanitize_csv_cell(event.handled_action or ""),
                ]
            )
            event_count += 1

        # AUDIT-2026-10-08：把导出的租户范围写进日志。批量导出危机数据属高敏操作，
        # 「导了哪些租户」必须可回溯 —— 事后无法从 CSV 内容反推（user_id 已脱敏）。
        logger.info(
            "Exported %d crisis events to %s (tenant_scope=%s)",
            event_count,
            self.build_filename(start_date, end_date),
            "all_tenants" if tenant_id is None else f"tenant:{tenant_id}",
        )

    async def export_crisis_events(
        self,
        start_date: date,
        end_date: date,
        tenant_id: int | None = None,
    ) -> tuple[str, str]:
        """导出危机事件为 CSV 格式 (聚合全量字符串, 兼容旧调用方).

        Args:
            start_date: 开始日期
            end_date: 结束日期
            tenant_id: 见 :meth:`iter_export_crisis_csv` —— ``None`` 表示全部租户

        Returns:
            (csv_content, filename) 元组
        """
        chunks: list[str] = []
        async for chunk in self.iter_export_crisis_csv(start_date, end_date, tenant_id):
            chunks.append(chunk)

        return "".join(chunks), self.build_filename(start_date, end_date)

    @staticmethod
    def _mask_user_id(user_id: int) -> str:
        """脱敏用户 ID：保留前 2 位，其余用 **** 代替。"""
        user_id_str = str(user_id)
        if len(user_id_str) <= 2:
            return user_id_str + "****"
        return user_id_str[:2] + "****"
