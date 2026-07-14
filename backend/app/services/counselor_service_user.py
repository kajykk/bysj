from __future__ import annotations

from sqlalchemy import func, select

from app.core.contracts import normalize_risk_level
from app.core.states import BindingStatus
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
    ) -> dict:
        offset = (page - 1) * page_size
        base_conditions = [
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
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
            select(User)
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
        }
