from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from app.core.degradation import record_silent_degradation
from app.core.pending_events import schedule_after_commit
from app.core.states import BindingStatus
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
)
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import UserCounselorBinding

logger = logging.getLogger(__name__)

# M12 修复（ROUND_19）：预警阈值默认值抽成常量。
# 无 WarningSetting 行时按"中风险及以上"（2 级）预警，与产品口径一致。
DEFAULT_WARNING_THRESHOLD = 2


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
            .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())
            .limit(1)
        )
        previous = (await self.db.execute(stmt)).scalar_one_or_none()

        # H-Svc-7 修复：previous.risk_level 可能为 None，需额外检查避免后续比较抛 TypeError
        previous_level = (
            previous.risk_level if previous and previous.risk_level is not None else 0
        )

        # M12 修复（ROUND_19）：预警阈值**先读设置再判定**。
        # 原实现先硬编码 `risk_level >= 2`、读完 threshold_level 后又拿它做一次
        # 上限比较 —— 结果是"只能把阈值调高、不能调低"：seed 里
        # threshold_level=1 的用户永远收不到 1 级预警，该配置是死配置。
        # 现在阈值唯一地来自用户设置（无设置时回落默认值），
        # 判定与文案都基于同一个 threshold。
        setting_stmt = select(WarningSetting).where(WarningSetting.user_id == user_id)
        setting = (await self.db.execute(setting_stmt)).scalar_one_or_none()
        threshold = (
            setting.threshold_level
            if setting and setting.threshold_level is not None
            else DEFAULT_WARNING_THRESHOLD
        )
        should_warn = current_risk.risk_level >= threshold
        if should_warn:
            if current_risk.risk_level > previous_level:
                reason = f"风险等级从{previous_level}级上升到{current_risk.risk_level}级，已达到预警阈值（{threshold}级）"
            else:
                reason = f"当前风险等级为{current_risk.risk_level}级，已达到预警阈值（{threshold}级），需要咨询师关注"
        else:
            reason = ""

        logger.info(
            "risk.judgement user_id=%s current_level=%s previous_level=%s threshold=%s should_warn=%s reason=%s",
            user_id,
            current_risk.risk_level,
            previous_level,
            threshold,
            should_warn,
            reason or "-",
        )

        if not should_warn:
            return None

        duplicate_stmt = select(WarningNotification).where(
            WarningNotification.risk_assessment_id == current_risk.id,
        )
        existing_warning = (await self.db.execute(duplicate_stmt)).scalar_one_or_none()
        if existing_warning is not None:
            return existing_warning

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
            # ROUND_25 (B 摊): bound_at 非唯一（无 (user_id,status=active) 唯一约束）
            # ⇒ 同秒多条 ACTIVE 绑定时"取当前绑定"结果不确定；补 id 次级键
            .order_by(
                UserCounselorBinding.bound_at.desc(), UserCounselorBinding.id.desc()
            )
            .limit(1)
        )
        binding = (await self.db.execute(bind_stmt)).scalars().first()
        if binding:
            warning.counselor_id = binding.counselor_id

        # R-C: 发布 warning.created 事件到 EventBus, 实时更新 Prometheus 指标.
        # M14 修复（ROUND_19）：改为**事务提交后**发布。原实现在 flush() 之后、
        # 调用方 commit() 之前发布，订阅方用独立 session 回查会读到空行；
        # 若事务随后回滚（同评估流程后续步骤失败），则"事件已发、数据不存在"。
        # 现在只登记，after_commit 钩子负责发布；回滚则事件随事务消失。
        # 事件发布非阻塞 (put_nowait)，不影响业务主流程。
        schedule_after_commit(
            self.db,
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
        # ISS-014 修复：with_for_update() 行级锁，降低同一用户重复生成计划的概率。
        # M13 修复（ROUND_23）：注意这把锁**不是唯一性保证**——它只锁已存在的
        # 行，空表（或历史计划都已 cancelled）时两个并发事务都查不到行、都无
        # 行可锁（文本/生理两路各自独立 AsyncSessionLocal，见
        # services/risk_service.py 的 _trigger_warning_and_intervention）。
        # 唯一性由 uq_intervention_plans_active_per_user 约束兜底（下方
        # _create_plan_from_template 的 except SAIntegrityError 分支），
        # 本 select 保留 for_update 只是把冲突窗口从"秒级"缩到"毫秒级"。
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
                # M17 + M13 修复（ROUND_23）：取消旧计划与插入新计划放在同一
                # savepoint 内。唯一约束（uq_intervention_plans_active_per_user）
                # 要求旧 active 先让位、新 active 才能插入；两步必须原子——
                #   - 插入失败（并发冲突/DB 错误）⇒ savepoint 自动回滚，旧计划
                #     恢复 active，不会"升级失败反而失去所有干预"；
                #   - 无模板（_create_plan_from_template 返回 None）⇒ 撤销让位
                #     （内存改回 + flush，**不 rollback savepoint**——rollback 会
                #     剥离子查询对象，异步上下文访问属性即 DetachedInstanceError），
                #     保持 M17 的语义（旧计划不被取消、原样返回）。
                async with self.db.begin_nested():
                    existing_plan.status = "cancelled"
                    # 让位先生效：savepoint 内 UPDATE 后再 INSERT，
                    # 同一连接按语句序执行，新插入才不会撞自己的唯一约束。
                    await self.db.flush()
                    new_plan = await self._create_plan_from_template(
                        user_id, risk_level
                    )
                    if new_plan is None:
                        existing_plan.status = "active"
                        await self.db.flush()
                if new_plan is not None:
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
            # ROUND_25 (B 摊): bound_at 非唯一（无 (user_id,status=active) 唯一约束）
            # ⇒ 同秒多条 ACTIVE 绑定时"取当前绑定"结果不确定；补 id 次级键
            .order_by(
                UserCounselorBinding.bound_at.desc(), UserCounselorBinding.id.desc()
            )
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
        # M13 修复（ROUND_23）：约束兜底。并发评估都查不到 active ⇒ 都走到
        # 这里插入，第二条撞 uq_intervention_plans_active_per_user
        # （model __table_args__ + 迁移 r2a3b4c5d6e7 双声明）。
        # savepoint 隔离冲突插入（C-2 同款范式：避免单个计划冲突把整个
        # 评估事务拖进"必须回滚"状态），except 后回查已存在的那条返回——
        # 并发冲突不是错误，但不能无痕：记 silent_degradation 供 /metrics 观测。
        # 回查带 for_update：若另一事务尚未提交，等其提交后即可见
        # （PG 下插入方在唯一索引上等待，flush 抛错时对方已提交；
        # SQLite 下写锁串行化，同理）。
        try:
            async with self.db.begin_nested():
                self.db.add(plan)
                await self.db.flush()
        except SAIntegrityError:
            existing = (
                await self.db.execute(
                    select(InterventionPlan)
                    .where(
                        InterventionPlan.user_id == user_id,
                        InterventionPlan.status == "active",
                    )
                    .order_by(InterventionPlan.id.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalars().first()
            if existing is not None:
                record_silent_degradation(
                    "services.risk_service_warning.active_plan_conflict_recovered"
                )
                logger.info(
                    "intervention.active_plan_conflict_recovered user_id=%s "
                    "existing_plan_id=%s risk_level=%s",
                    user_id,
                    existing.id,
                    risk_level,
                )
                return existing
            # 回查仍为空 ⇒ 冲突并非来自本唯一约束（或对方已回滚），
            # 原样上抛，由调用方的降级分支记账（services.risk_service
            # 的 intervention_generation_failed）。
            raise

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
