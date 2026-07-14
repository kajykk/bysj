from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update

from app.models.admin import OperationLog
from app.models.risk import RiskAssessment

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ArchiveMixin:
    """数据归档与 GDPR 合规相关方法 Mixin。

    包含:
    - `archive_old_logs`: 归档 (删除) 超期 OperationLog (C-04 / M-Svc-17 修复)
    - `archive_old_monitoring_logs`: 归档超期 MonitoringLog (RES-P2-005)
    - `mask_old_ips`: 掩码超期 OperationLog.ip_address (SEC-P2-008 GDPR 合规)
    - `archive_old_risk_assessments`: 归档超期 RiskAssessment 并维护 is_latest (PERF-P2-003)

    依赖主类 AdminService 提供 `self.db` 以及主模块的 `_mask_ip` 模块级函数
    (通过延迟导入规避循环导入)。
    """

    async def archive_old_logs(self, days: int = 90) -> int:
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
        # C-04 修复：使用 DELETE 语句的 rowcount 替代 COUNT 结果，避免 COUNT 与实际删除行数不一致
        result = await self.db.execute(
            delete(OperationLog).where(OperationLog.created_at < cutoff)
        )
        await self.db.commit()
        # M-Svc-17 修复：rowcount 语义在 SQLite 与 PostgreSQL 间存在差异
        # （PostgreSQL 返回实际删除行数；SQLite 的 aiosqlite 驱动可能返回 -1 或 0
        # 表示无法确定）。此处返回值仅作日志参考，不保证精确等于实际删除行数。
        deleted = result.rowcount or 0
        logger.info(
            "archive_old_logs: rowcount=%d (dialect-dependent, may be -1/0 on SQLite), "
            "cutoff=%s, days=%d",
            deleted,
            cutoff.isoformat(),
            days,
        )
        return deleted

    async def archive_old_monitoring_logs(self, days: int = 180) -> int:
        """RES-P2-005: 归档 (删除) 超过指定天数的 MonitoringLog 记录.

        监控日志 (inference/fallback/drift_alert 等) 增长迅速, 需独立归档策略.
        与 archive_old_logs (OperationLog, 90 天) 分离, 默认 180 天保留窗口
        (监控日志用于长期趋势分析, 保留更久).

        Args:
            days: 保留天数, 默认 180. 超过此天数的记录将被删除.

        Returns:
            删除的记录数 (rowcount, 方言相关, SQLite 可能返回 -1/0).
        """
        from app.models.monitoring import MonitoringLog

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
        result = await self.db.execute(
            delete(MonitoringLog).where(MonitoringLog.created_at < cutoff)
        )
        await self.db.commit()
        deleted = result.rowcount or 0
        logger.info(
            "archive_old_monitoring_logs: rowcount=%d (dialect-dependent), "
            "cutoff=%s, days=%d",
            deleted,
            cutoff.isoformat(),
            days,
        )
        return deleted

    async def mask_old_ips(self, days: int = 30) -> int:
        """SEC-P2-008: 掩码超过指定天数的 OperationLog.ip_address (GDPR 合规).

        GDPR 数据最小化原则: 30 天后将 ip_address 末段替换为 0 (IPv4) 或
        保留前两组 (IPv6), 保留网络段用于异常检测/审计, 同时无法识别个人.
        非标准格式 IP 替换为固定占位符. 90 天后由 archive_old_logs 删除整条记录.

        Args:
            days: 掩码阈值天数, 默认 30.

        Returns:
            已掩码的记录数.
        """
        # 延迟导入主模块的 _mask_ip 模块级函数，规避循环导入
        from app.services.admin_service import _mask_ip

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
        # 只查询超过阈值且 ip_address 非空的记录
        stmt = select(OperationLog.id, OperationLog.ip_address).where(
            OperationLog.created_at < cutoff,
            OperationLog.ip_address.isnot(None),
        )
        rows = (await self.db.execute(stmt)).all()

        masked_count = 0
        for row in rows:
            log_id, ip = row[0], row[1]
            if not ip:
                continue
            masked = _mask_ip(ip)
            if masked != ip:
                await self.db.execute(
                    update(OperationLog)
                    .where(OperationLog.id == log_id)
                    .values(ip_address=masked)
                )
                masked_count += 1

        await self.db.commit()
        logger.info(
            "mask_old_ips: masked=%d (cutoff=%s, days=%d)",
            masked_count,
            cutoff.isoformat(),
            days,
        )
        return masked_count

    async def archive_old_risk_assessments(self, days: int = 365) -> int:
        """PERF-P2-003: 归档 (删除) 超过指定天数的 RiskAssessment 记录.

        长期累积的 risk_assessments 表会拖慢查询 (counselor_service list_my_users
        / risk_service get_risk_trend 等). 本方法删除超过 days 天的记录,
        并维护 is_latest 标志位 (PERF-P2-002): 如果被删除的记录是某用户的
        is_latest=True, 则从剩余记录中重新标记一条最新的.

        WarningNotification.risk_assessment_id 外键 ondelete="SET NULL",
        删除 RiskAssessment 时相关告警记录的 risk_assessment_id 自动置 NULL
        (保留告警历史, 仅断开关联).

        Args:
            days: 归档阈值天数, 默认 365 (1 年).

        Returns:
            已删除的记录数 (dialect-dependent, SQLite 可能返回 -1/0).
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

        # 1. 查询将被删除的 is_latest=True 记录的 user_id 列表
        #    这些用户需要从剩余记录中重新标记 is_latest
        latest_to_delete = await self.db.execute(
            select(RiskAssessment.user_id)
            .where(
                RiskAssessment.created_at < cutoff,
                RiskAssessment.is_latest.is_(True),
            )
            .distinct()
        )
        affected_user_ids = [row[0] for row in latest_to_delete.all()]

        # 2. 对每个受影响的用户, 从剩余记录中找最新的并标记 is_latest=True
        if affected_user_ids:
            # 先清除这些用户的 is_latest 标志 (将被删除的记录)
            await self.db.execute(
                update(RiskAssessment)
                .where(
                    RiskAssessment.user_id.in_(affected_user_ids),
                    RiskAssessment.created_at < cutoff,
                    RiskAssessment.is_latest.is_(True),
                )
                .values(is_latest=False)
            )

            # 对每个用户, 找剩余记录中 created_at 最大的, 标记 is_latest=True
            for user_id in affected_user_ids:
                latest_remaining = await self.db.execute(
                    select(RiskAssessment.id)
                    .where(
                        RiskAssessment.user_id == user_id,
                        RiskAssessment.created_at >= cutoff,
                    )
                    .order_by(RiskAssessment.created_at.desc())
                    .limit(1)
                )
                new_latest_id = latest_remaining.scalar_one_or_none()
                if new_latest_id is not None:
                    await self.db.execute(
                        update(RiskAssessment)
                        .where(RiskAssessment.id == new_latest_id)
                        .values(is_latest=True)
                    )

        # 3. 删除超过阈值的记录
        result = await self.db.execute(
            delete(RiskAssessment).where(RiskAssessment.created_at < cutoff)
        )
        await self.db.commit()

        deleted = result.rowcount or 0
        logger.info(
            "archive_old_risk_assessments: deleted=%d (dialect-dependent), "
            "cutoff=%s, days=%d, affected_is_latest_users=%d",
            deleted,
            cutoff.isoformat(),
            days,
            len(affected_user_ids),
        )
        return deleted
