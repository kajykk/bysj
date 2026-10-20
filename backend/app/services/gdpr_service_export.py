"""GDPR 数据导出 Mixin.

实现用户的"数据可携权"(Article 20 - Data Portability).

包含:
- export_user_data: 一次性导出所有个人数据 (机器可读 JSON)
- fetch_user_account / fetch_profile: 流式导出基础方法
- iter_emergency_contacts / iter_counselor_bindings / iter_risk_assessments /
  iter_warnings / iter_crisis_events / iter_intervention_plans /
  iter_intervention_tasks / iter_operation_logs / iter_structured_assessments /
  iter_text_entries / iter_physiological_records / iter_consultation_records /
  iter_task_executions / iter_data_drafts: 流式迭代器 (OFFSET 分页)

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
from app.models.assessment import (
    DataDraft,
    PhysiologicalRecord,
    StructuredAssessment,
    TextEntry,
)
from app.models.counselor import ConsultationRecord
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    TaskExecution,
)
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
            _consultation_to_dict,
            _contact_to_dict,
            _crisis_to_dict,
            _data_draft_to_dict,
            _log_to_dict,
            _physiological_to_dict,
            _plan_to_dict,
            _profile_to_dict,
            _risk_to_dict,
            _safe_decrypt,
            _structured_to_dict,
            _task_execution_to_dict,
            _task_to_dict,
            _text_entry_to_dict,
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
        # P2-31：GDPR 数据主体导出按 user_id 取数（scope 是数据主体本人或平台
        # 管理员的 Article 15 履行，不按租户切分），显式声明豁免。
        crisis_events = (
            (
                await self.db.execute(
                    select(CrisisEvent)
                    .where(CrisisEvent.user_id == user_id)
                    .execution_options(tenant_exempt="data_subject_gdpr")
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

        # 9~14. M16 修复（ROUND_19）：补齐此前漏导出的核心个人数据。
        # 这些表**全部**在匿名化流程里被擦除（gdpr_service_anonymize 的
        # _step_anonymize_pii_texts / _step_anonymize_intervention_chain /
        # _step_clear_json_payloads）⇒ 漏导出 = 用户"导出时拿不到、
        # 删除后永远拿不到"，可携权（Article 20）形同虚设。
        structured_assessments = (
            (
                await self.db.execute(
                    select(StructuredAssessment).where(
                        StructuredAssessment.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        text_entries = (
            (
                await self.db.execute(
                    select(TextEntry).where(TextEntry.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        physiological_records = (
            (
                await self.db.execute(
                    select(PhysiologicalRecord).where(
                        PhysiologicalRecord.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        consultation_records = (
            (
                await self.db.execute(
                    select(ConsultationRecord).where(
                        ConsultationRecord.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        task_ids = [t.id for t in tasks]
        task_executions: list[Any] = []
        if task_ids:
            task_executions = (
                (
                    await self.db.execute(
                        select(TaskExecution).where(TaskExecution.task_id.in_(task_ids))
                    )
                )
                .scalars()
                .all()
            )
        data_drafts = (
            (
                await self.db.execute(
                    select(DataDraft).where(DataDraft.user_id == user_id)
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
            # M16 修复（ROUND_19）：新增 6 个 section（与匿名化覆盖面对齐）
            "structured_assessments": [
                _structured_to_dict(s) for s in structured_assessments
            ],
            "text_entries": [_text_entry_to_dict(t) for t in text_entries],
            "physiological_records": [
                _physiological_to_dict(p) for p in physiological_records
            ],
            "consultation_records": [
                _consultation_to_dict(c) for c in consultation_records
            ],
            "task_executions": [_task_execution_to_dict(e) for e in task_executions],
            "data_drafts": [_data_draft_to_dict(d) for d in data_drafts],
            "summary": {
                "risk_assessments_count": len(risk_assessments),
                "warnings_count": len(warnings),
                "crisis_events_count": len(crisis_events),
                "intervention_plans_count": len(plans),
                "operation_logs_count": len(op_logs),
                # M16：summary 同步补 6 项，避免"数组里有、摘要里没有"的口径分裂
                "structured_assessments_count": len(structured_assessments),
                "text_entries_count": len(text_entries),
                "physiological_records_count": len(physiological_records),
                "consultation_records_count": len(consultation_records),
                "task_executions_count": len(task_executions),
                "data_drafts_count": len(data_drafts),
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
                        # AUDIT-2026-10-13 (P1-23)：LIMIT/OFFSET 分页**必须有稳定
                        # ORDER BY**。SQL 不保证无 ORDER BY 时 LIMIT/OFFSET 的返回
                        # 顺序，同一行可能在两页都出现或整页被跳过 —— GDPR 导出
                        # 漏行是**合规实质缺陷**（主体有权拿到全部个人数据）。
                        # 按主键升序 = 稳定且与物理写入顺序无关。
                        .order_by(EmergencyContact.id.asc())
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）
                        .order_by(UserCounselorBinding.id.asc())
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）
                        .order_by(RiskAssessment.id.asc())
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）
                        .order_by(WarningNotification.id.asc())
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）
                        .order_by(CrisisEvent.id.asc())
                        .offset(offset)
                        .limit(batch_size)
                        # P2-31：数据主体导出按 user_id 取数，显式豁免（理由同 collect_user_data）
                        .execution_options(tenant_exempt="data_subject_gdpr")
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）
                        .order_by(InterventionPlan.id.asc())
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）
                        .order_by(InterventionTask.id.asc())
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
                        # P1-23：稳定排序，避免 OFFSET 翻页漏行/重复（同上）。
                        # 操作日志是本方法中数据量最大的一张表，翻页最深，漏行
                        # 风险也最高。
                        .order_by(OperationLog.id.asc())
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

    # ── M16 修复（ROUND_19）：流式导出补齐 6 个漏掉的 section ──────────
    # 一次性导出（export_user_data）与流式导出必须同清单，否则两条路径
    # 给用户的东西不一样；coverage 闸门同时盯两张清单。

    async def iter_structured_assessments(self, user_id: int, batch_size: int = 200):
        """流式输出结构化问卷逐题作答（含 ``data_payload`` 原文）。"""
        from app.services.gdpr_service import _structured_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(StructuredAssessment)
                        .where(StructuredAssessment.user_id == user_id)
                        .order_by(StructuredAssessment.id.asc())
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for s in rows:
                yield json.dumps(
                    _structured_to_dict(s), ensure_ascii=False, default=str
                )
            offset += batch_size

    async def iter_text_entries(self, user_id: int, batch_size: int = 200):
        """流式输出情绪日记正文。"""
        from app.services.gdpr_service import _text_entry_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(TextEntry)
                        .where(TextEntry.user_id == user_id)
                        .order_by(TextEntry.id.asc())
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
                yield json.dumps(_text_entry_to_dict(t), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_physiological_records(self, user_id: int, batch_size: int = 200):
        """流式输出生理指标记录。"""
        from app.services.gdpr_service import _physiological_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(PhysiologicalRecord)
                        .where(PhysiologicalRecord.user_id == user_id)
                        .order_by(PhysiologicalRecord.id.asc())
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
                yield json.dumps(
                    _physiological_to_dict(p), ensure_ascii=False, default=str
                )
            offset += batch_size

    async def iter_consultation_records(self, user_id: int, batch_size: int = 200):
        """流式输出咨询记录自由文本。"""
        from app.services.gdpr_service import _consultation_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(ConsultationRecord)
                        .where(ConsultationRecord.user_id == user_id)
                        .order_by(ConsultationRecord.id.asc())
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
                yield json.dumps(
                    _consultation_to_dict(c), ensure_ascii=False, default=str
                )
            offset += batch_size

    async def iter_task_executions(self, user_id: int, batch_size: int = 200):
        """流式输出干预任务执行记录（基于该用户的 plans 关联）。"""
        from app.services.gdpr_service import _task_execution_to_dict

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
                        select(TaskExecution)
                        .join(
                            InterventionTask,
                            TaskExecution.task_id == InterventionTask.id,
                        )
                        .where(InterventionTask.plan_id.in_(plan_ids_result))
                        .order_by(TaskExecution.id.asc())
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for e in rows:
                yield json.dumps(
                    _task_execution_to_dict(e), ensure_ascii=False, default=str
                )
            offset += batch_size

    async def iter_data_drafts(self, user_id: int, batch_size: int = 200):
        """流式输出表单草稿。"""
        from app.services.gdpr_service import _data_draft_to_dict

        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(DataDraft)
                        .where(DataDraft.user_id == user_id)
                        .order_by(DataDraft.id.asc())
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for d in rows:
                yield json.dumps(_data_draft_to_dict(d), ensure_ascii=False, default=str)
            offset += batch_size
