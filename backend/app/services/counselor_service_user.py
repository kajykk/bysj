from __future__ import annotations

from sqlalchemy import func, select

from app.core.contracts import DEFAULT_TENANT_ID, normalize_risk_level
from app.core.states import BindingStatus
from app.core.tenant_query import tenant_scoped_filter, tenant_scoped_query
from app.models.assessment import StructuredAssessment
from app.models.intervention import InterventionPlan
from app.models.risk import RiskAssessment
from app.models.user import User, UserCounselorBinding


class UserMixin:
    """咨询师用户管理相关方法 Mixin。

    包含:
    - `list_my_users`: 列出当前咨询师绑定的用户 (支持 risk_level 过滤，含 PERF-P2-002 优化)
    - `get_user_detail`: 获取绑定用户详情 (含最新风险评估，PII 越权暴露修复)

    依赖主类 CounselorService 提供 `self.db`。
    """

    async def list_my_users(
        self,
        counselor_id: int,
        page: int,
        page_size: int,
        risk_level: int | None = None,
        tenant_id: int | None = None,
    ) -> dict:
        """列出当前咨询师绑定的用户。

        AUDIT-2026-10-06 (P0-1): 接入 ``tenant_scoped_query`` —— 原实现只按
        counselor_id 过滤，**没有任何租户条件**。路由层的 ``require_role("counselor")``
        已保证"咨询师租户 == 请求租户"，但绑定关系本身不带 tenant_id；
        一旦出现跨租户绑定（历史数据 / 绑定接口漏校验），咨询师就能看到
        其他租户用户的 username / nickname / 风险等级。
        这里加数据层纵深防御。
        """
        offset = (page - 1) * page_size
        effective_tenant = tenant_id if tenant_id is not None else DEFAULT_TENANT_ID
        base_conditions = [
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
            # 租户隔离（数据层）：咨询师只能看到本租户的用户
            tenant_scoped_filter(User, effective_tenant),
        ]

        # 按风险等级过滤：筛选最新风险评估匹配指定等级的用户
        # PERF-P2-002: 使用 is_latest 标志替代 GROUP BY + max(created_at) 子查询
        if risk_level is not None:
            matching_user_ids = (
                select(RiskAssessment.user_id)
                .where(
                    RiskAssessment.is_latest.is_(True),
                    RiskAssessment.risk_level == risk_level,
                )
                .scalar_subquery()
            )
            base_conditions.append(User.id.in_(matching_user_ids))

        stmt = (
            tenant_scoped_query(User, effective_tenant)
            .join(UserCounselorBinding, UserCounselorBinding.user_id == User.id)
            .where(*base_conditions)
            .order_by(User.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        count_stmt = (
            select(func.count(User.id))
            .join(UserCounselorBinding, UserCounselorBinding.user_id == User.id)
            .where(*base_conditions)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        user_ids = [u.id for u in rows]
        risk_map: dict[int, RiskAssessment] = {}
        if user_ids:
            # PERF-P2-002: 使用 is_latest 标志替代 GROUP BY + max(created_at) 子查询
            risk_stmt = (
                select(RiskAssessment)
                .where(
                    RiskAssessment.user_id.in_(user_ids),
                    RiskAssessment.is_latest.is_(True),
                )
            )
            risk_rows = (await self.db.execute(risk_stmt)).scalars().all()
            risk_map = {r.user_id: r for r in risk_rows}

        items = [
            {
                "id": u.id,
                "username": u.username,
                "status": u.status,
                "latest_risk_level": (
                    risk_map[u.id].risk_level if u.id in risk_map else None
                ),
                "latest_risk_score": (
                    risk_map[u.id].risk_score if u.id in risk_map else None
                ),
                "latest_risk_label": (
                    normalize_risk_level(risk_map[u.id].risk_level)
                    if u.id in risk_map
                    else "none"
                ),
                "risk_level": risk_map[u.id].risk_level if u.id in risk_map else 0,
                "risk_score": risk_map[u.id].risk_score if u.id in risk_map else None,
            }
            for u in rows
        ]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def get_user_detail(self, counselor_id: int, user_id: int) -> dict | None:
        binding_stmt = select(UserCounselorBinding).where(
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        binding = (await self.db.execute(binding_stmt)).scalar_one_or_none()
        if not binding:
            return None
        user = await self.db.get(User, user_id)
        if not user:
            return None
        # PERF-P2-002: 使用 is_latest 标志替代 ORDER BY created_at DESC LIMIT 1
        latest_risk_stmt = (
            select(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id,
                RiskAssessment.is_latest.is_(True),
            )
            .limit(1)
        )
        latest_risk = (await self.db.execute(latest_risk_stmt)).scalar_one_or_none()
        # UX-P3-02 修复：返回风险历史/评估/干预记录，支撑咨询师用户详情时间线视图
        risk_history_stmt = (
            select(
                RiskAssessment.id,
                RiskAssessment.risk_level,
                RiskAssessment.risk_score,
                RiskAssessment.created_at,
            )
            .where(RiskAssessment.user_id == user_id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(100)
        )
        risk_history = [
            {
                "id": row.id,
                "risk_level": row.risk_level,
                "risk_score": row.risk_score,
                "created_at": row.created_at.isoformat(sep=" ") if row.created_at else None,
            }
            for row in (await self.db.execute(risk_history_stmt)).all()
        ]
        assessments_stmt = (
            select(StructuredAssessment)
            .where(StructuredAssessment.user_id == user_id)
            .order_by(StructuredAssessment.created_at.desc())
            .limit(100)
        )
        assessments = [
            {
                "id": row.id,
                "type": row.assessment_type,
                "score": row.score,
                "created_at": row.created_at.isoformat(sep=" ") if row.created_at else None,
            }
            for row in (await self.db.execute(assessments_stmt)).scalars().all()
        ]
        interventions_stmt = (
            select(InterventionPlan)
            .where(InterventionPlan.user_id == user_id)
            .order_by(InterventionPlan.created_at.desc())
            .limit(100)
        )
        interventions = [
            {
                "id": row.id,
                "type": row.plan_name,
                "status": row.status,
                "created_at": row.created_at.isoformat(sep=" ") if row.created_at else None,
            }
            for row in (await self.db.execute(interventions_stmt)).scalars().all()
        ]
        return {
            "id": user.id,
            "username": user.username,
            "nickname": getattr(user, "nickname", None),
            # 修复：咨询师不需要用户 email（PII 越权暴露），仅管理员可获取
            "status": user.status,
            "latest_risk_level": latest_risk.risk_level if latest_risk else None,
            "latest_risk_score": latest_risk.risk_score if latest_risk else None,
            "latest_risk_label": (
                normalize_risk_level(latest_risk.risk_level) if latest_risk else "none"
            ),
            "risk_level": latest_risk.risk_level if latest_risk else 0,
            "risk_score": latest_risk.risk_score if latest_risk else None,
            "risk_history": risk_history,
            "assessments": assessments,
            "interventions": interventions,
        }
