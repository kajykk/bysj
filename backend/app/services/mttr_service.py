"""STAB-P1-008: MTTR (Mean Time To Repair) 自动统计服务.

基于 OperationLog 表中 alert_fired / alert_resolved 配对计算故障恢复时长。

数据源:
- OperationLog.action_type == "alert_fired": 故障开始 (created_at 作为 starts_at)
- OperationLog.action_type == "alert_resolved": 故障恢复 (created_at 作为 resolved_at)
- 配对键: detail JSON 中的 fingerprint 字段

MTTR = Σ(resolved_at - starts_at) / N (已配对的告警)

设计要点:
- 跨 90 天窗口: 同时查询 operation_logs 和 alert_archives 两张表
- 按 severity 分组: critical/warning/info 分别统计
- 未配对告警: 单独统计 unresolved_count (告警 fired 但未 resolved)
- 时间窗口: 默认 24h, 可配置
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AlertArchive, OperationLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MttrStats:
    """MTTR 统计结果.

    Attributes:
        mttr_seconds: 平均恢复时长 (秒), 已配对告警的均值
        resolved_count: 已配对告警数 (有 fired + resolved)
        unresolved_count: 未配对告警数 (有 fired 但无 resolved)
        total_count: 总告警数 (fired + resolved)
        severity_breakdown: 按 severity 分组的统计 {severity: {mttr, resolved, unresolved}}
        window_hours: 统计窗口 (小时)
    """

    mttr_seconds: float
    resolved_count: int
    unresolved_count: int
    total_count: int
    severity_breakdown: dict[str, dict[str, float]]
    window_hours: int


class MttrService:
    """MTTR 自动统计服务.

    Usage:
        service = MttrService()
        stats = await service.compute_mttr(db_session, window_hours=24)
        # stats.mttr_seconds, stats.resolved_count, stats.unresolved_count
    """

    def __init__(self, window_hours: int = 24) -> None:
        self.window_hours = window_hours

    async def compute_mttr(
        self,
        db_session: AsyncSession,
        window_hours: int | None = None,
    ) -> MttrStats:
        """计算最近 window_hours 内的 MTTR 统计.

        Args:
            db_session: 异步数据库会话
            window_hours: 统计窗口 (小时), 默认使用实例配置

        Returns:
            MttrStats 统计结果
        """
        hours = window_hours or self.window_hours
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        since = now - timedelta(hours=hours)

        # 查询窗口内的所有 alert_fired / alert_resolved (含归档表)
        fired_entries = await self._query_alert_logs(
            db_session, action_type="alert_fired", since=since
        )
        resolved_entries = await self._query_alert_logs(
            db_session, action_type="alert_resolved", since=since
        )

        # 按 fingerprint 分组
        fired_by_fp = self._group_by_fingerprint(fired_entries)
        resolved_by_fp = self._group_by_fingerprint(resolved_entries)

        # 配对计算
        all_fingerprints = set(fired_by_fp.keys()) | set(resolved_by_fp.keys())
        severity_breakdown: dict[str, dict[str, float]] = {}
        total_mttr_seconds = 0.0
        resolved_count = 0
        unresolved_count = 0

        for fp in all_fingerprints:
            fired_list = fired_by_fp.get(fp, [])
            resolved_list = resolved_by_fp.get(fp, [])
            # 取最早的 fired 和最早的 resolved (同一 fingerprint 可能多次触发)
            if not fired_list:
                # 仅有 resolved (可能是窗口前 fired, 不参与 MTTR 计算)
                continue
            earliest_fired = fired_list[0]
            severity = earliest_fired["severity"]

            # 确保 severity_breakdown 有该 severity 的桶
            if severity not in severity_breakdown:
                severity_breakdown[severity] = {
                    "mttr_seconds": 0.0,
                    "resolved_count": 0,
                    "unresolved_count": 0,
                }
            bucket = severity_breakdown[severity]

            if resolved_list:
                earliest_resolved = resolved_list[0]
                mttr = (
                    earliest_resolved["created_at"] - earliest_fired["created_at"]
                ).total_seconds()
                # 仅计入正数 MTTR (避免窗口边界异常导致负值)
                if mttr >= 0:
                    total_mttr_seconds += mttr
                    resolved_count += 1
                    bucket["mttr_seconds"] += mttr
                    bucket["resolved_count"] += 1
            else:
                # 有 fired 但无 resolved (未恢复)
                unresolved_count += 1
                bucket["unresolved_count"] += 1

        # 计算平均 MTTR
        avg_mttr = total_mttr_seconds / resolved_count if resolved_count > 0 else 0.0

        # 计算各 severity 的平均 MTTR
        for severity, bucket in severity_breakdown.items():
            if bucket["resolved_count"] > 0:
                bucket["mttr_seconds"] = (
                    bucket["mttr_seconds"] / bucket["resolved_count"]
                )
            else:
                bucket["mttr_seconds"] = 0.0

        return MttrStats(
            mttr_seconds=avg_mttr,
            resolved_count=resolved_count,
            unresolved_count=unresolved_count,
            total_count=len(fired_entries) + len(resolved_entries),
            severity_breakdown=severity_breakdown,
            window_hours=hours,
        )

    async def _query_alert_logs(
        self,
        db_session: AsyncSession,
        action_type: str,
        since: datetime,
    ) -> list[dict[str, Any]]:
        """查询指定 action_type 的告警日志 (含归档表).

        Args:
            db_session: 异步数据库会话
            action_type: "alert_fired" 或 "alert_resolved"
            since: 起始时间

        Returns:
            list of {fingerprint, severity, created_at}
        """
        results: list[dict[str, Any]] = []

        # 1. 查询 operation_logs (最近 90 天内的日志, detail 是 JSON)
        stmt = select(OperationLog).where(
            OperationLog.action_type == action_type,
            OperationLog.created_at >= since,
        )
        rows = (await db_session.execute(stmt)).scalars().all()
        for row in rows:
            entry = self._parse_operation_log_row(row)
            if entry:
                results.append(entry)

        # 2. 查询 alert_archives (90 天前的归档日志, fingerprint 是独立字段)
        # 仅当 since 早于 90 天前时查询 (避免不必要的全表扫描)
        archive_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=90
        )
        if since < archive_cutoff:
            # AlertArchive 用 status 字段映射 action_type (firing→alert_fired, resolved→alert_resolved)
            status_filter = "firing" if action_type == "alert_fired" else "resolved"
            archive_stmt = select(AlertArchive).where(
                AlertArchive.status == status_filter,
                AlertArchive.original_created_at >= since,
            )
            archive_rows = (await db_session.execute(archive_stmt)).scalars().all()
            for row in archive_rows:
                # AlertArchive 字段: fingerprint, severity, original_created_at 都是独立字段
                if not row.fingerprint:
                    continue
                results.append(
                    {
                        "fingerprint": row.fingerprint,
                        "severity": row.severity,
                        "created_at": row.original_created_at,
                    }
                )

        return results

    @staticmethod
    def _parse_operation_log_row(row: OperationLog) -> dict[str, Any] | None:
        """解析 OperationLog 行, 从 detail JSON 提取 fingerprint/severity."""
        if not row.detail:
            return None
        try:
            detail = json.loads(row.detail)
        except (json.JSONDecodeError, TypeError):
            return None
        fingerprint = detail.get("fingerprint")
        severity = detail.get("severity", "unknown")
        if not fingerprint:
            return None
        return {
            "fingerprint": fingerprint,
            "severity": severity,
            "created_at": row.created_at,
        }

    @staticmethod
    def _group_by_fingerprint(
        entries: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """按 fingerprint 分组, 每组按 created_at 升序排序."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            fp = entry["fingerprint"]
            grouped.setdefault(fp, []).append(entry)
        # 每组按时间升序
        for fp, items in grouped.items():
            items.sort(key=lambda x: x["created_at"])
        return grouped


# 全局实例 (默认 24h 窗口)
mttr_service = MttrService(window_hours=24)
