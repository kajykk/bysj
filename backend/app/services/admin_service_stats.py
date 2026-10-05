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
        # H-Svc-2 修复：DateTime 列为 naive，统一生成 naive UTC datetime 进行比较，避免 aware/naive 混用抛 TypeError
        today = datetime.now(UTC).replace(tzinfo=None).date()
        today_start = datetime.combine(today, datetime.min.time())
        # H-9 修复：补充 yesterday_* 字段，供前端 AdminDashboard 计算环比趋势。
        # yesterday_start 为昨日 00:00 UTC，用于计算昨日增量与累计快照。
        yesterday_start = datetime.combine(
            today - timedelta(days=1), datetime.min.time()
        )

        # AUDIT-2026-10-05: 12 条串行 count 合并为 1 条 SQL。
        # 原实现每个指标一次独立 count + 一次往返 = 12 次串行 DB 往返,
        # 管理仪表盘首屏 1.2s 几乎全部耗在这里。改为标量子查询一次性取回,
        # 语义完全等价(PG 对无 where 的 count 走全表扫描, 合并后一次扫描
        # 即可算出全部计数, 比 12 次全表扫描快一个数量级)。
        stmt = select(
            # 基础计数
            select(func.count())
            .select_from(User)
            .scalar_subquery()
            .label("total_users"),
            select(func.count())
            .select_from(User)
            .where(User.role == "counselor")
            .scalar_subquery()
            .label("total_counselors"),
            # 今日告警
            select(func.count())
            .select_from(WarningNotification)
            .where(WarningNotification.created_at >= today_start)
            .scalar_subquery()
            .label("today_warnings"),
            select(func.count())
            .select_from(WarningNotification)
            .where(
                WarningNotification.created_at >= today_start,
                WarningNotification.is_handled.is_(False),
            )
            .scalar_subquery()
            .label("today_unhandled_warnings"),
            # 评估与高风险
            select(func.count())
            .select_from(RiskAssessment)
            .scalar_subquery()
            .label("total_assessments"),
            # H-15 修复：high_risk_users 应统计高风险用户数（DISTINCT user_id），而非评估记录数
            select(func.count(func.distinct(RiskAssessment.user_id)))
            .where(RiskAssessment.risk_level >= 3)
            .scalar_subquery()
            .label("high_risk_users"),
            # 模板
            select(func.count())
            .select_from(InterventionTemplate)
            .scalar_subquery()
            .label("total_templates"),
            select(func.count())
            .select_from(InterventionTemplate)
            .where(InterventionTemplate.status == "active")
            .scalar_subquery()
            .label("active_templates"),
            # H-9 修复：yesterday_* 快照
            select(func.count())
            .select_from(User)
            .where(User.created_at < today_start)
            .scalar_subquery()
            .label("yesterday_users"),
            select(func.count())
            .select_from(WarningNotification)
            .where(
                WarningNotification.created_at >= yesterday_start,
                WarningNotification.created_at < today_start,
            )
            .scalar_subquery()
            .label("yesterday_warnings"),
            select(func.count())
            .select_from(RiskAssessment)
            .where(RiskAssessment.created_at < today_start)
            .scalar_subquery()
            .label("yesterday_assessments"),
            select(func.count())
            .select_from(InterventionTemplate)
            .where(
                InterventionTemplate.status == "active",
                InterventionTemplate.created_at < today_start,
            )
            .scalar_subquery()
            .label("yesterday_templates"),
        )
        row = (await self.db.execute(stmt)).one()
        (
            total_users,
            total_counselors,
            today_warnings,
            today_unhandled_warnings,
            total_assessments,
            high_risk_users,
            total_templates,
            active_templates,
            yesterday_users,
            yesterday_warnings,
            yesterday_assessments,
            yesterday_templates,
        ) = row
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
