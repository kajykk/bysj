from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import CrisisEvent

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

    async def export_crisis_events(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[str, str]:
        """导出危机事件为 CSV 格式。

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            (csv_content, filename) 元组
        """
        # 查询数据
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        stmt = (
            select(CrisisEvent)
            .where(CrisisEvent.created_at >= start_dt)
            .where(CrisisEvent.created_at <= end_dt)
            .order_by(CrisisEvent.created_at.desc())
        )
        result = await self.db.execute(stmt)
        events = result.scalars().all()

        # 生成 CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow([
            "id", "user_id", "trigger_source", "crisis_score",
            "status", "created_at", "handled_by", "handled_action",
        ])

        # 写入数据（脱敏 + P1-SEC-029 CSV 注入防护）
        for event in events:
            writer.writerow([
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
            ])

        csv_content = output.getvalue()
        output.close()

        filename = f"crisis_events_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
        logger.info("Exported %d crisis events to %s", len(events), filename)
        return csv_content, filename

    @staticmethod
    def _mask_user_id(user_id: int) -> str:
        """脱敏用户 ID：保留前 2 位，其余用 **** 代替。"""
        user_id_str = str(user_id)
        if len(user_id_str) <= 2:
            return user_id_str + "****"
        return user_id_str[:2] + "****"
