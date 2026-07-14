"""GDPR 数据导出 Mixin.

实现用户的"数据可携权"(Article 20 - Data Portability).

包含:
- export_user_data: 一次性导出所有个人数据 (机器可读 JSON)
- fetch_user_account / fetch_profile: 流式导出基础方法
- iter_emergency_contacts / iter_counselor_bindings / iter_risk_assessments /
  iter_warnings / iter_crisis_events / iter_intervention_plans /
  iter_intervention_tasks / iter_operation_logs: 流式迭代器 (OFFSET 分页)

依赖主类 GDPRService 提供 `self.db`，以及主模块 gdpr_service 提供的模块级工具:
- `_safe_decrypt` / `_profile_to_dict` / `_contact_to_dict` / `_binding_to_dict` /
  `_risk_to_dict` / `_warning_to_dict` / `_crisis_to_dict` / `_plan_to_dict` /
  `_task_to_dict` / `_log_to_dict`: 模型序列化辅助函数

这些模块级工具通过延迟导入 (方法内 import) 访问, 避免与主模块形成循环导入。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.models.admin import OperationLog
from app.models.intervention import InterventionPlan, InterventionTask
from app.models.review import CrisisEvent
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import EmergencyContact, User, UserCounselorBinding, UserProfile


class ExportMixin:
    """GDPR 数据导出相关方法 Mixin。

    包含一次性导出与流式迭代器两类方法, 覆盖 Article 15 (Access) 与
    Article 20 (Portability) 的数据可携权要求。

    依赖主类 GDPRService 提供 `self.db`。
    """

    # ── 数据导出 (Article 20 - Data Portability) ──────────────────────

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """导出用户的所有个人数据 (机器可读 JSON).

        保留此方法用于小数据量场景或单测。生产环境优先使用流式方法（fetch_user_account + iter_*）。

        Returns:
            包含所有用户相关表的数据字典
        """
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import (
            _binding_to_dict,
            _contact_to_dict,
            _crisis_to_dict,
            _log_to_dict,
            _plan_to_dict,
            _profile_to_dict,
            _risk_to_dict,
            _safe_decrypt,
            _task_to_dict,
            _warning_to_dict,
        )

        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        # 1. 基础信息
        profile = (
            await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
        ).scalar_one_or_none()

        # 2. 紧急联系人
        contacts = (
            (
                await self.db.execute(
                    select(EmergencyContact).where(EmergencyContact.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        # 3. 咨询师绑定
        bindings = (
            (
                await self.db.execute(
                    select(UserCounselorBinding).where(
                        UserCounselorBinding.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )

        # 4. 风险评估
        risk_assessments = (
            (
                await self.db.execute(
                    select(RiskAssessment).where(RiskAssessment.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        # 5. 预警记录
        warnings = (
            (
                await self.db.execute(
                    select(WarningNotification).where(
                        WarningNotification.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )

        # 6. 危机事件
        crisis_events = (
            (
                await self.db.execute(
                    select(CrisisEvent).where(CrisisEvent.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        # 7. 干预计划
        plans = (
            (
                await self.db.execute(
                    select(InterventionPlan).where(InterventionPlan.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        plan_ids = [p.id for p in plans]
        tasks: list[Any] = []
        if plan_ids:
            tasks = (
                (
                    await self.db.execute(
                        select(InterventionTask).where(
                            InterventionTask.plan_id.in_(plan_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )

        # 8. 操作日志 (该用户的)
        op_logs = (
            (
                await self.db.execute(
                    select(OperationLog).where(OperationLog.operator_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        return {
            "export_metadata": {
                "export_id": str(uuid.uuid4()),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "gdpr_articles": ["Article 15 (Access)", "Article 20 (Portability)"],
                "format_version": "1.0",
            },
            "account": {
                "username": _safe_decrypt(user.username, "username"),
                "email": _safe_decrypt(user.email, "email"),
                "phone": _safe_decrypt(user.phone, "phone"),
                "role": user.role,
                "status": user.status,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": (
                    user.last_login_at.isoformat() if user.last_login_at else None
                ),
            },
            "profile": _profile_to_dict(profile) if profile else None,
            "emergency_contacts": [_contact_to_dict(c) for c in contacts],
            "counselor_bindings": [_binding_to_dict(b) for b in bindings],
            "risk_assessments": [_risk_to_dict(r) for r in risk_assessments],
            "warnings": [_warning_to_dict(w) for w in warnings],
            "crisis_events": [_crisis_to_dict(c) for c in crisis_events],
            "intervention_plans": [_plan_to_dict(p) for p in plans],
            "intervention_tasks": [_task_to_dict(t) for t in tasks],
            "operation_logs": [_log_to_dict(o) for o in op_logs],
            "summary": {
                "risk_assessments_count": len(risk_assessments),
                "warnings_count": len(warnings),
                "crisis_events_count": len(crisis_events),
                "intervention_plans_count": len(plans),
                "operation_logs_count": len(op_logs),
            },
        }

    # ── M-4 修复：流式导出方法 ──────────────────────────────────────────
    # M-Svc-4 TODO：以下 iter_* 方法均使用 OFFSET 分页，深翻页时性能下降
    # （OFFSET N 需扫描 N+batch_size 行）。后续应改为 keyset pagination：
    # 基于 (created_at, id) 游标，where (created_at, id) > (last_created_at, last_id)
    # 配合 order_by(created_at.asc(), id.asc()) 实现稳定且高性能的分页。
    # 当前保留 OFFSET 方案，因单用户数据量通常有限（GDPR 导出为低频操作）。

    async def fetch_user_account(self, user_id: int) -> dict[str, Any]:
        """拉取用户账户基础信息（小数据，一次性获取）.

        Raises:
            ValueError: 用户不存在
        """
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _safe_decrypt

        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")
        return {
            "username": _safe_decrypt(user.username, "username"),
            "email": _safe_decrypt(user.email, "email"),
            "phone": _safe_decrypt(user.phone, "phone"),
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
        }

    async def fetch_profile(self, user_id: int) -> dict[str, Any] | None:
        """拉取用户档案（单条）。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _profile_to_dict

        profile = (
            await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        return _profile_to_dict(profile) if profile else None

    async def iter_emergency_contacts(self, user_id: int, batch_size: int = 200):
        """流式输出紧急联系人。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _contact_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(EmergencyContact)
                        .where(EmergencyContact.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for c in rows:
                yield json.dumps(_contact_to_dict(c), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_counselor_bindings(self, user_id: int, batch_size: int = 200):
        """流式输出咨询师绑定。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _binding_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(UserCounselorBinding)
                        .where(UserCounselorBinding.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for b in rows:
                yield json.dumps(_binding_to_dict(b), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_risk_assessments(self, user_id: int, batch_size: int = 200):
        """流式输出风险评估。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _risk_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(RiskAssessment)
                        .where(RiskAssessment.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for r in rows:
                yield json.dumps(_risk_to_dict(r), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_warnings(self, user_id: int, batch_size: int = 200):
        """流式输出预警记录。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _warning_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(WarningNotification)
                        .where(WarningNotification.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for w in rows:
                yield json.dumps(_warning_to_dict(w), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_crisis_events(self, user_id: int, batch_size: int = 200):
        """流式输出危机事件。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _crisis_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(CrisisEvent)
                        .where(CrisisEvent.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for c in rows:
                yield json.dumps(_crisis_to_dict(c), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_intervention_plans(self, user_id: int, batch_size: int = 200):
        """流式输出干预计划。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _plan_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(InterventionPlan)
                        .where(InterventionPlan.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for p in rows:
                yield json.dumps(_plan_to_dict(p), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_intervention_tasks(self, user_id: int, batch_size: int = 200):
        """流式输出干预任务（基于该用户的 plans 关联）。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _task_to_dict

        # 先获取该用户的所有 plan_ids（小集合）
        plan_ids_result = (
            (
                await self.db.execute(
                    select(InterventionPlan.id).where(
                        InterventionPlan.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not plan_ids_result:
            return
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(InterventionTask)
                        .where(InterventionTask.plan_id.in_(plan_ids_result))
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for t in rows:
                yield json.dumps(_task_to_dict(t), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_operation_logs(self, user_id: int, batch_size: int = 200):
        """流式输出操作日志（大数据量，重点分批）。"""
        # 延迟导入模块级辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import _log_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(OperationLog)
                        .where(OperationLog.operator_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for o in rows:
                yield json.dumps(_log_to_dict(o), ensure_ascii=False, default=str)
            offset += batch_size
