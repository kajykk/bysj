from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Select, select

from app.core.event_bus import event_bus
from app.core.states import BindingStatus
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
)
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import UserCounselorBinding

logger = logging.getLogger(__name__)


class WarningInterventionMixin:
    """风险告警与干预计划生成相关方法 Mixin。

    包含告警触发判定、告警通知生成、自动干预计划生成、模板应用等逻辑。
    依赖主类 RiskService 提供 `self.db`。
    """

    async def _check_warning_trigger(
        self, user_id: int, current_risk: RiskAssessment
    ) -> WarningNotification | None:
        stmt: Select = (
            select(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id, RiskAssessment.id < current_risk.id
            )
            .order_by(RiskAssessment.created_at.desc())
            .limit(1)
        )
        previous = (await self.db.execute(stmt)).scalar_one_or_none()

        # H-Svc-7 修复：previous.risk_level 可能为 None，需额外检查避免后续比较抛 TypeError
        previous_level = (
            previous.risk_level if previous and previous.risk_level is not None else 0
        )
        should_warn = current_risk.risk_level >= 2
        # L-08 修复：复用 should_warn 变量，避免重复计算 current_risk.risk_level >= 2
        if should_warn:
            if current_risk.risk_level > previous_level:
                reason = f"风险等级从{previous_level}级上升到{current_risk.risk_level}级，已达到中风险及以上"
            else:
                reason = f"当前风险等级为{current_risk.risk_level}级，已达到中风险及以上，需要咨询师关注"
        else:
            reason = ""

        logger.info(
            "risk.judgement user_id=%s current_level=%s previous_level=%s should_warn=%s reason=%s",
            user_id,
            current_risk.risk_level,
            previous_level,
            should_warn,
            reason or "-",
        )

        if not should_warn:
            return None

        setting_stmt = select(WarningSetting).where(WarningSetting.user_id == user_id)
        setting = (await self.db.execute(setting_stmt)).scalar_one_or_none()
        threshold = (
            setting.threshold_level
            if setting and setting.threshold_level is not None
            else 2
        )
        if current_risk.risk_level < threshold:
            return None

        duplicate_stmt = select(WarningNotification).where(
            WarningNotification.risk_assessment_id == current_risk.id,
        )
        existing_warning = (await self.db.execute(duplicate_stmt)).scalar_one_or_none()
        if existing_warning is not None:
            return existing_warning

        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        warning = WarningNotification(
            user_id=user_id,
            risk_assessment_id=current_risk.id,
            previous_level=previous_level,
            current_level=current_risk.risk_level,
            trigger_reason=reason,
        )
        try:
            # C-2 修复：使用 savepoint 隔离 warning 插入失败，避免回滚已成功的 risk assessment
            async with self.db.begin_nested():
                self.db.add(warning)
                await self.db.flush()
        except SAIntegrityError:
            warning = (await self.db.execute(duplicate_stmt)).scalar_one_or_none()
            if warning is not None:
                return warning
            raise

        bind_stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(bind_stmt)).scalars().first()
        if binding:
            warning.counselor_id = binding.counselor_id

        # R-C: 发布 warning.created 事件到 EventBus, 实时更新 Prometheus 指标.
        # 仅在新建 WarningNotification 成功 (flush 通过) 后发布;
        # 重复 warning (IntegrityError 路径) 提前 return, 不发布事件.
        # 事件发布非阻塞 (put_nowait), 不影响业务主流程.
        try:
            await event_bus.publish(
                "warning.created",
                {
                    "warning_id": warning.id,
                    "user_id": warning.user_id,
                    "risk_assessment_id": warning.risk_assessment_id,
                    "previous_level": warning.previous_level,
                    "current_level": warning.current_level,
                    "trigger_reason": warning.trigger_reason,
                    "counselor_id": warning.counselor_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            # EventBus 发布失败不应影响业务主流程
            logger.warning("Failed to publish warning.created event", exc_info=True)

        return warning

    async def trigger_warning_for_risk(
        self, risk: RiskAssessment
    ) -> WarningNotification | None:
        return await self._check_warning_trigger(
            user_id=risk.user_id, current_risk=risk
        )

    async def generate_intervention_for_risk(self, risk: RiskAssessment) -> None:
        """Generate or update an active intervention plan for medium-and-above risk assessments."""
        if risk.risk_level < 2:
            return
        await self._auto_generate_intervention(
            user_id=risk.user_id, risk_level=risk.risk_level
        )

    async def _auto_generate_intervention(
        self, user_id: int, risk_level: int
    ) -> InterventionPlan | None:
        # ISS-014 修复：添加 with_for_update() 行级锁，防止并发产生重复干预计划
        stmt = (
            select(InterventionPlan)
            .where(
                InterventionPlan.user_id == user_id,
                InterventionPlan.status == "active",
            )
            .order_by(InterventionPlan.id.desc())
            .limit(1)
            .with_for_update()
        )
        existing_plan = (await self.db.execute(stmt)).scalars().first()

        if existing_plan:
            if risk_level > existing_plan.risk_level:
                # M17 修复：先创建新计划，确认成功后再取消旧计划，避免无模板时用户失去所有干预
                new_plan = await self._create_plan_from_template(user_id, risk_level)
                if new_plan is not None:
                    existing_plan.status = "cancelled"
                    return new_plan
            return existing_plan

        return await self._create_plan_from_template(user_id, risk_level)

    async def _create_plan_from_template(
        self, user_id: int, risk_level: int
    ) -> InterventionPlan | None:
        stmt = (
            select(InterventionTemplate)
            .where(InterventionTemplate.status == "active")
            .order_by(InterventionTemplate.id)
        )
        templates = (await self.db.execute(stmt)).scalars().all()

        template = None
        for candidate in templates:
            levels = candidate.applicable_levels or []
            if risk_level in levels:
                template = candidate
                break

        if template is None:
            template = templates[0] if templates else None
            if template is None:
                # H-Svc-8 修复：无活跃模板时记录告警，避免高风险用户无干预计划被静默掩盖
                logger.warning(
                    "No active intervention template found for risk level %s",
                    risk_level,
                )
                return None

        normalized_tasks = self._validate_and_normalize_template_tasks(
            template.task_list, template.template_name
        )

        bind_stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(bind_stmt)).scalars().first()

        plan = InterventionPlan(
            user_id=user_id,
            counselor_id=binding.counselor_id if binding else None,
            plan_name=template.template_name,
            risk_level=risk_level,
            status="active",
            start_date=date.today(),
            end_date=date.today() + timedelta(weeks=template.estimated_weeks or 4),
        )
        self.db.add(plan)
        await self.db.flush()

        for i, task_def in enumerate(normalized_tasks):
            task = InterventionTask(
                plan_id=plan.id,
                task_name=task_def["task_name"],
                task_type=task_def["task_type"],
                description=task_def.get("description", ""),
                schedule=task_def.get("schedule", "daily"),
                duration_minutes=task_def.get("duration_minutes", 15),
                sort_order=i,
            )
            self.db.add(task)

        return plan

    @staticmethod
    def _validate_and_normalize_template_tasks(
        task_list: object, template_name: str
    ) -> list[dict]:
        if not isinstance(task_list, list):
            raise ValueError(f"干预模板 {template_name} 的任务列表格式错误")
        if not task_list:
            raise ValueError(f"干预模板 {template_name} 的任务列表不能为空")

        normalized: list[dict] = []
        for idx, task_def in enumerate(task_list, start=1):
            if not isinstance(task_def, dict):
                raise ValueError(f"干预模板 {template_name} 的第 {idx} 个任务格式错误")

            task_name = str(task_def.get("task_name", "")).strip()
            task_type = str(task_def.get("task_type", "")).strip()
            if not task_name or not task_type:
                raise ValueError(
                    f"干预模板 {template_name} 的第 {idx} 个任务缺少必要字段"
                )

            duration_raw = task_def.get("duration_minutes", 15)
            try:
                duration_minutes = int(duration_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"干预模板 {template_name} 的第 {idx} 个任务时长非法"
                ) from exc
            if duration_minutes <= 0:
                raise ValueError(
                    f"干预模板 {template_name} 的第 {idx} 个任务时长必须大于0"
                )

            normalized.append(
                {
                    "task_name": task_name,
                    "task_type": task_type,
                    "description": str(task_def.get("description", "") or "").strip(),
                    "schedule": str(
                        task_def.get("schedule", "daily") or "daily"
                    ).strip()
                    or "daily",
                    "duration_minutes": duration_minutes,
                }
            )

        return normalized
