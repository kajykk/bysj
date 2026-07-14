from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.admin import OperationLog

if TYPE_CHECKING:
    pass


class LogMixin:
    """操作日志与合规审计相关方法 Mixin。

    包含:
    - `_apply_log_filters` / `_query_logs` / `_log_item` 公共辅助方法
      (L-Svc-7 修复: 抽取 list_operation_logs / list_audit_logs 的公共逻辑)
    - `list_operation_logs`: 操作日志分页查询
    - `export_operation_logs`: 操作日志全量导出 (CSV)
    - `list_audit_logs`: 合规审计日志查询 (含 action_type 分组统计与 retention 信息)

    依赖主类 AdminService 提供 `self.db`。
    """

    @staticmethod
    def _apply_log_filters(stmt, filters: dict):
        """L-Svc-7 修复：将公共过滤条件应用到任意日志查询语句。

        支持的 filters 键：action_types(list)、operator_role、target_type、start_time、end_time。
        """
        action_types = filters.get("action_types")
        if action_types:
            stmt = stmt.where(OperationLog.action_type.in_(action_types))
        if filters.get("operator_role"):
            stmt = stmt.where(OperationLog.operator_role == filters["operator_role"])
        if filters.get("target_type"):
            stmt = stmt.where(OperationLog.target_type == filters["target_type"])
        if filters.get("start_time"):
            stmt = stmt.where(OperationLog.created_at >= filters["start_time"])
        if filters.get("end_time"):
            stmt = stmt.where(OperationLog.created_at <= filters["end_time"])
        return stmt

    async def _query_logs(
        self, filters: dict, page: int, page_size: int
    ) -> tuple[list[OperationLog], int]:
        """L-Svc-7 修复：抽取 list_operation_logs/list_audit_logs 公共的过滤+分页+计数逻辑。"""
        offset = (page - 1) * page_size
        stmt = self._apply_log_filters(select(OperationLog), filters)
        count_stmt = self._apply_log_filters(
            select(func.count()).select_from(OperationLog), filters
        )
        stmt = (
            stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()
        return rows, total

    @staticmethod
    def _log_item(r: OperationLog) -> dict:
        """L-Svc-7 修复：抽取日志条目序列化，供 list_operation_logs/list_audit_logs 复用。"""
        return {
            "id": r.id,
            "operator_id": r.operator_id,
            "operator_role": r.operator_role,
            "action_type": r.action_type,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "detail": r.detail,
            "ip_address": r.ip_address,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    async def list_operation_logs(
        self,
        page: int,
        page_size: int,
        action_type: str | None = None,
        operator_role: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        # L-Svc-7 修复：抽取公共过滤/分页逻辑至 _query_logs，避免与 list_audit_logs 重复
        filters = {
            "action_types": [action_type] if action_type else None,
            "operator_role": operator_role,
            "target_type": None,
            "start_time": start_time,
            "end_time": end_time,
        }
        rows, total = await self._query_logs(filters, page, page_size)
        return {
            "items": [self._log_item(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def export_operation_logs(
        self,
        action_type: str | None = None,
        operator_role: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict]:
        """ISS-080: 导出全部筛选条件下的操作日志（不分页），供前端生成 CSV."""
        filters = {
            "action_types": [action_type] if action_type else None,
            "operator_role": operator_role,
            "target_type": None,
            "start_time": start_time,
            "end_time": end_time,
        }
        stmt = self._apply_log_filters(select(OperationLog), filters)
        stmt = stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._log_item(r) for r in rows]

    async def list_audit_logs(
        self,
        page: int,
        page_size: int,
        action_types: list[str] | None = None,
        operator_role: str | None = None,
        target_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """v1.32: 合规审计日志查询.

        与 list_operation_logs 的差异:
        - 接受多 action_type 过滤 (合规审计需要批量类型)
        - 额外 target_type 过滤
        - 返回合规统计 (按 action_type 分组)
        - 包含 retention 信息

        适合合规审计员做 GDPR/等保 2.0 审查。
        """
        # L-Svc-7 修复：抽取公共过滤/分页逻辑至 _query_logs / _apply_log_filters
        filters = {
            "action_types": action_types,
            "operator_role": operator_role,
            "target_type": target_type,
            "start_time": start_time,
            "end_time": end_time,
        }
        rows, total = await self._query_logs(filters, page, page_size)

        # 合规统计 - 按 action_type 聚合
        breakdown_stmt = self._apply_log_filters(
            select(OperationLog.action_type, func.count().label("cnt")).group_by(
                OperationLog.action_type
            ),
            filters,
        )
        breakdown_rows = (await self.db.execute(breakdown_stmt)).all()
        action_breakdown = {row[0]: int(row[1]) for row in breakdown_rows}

        # 最早/最晚日志时间 - 用于 retention 检查
        range_stmt = self._apply_log_filters(
            select(
                func.min(OperationLog.created_at).label("earliest"),
                func.max(OperationLog.created_at).label("latest"),
            ),
            filters,
        )
        earliest, latest = (await self.db.execute(range_stmt)).one()

        return {
            "items": [self._log_item(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "compliance": {
                "action_breakdown": action_breakdown,
                "earliest_log": earliest.isoformat() if earliest else None,
                "latest_log": latest.isoformat() if latest else None,
                "retention_days": 90,  # 与 archive_logs 保持一致
            },
        }
