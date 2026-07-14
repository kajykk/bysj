from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.intervention import InterventionTemplate
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User

if TYPE_CHECKING:
    pass


class StatsMixin:
    """管理后台统计仪表盘相关方法 Mixin。

    包含 `get_stats` 方法，聚合返回管理仪表盘所需的各项指标:
    用户/咨询师数、今日告警、高风险用户、模板数及昨日环比快照 (H-9 修复)。

    依赖主类 AdminService 提供 `self.db`。
    """

    async def get_stats(self) -> dict:
        total_users = (
            await self.db.execute(select(func.count()).select_from(User))
        ).scalar_one()
        total_counselors = (
            await self.db.execute(
                select(func.count()).select_from(User).where(User.role == "counselor")
            )
        ).scalar_one()
        # H-Svc-2 修复：DateTime 列为 naive，统一生成 naive UTC datetime 进行比较，避免 aware/naive 混用抛 TypeError
        today = datetime.now(UTC).replace(tzinfo=None).date()
        today_start = datetime.combine(today, datetime.min.time())
        # H-9 修复：补充 yesterday_* 字段，供前端 AdminDashboard 计算环比趋势。
        # yesterday_start 为昨日 00:00 UTC，用于计算昨日增量与累计快照。
        yesterday_start = datetime.combine(
            today - timedelta(days=1), datetime.min.time()
        )
        today_warning_stmt = (
            select(func.count())
            .select_from(WarningNotification)
            .where(WarningNotification.created_at >= today_start)
        )
        today_warnings = (await self.db.execute(today_warning_stmt)).scalar_one()
        today_unhandled_warnings = (
            await self.db.execute(
                select(func.count())
                .select_from(WarningNotification)
                .where(
                    WarningNotification.created_at >= today_start,
                    WarningNotification.is_handled.is_(False),
                )
            )
        ).scalar_one()
        total_assessments = (
            await self.db.execute(select(func.count()).select_from(RiskAssessment))
        ).scalar_one()
        # H-15 修复：high_risk_users 应统计高风险用户数（DISTINCT user_id），而非评估记录数
        high_risk_users = (
            await self.db.execute(
                select(func.count(func.distinct(RiskAssessment.user_id))).where(
                    RiskAssessment.risk_level >= 3
                )
            )
        ).scalar_one()
        total_templates = (
            await self.db.execute(
                select(func.count()).select_from(InterventionTemplate)
            )
        ).scalar_one()
        active_templates = (
            await self.db.execute(
                select(func.count())
                .select_from(InterventionTemplate)
                .where(InterventionTemplate.status == "active")
            )
        ).scalar_one()
        # H-9 修复：计算 yesterday_* 快照
        # yesterday_users / yesterday_assessments：截至昨日结束的累计值（created_at < today_start）
        # yesterday_warnings：昨日单日增量（yesterday_start <= created_at < today_start）
        # yesterday_templates：截至昨日结束的活跃模板数（无状态变更历史，以 created_at 近似）
        yesterday_users = (
            await self.db.execute(
                select(func.count())
                .select_from(User)
                .where(User.created_at < today_start)
            )
        ).scalar_one()
        yesterday_warnings = (
            await self.db.execute(
                select(func.count())
                .select_from(WarningNotification)
                .where(
                    WarningNotification.created_at >= yesterday_start,
                    WarningNotification.created_at < today_start,
                )
            )
        ).scalar_one()
        yesterday_assessments = (
            await self.db.execute(
                select(func.count())
                .select_from(RiskAssessment)
                .where(RiskAssessment.created_at < today_start)
            )
        ).scalar_one()
        yesterday_templates = (
            await self.db.execute(
                select(func.count())
                .select_from(InterventionTemplate)
                .where(
                    InterventionTemplate.status == "active",
                    InterventionTemplate.created_at < today_start,
                )
            )
        ).scalar_one()
        return {
            "total_users": total_users,
            "total_counselors": total_counselors,
            "today_warnings": today_warnings,
            "today_unhandled_warnings": today_unhandled_warnings,
            "total_assessments": total_assessments,
            "high_risk_users": high_risk_users,
            "total_templates": total_templates,
            "active_templates": active_templates,
            "yesterday_users": yesterday_users,
            "yesterday_warnings": yesterday_warnings,
            "yesterday_assessments": yesterday_assessments,
            "yesterday_templates": yesterday_templates,
        }
