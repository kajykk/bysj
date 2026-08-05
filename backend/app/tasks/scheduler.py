from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, func, insert, literal, not_, select

from app.core.celery_app import celery_app
from app.core.celery_async import get_celery_loop
from app.core.celery_async import run_async as _run_async
from app.core.database import AsyncSessionLocal
from app.models.admin import OperationLog
from app.models.counselor import CounselorProfile
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import User, UserCounselorBinding

logger = logging.getLogger(__name__)
_get_loop = get_celery_loop

# RES-P3-002: 每日风险扫描分页大小 (keyset 游标分页, 避免一次性加载全部活跃用户)
_RISK_SCAN_PAGE_SIZE = 500


def _to_aware_utc(dt: datetime) -> datetime:
    """将 naive datetime 视为 UTC 并转为 aware，避免 aware/naive 相减抛 TypeError。

    模型列使用 DateTime（无 timezone），DB 返回 naive datetime；
    而代码中统一使用 datetime.now(UTC)（aware）做比较，需先归一化。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def _notify_warning(
    user_id: int,
    warning_id: int,
    risk_level: int,
    trigger_reason: str,
    counselor_id: int | None,
) -> None:
    try:
        from app.core.contracts import normalize_risk_level
        from app.core.ws import notify_counselor, notify_warning

        level_str = normalize_risk_level(risk_level)
        await notify_warning(user_id, warning_id, level_str, trigger_reason)
        if counselor_id:
            await notify_counselor(counselor_id, user_id, warning_id, level_str)
    except Exception:
        logger.warning(
            "Failed to send WebSocket notification for warning %d",
            warning_id,
            exc_info=True,
        )


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=270,
)
def daily_risk_scan(self):
    logger.info("Starting daily risk scan")
    # P1-P3 修复：原代码声明 max_retries=2 但无 try/except + self.retry()，
    # 导致任务失败后不会重试，max_retries 配置形同虚设。
    # 改为：捕获异常后调用 self.retry() 触发重试（受 max_retries 限制）。
    try:
        _run_async(_daily_risk_scan_impl())
    except Exception as exc:
        logger.warning("Daily risk scan failed, will retry: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    logger.info("Daily risk scan completed")


async def _daily_risk_scan_impl():
    async with AsyncSessionLocal() as db:
        # RES-P3-002 修复: keyset 游标分页 (每批 500), 替代一次性 .all() 全量加载.
        # 用户规模大时全量加载会同时占满内存与连接; 分页后单批内存有界, 长列表可中断续跑.
        scanned_count = 0
        warning_count = 0
        # H-ML-6 修复：收集待发送的通知，commit 之后再发送
        # 原 flush 后立即 notify，若 commit 失败 rollback，用户收到告警但 DB 无记录
        pending_notifications: list[tuple[int, int, int, str, int | None]] = []

        last_user_id: int | None = None
        while True:
            conditions = [User.role == "user", User.status == "active"]
            if last_user_id is not None:
                conditions.append(User.id > last_user_id)
            active_users_stmt = (
                select(User)
                .where(*conditions)
                .order_by(User.id)
                .limit(_RISK_SCAN_PAGE_SIZE)
            )
            users = (await db.execute(active_users_stmt)).scalars().all()
            if not users:
                break
            last_user_id = users[-1].id

            for user in users:
                scanned_count += 1
                # PERF-P2-002: 使用 is_latest 标志替代 ORDER BY created_at DESC LIMIT 1
                latest_risk_stmt = (
                    select(RiskAssessment)
                    .where(
                        RiskAssessment.user_id == user.id,
                        RiskAssessment.is_latest.is_(True),
                    )
                    .limit(1)
                )
                latest_risk = (await db.execute(latest_risk_stmt)).scalar_one_or_none()

                if latest_risk is None:
                    continue

                days_since = (
                    datetime.now(UTC) - _to_aware_utc(latest_risk.created_at)
                ).days
                if days_since > 7 and latest_risk.risk_level >= 2:
                    setting_stmt = select(WarningSetting).where(
                        WarningSetting.user_id == user.id
                    )
                    setting = (await db.execute(setting_stmt)).scalar_one_or_none()
                    threshold = setting.threshold_level if setting else 2

                    if latest_risk.risk_level >= threshold:
                        bind_stmt = select(UserCounselorBinding).where(
                            UserCounselorBinding.user_id == user.id,
                            UserCounselorBinding.status == "active",
                        )
                        binding = (await db.execute(bind_stmt)).scalar_one_or_none()
                        trigger_reason = (
                            f"用户风险等级{latest_risk.risk_level}级且超过"
                            f"{days_since}天未评估，建议关注"
                        )
                        # H-ML-7 修复: 检查 + 插入合并为单条原子 INSERT ... WHERE NOT EXISTS,
                        # 消除 TOCTOU 竞态 (原实现先 SELECT 再 INSERT, 两个并发扫描/重试窗口内
                        # 会重复插入同原因告警). returning() 拿到自增 id, 空结果即重复, 跳过.
                        dedupe_condition = and_(
                            WarningNotification.user_id == user.id,
                            WarningNotification.trigger_reason.like("%超过7天未评估%"),
                            # H-ML-5 修复: DB 列为 naive datetime, 使用 naive UTC 比较
                            WarningNotification.created_at
                            >= datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
                        )
                        insert_stmt = (
                            insert(WarningNotification)
                            .from_select(
                                [
                                    WarningNotification.user_id,
                                    WarningNotification.risk_assessment_id,
                                    WarningNotification.previous_level,
                                    WarningNotification.current_level,
                                    WarningNotification.trigger_reason,
                                    WarningNotification.counselor_id,
                                    WarningNotification.is_read,
                                    WarningNotification.is_handled,
                                ],
                                select(
                                    literal(user.id),
                                    literal(latest_risk.id),
                                    literal(latest_risk.risk_level),
                                    literal(latest_risk.risk_level),
                                    literal(trigger_reason),
                                    literal(binding.counselor_id if binding else None),
                                    literal(False),
                                    literal(False),
                                ).where(
                                    not_(
                                        select(1).where(dedupe_condition).exists()
                                    )
                                ),
                            )
                            .returning(WarningNotification.id)
                        )
                        inserted_id = (
                            await db.execute(insert_stmt)
                        ).scalar_one_or_none()
                        if inserted_id is not None:
                            warning_count += 1
                            # H-ML-6 修复：先收集通知，等 commit 成功后再发送
                            # 原 flush 后立即 notify，若 commit 失败 rollback，用户收到告警但 DB 无记录
                            pending_notifications.append(
                                (
                                    user.id,
                                    inserted_id,
                                    latest_risk.risk_level,
                                    trigger_reason,
                                    binding.counselor_id if binding else None,
                                )
                            )

            if len(users) < _RISK_SCAN_PAGE_SIZE:
                break

        await db.commit()
        logger.info(
            "Daily risk scan summary: scanned=%d users, generated=%d warnings",
            scanned_count,
            warning_count,
        )

        # H-ML-6 修复：commit 成功后再发通知，避免 rollback 后用户收到告警但 DB 无记录
        for (
            user_id,
            warning_id,
            risk_level,
            trigger_reason,
            counselor_id,
        ) in pending_notifications:
            await _notify_warning(
                user_id, warning_id, risk_level, trigger_reason, counselor_id
            )


@celery_app.task(bind=True, max_retries=1, time_limit=120, soft_time_limit=100)
def stale_warning_reminder(self):
    logger.info("Starting stale warning reminder")
    try:
        _run_async(_stale_warning_reminder_impl())
    except Exception as exc:
        logger.warning(
            "Stale warning reminder failed, will retry: %s", exc, exc_info=True
        )
        raise self.retry(exc=exc)
    logger.info("Stale warning reminder completed")


async def _stale_warning_reminder_impl():
    async with AsyncSessionLocal() as db:
        # H-ML-5 修复：DB 列为 naive datetime，使用 naive UTC 比较
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        unhandled_stmt = select(WarningNotification).where(
            WarningNotification.is_handled.is_(False),
            WarningNotification.created_at < cutoff,
            WarningNotification.current_level >= 3,
        )
        stale_warnings = (await db.execute(unhandled_stmt)).scalars().all()

        for warning in stale_warnings:
            if warning.counselor_id:
                logger.info(
                    "Reminder: Warning %d for user %d is unhandled for >24h (counselor: %d)",
                    warning.id,
                    warning.user_id,
                    warning.counselor_id,
                )


@celery_app.task(bind=True, max_retries=1, time_limit=180, soft_time_limit=160)
def daily_intervention_check(self):
    logger.info("Starting daily intervention check")
    try:
        _run_async(_daily_intervention_check_impl())
    except Exception as exc:
        logger.warning(
            "Daily intervention check failed, will retry: %s", exc, exc_info=True
        )
        raise self.retry(exc=exc)
    logger.info("Daily intervention check completed")


async def _daily_intervention_check_impl():
    async with AsyncSessionLocal() as db:
        active_plans_stmt = select(InterventionPlan).where(
            InterventionPlan.status == "active"
        )
        plans = (await db.execute(active_plans_stmt)).scalars().all()

        # P1-E 修复：日志添加业务上下文（计划数、完成任务数）
        plan_count = len(plans)
        completed_plan_count = 0
        execution_created_count = 0

        # L-ML-9 确认：end_date 为 Date 列（naive），today 取 naive UTC 日期，与 H-ML-5 保持一致
        today = datetime.now(UTC).date()

        for plan in plans:
            if plan.end_date and plan.end_date < today:
                plan.status = "completed"
                completed_plan_count += 1
                continue

            tasks_stmt = select(InterventionTask).where(
                InterventionTask.plan_id == plan.id
            )
            tasks = (await db.execute(tasks_stmt)).scalars().all()

            for task in tasks:
                if (task.schedule or "daily").strip().lower() == "daily":
                    existing_stmt = select(TaskExecution).where(
                        TaskExecution.task_id == task.id,
                        TaskExecution.user_id == plan.user_id,
                        TaskExecution.scheduled_date == today,
                    )
                    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
                    if existing is None:
                        execution = TaskExecution(
                            task_id=task.id,
                            user_id=plan.user_id,
                            scheduled_date=today,
                            status="pending",
                        )
                        db.add(execution)
                        execution_created_count += 1

            total_tasks_stmt = (
                select(func.count())
                .select_from(TaskExecution)
                .where(
                    TaskExecution.user_id == plan.user_id,
                    TaskExecution.task_id.in_([t.id for t in tasks]),
                )
            )
            completed_tasks_stmt = (
                select(func.count())
                .select_from(TaskExecution)
                .where(
                    TaskExecution.user_id == plan.user_id,
                    TaskExecution.status == "completed",
                    TaskExecution.task_id.in_([t.id for t in tasks]),
                )
            )
            total = (await db.execute(total_tasks_stmt)).scalar_one()
            completed = (await db.execute(completed_tasks_stmt)).scalar_one()
            if total > 0:
                plan.progress = int(completed / total * 100)

        await db.commit()
        logger.info(
            "Daily intervention check summary: plans=%d, completed_plans=%d, executions_created=%d",
            plan_count,
            completed_plan_count,
            execution_created_count,
        )


@celery_app.task(bind=True, max_retries=1, time_limit=120, soft_time_limit=100)
def weekly_log_archive(self):
    logger.info("Starting weekly log archive")
    try:
        _run_async(_weekly_log_archive_impl())
    except Exception as exc:
        logger.warning("Weekly log archive failed, will retry: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    logger.info("Weekly log archive completed")


async def _weekly_log_archive_impl():
    async with AsyncSessionLocal() as db:
        from app.services.admin_service import AdminService

        service = AdminService(db)
        count = await service.archive_old_logs(days=90)
        logger.info("Archived %d old operation logs", count)


@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30, time_limit=60, soft_time_limit=50
)
def mask_old_ips_task(self):
    """SEC-P2-008: 掩码 30 天前的 OperationLog.ip_address (GDPR 合规).

    与 weekly_log_archive 配合:
    - 30 天后: 掩码 IP (保留网络段, 仍可用于异常检测)
    - 90 天后: 删除整条记录 (archive_old_logs)
    """
    logger.info("Starting mask old IPs task (SEC-P2-008)")
    try:
        _run_async(_mask_old_ips_impl())
    except Exception as exc:
        logger.warning(
            "Mask old IPs task failed, will retry: %s", exc, exc_info=True
        )
        raise self.retry(exc=exc)
    logger.info("Mask old IPs task completed")


async def _mask_old_ips_impl():
    async with AsyncSessionLocal() as db:
        from app.services.admin_service import AdminService

        service = AdminService(db)
        count = await service.mask_old_ips(days=30)
        logger.info("Masked IPs for %d old operation logs", count)


@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30, time_limit=120, soft_time_limit=100
)
def weekly_risk_assessment_archive(self):
    """PERF-P2-003: 归档 (删除) 365 天前的 RiskAssessment 记录.

    长期累积的 risk_assessments 表会拖慢查询, 每周清理一次超过 365 天的记录.
    维护 is_latest 标志位 (PERF-P2-002): 被删除的 is_latest=True 记录
    会从剩余记录中重新标记一条最新的.
    WarningNotification.risk_assessment_id 外键 ondelete="SET NULL" 自动处理.
    """
    logger.info("Starting weekly risk assessment archive (PERF-P2-003)")
    try:
        _run_async(_weekly_risk_assessment_archive_impl())
    except Exception as exc:
        logger.warning(
            "Weekly risk assessment archive failed, will retry: %s",
            exc,
            exc_info=True,
        )
        raise self.retry(exc=exc)
    logger.info("Weekly risk assessment archive completed")


async def _weekly_risk_assessment_archive_impl():
    async with AsyncSessionLocal() as db:
        from app.services.admin_service import AdminService

        service = AdminService(db)
        count = await service.archive_old_risk_assessments(days=365)
        logger.info("Archived %d old risk assessments", count)


@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30, time_limit=120, soft_time_limit=100
)
def weekly_monitoring_logs_archive(self):
    """RES-P2-005: 归档 (删除) 180 天前的 MonitoringLog 记录.

    监控日志 (inference/fallback/drift_alert/canary_switch 等) 增长迅速,
    每周清理一次超过 180 天的记录, 避免监控日志表拖慢查询.
    与 archive_old_logs (OperationLog, 90 天) 分离, 监控日志保留更久用于趋势分析.
    """
    logger.info("Starting weekly monitoring logs archive (RES-P2-005)")
    try:
        _run_async(_weekly_monitoring_logs_archive_impl())
    except Exception as exc:
        logger.warning(
            "Weekly monitoring logs archive failed, will retry: %s",
            exc,
            exc_info=True,
        )
        raise self.retry(exc=exc)
    logger.info("Weekly monitoring logs archive completed")


async def _weekly_monitoring_logs_archive_impl():
    async with AsyncSessionLocal() as db:
        from app.services.admin_service import AdminService

        service = AdminService(db)
        count = await service.archive_old_monitoring_logs(days=180)
        logger.info("Archived %d old monitoring logs", count)


@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=30, time_limit=60, soft_time_limit=50
)
def canary_auto_rollback_check(self):
    logger.info("Starting canary auto-rollback check")
    try:
        _run_async(_canary_auto_rollback_check_impl())
    except Exception as exc:
        logger.warning(
            "Canary auto-rollback check failed, will retry: %s", exc, exc_info=True
        )
        raise self.retry(exc=exc)
    logger.info("Canary auto-rollback check completed")


async def _canary_auto_rollback_check_impl():
    async with AsyncSessionLocal() as db:
        from app.services.auto_rollback_service import auto_rollback_service

        results = await auto_rollback_service.check_all_canaries(db)
        # H-AUDIT-01 修复: execute_rollback 仅 flush (C-Svc-1), 此处必须 commit,
        # 否则回滚状态/rollback_reason/ended_at 随 session 关闭全部丢失,
        # 自动回滚静默失效. (对照 drift 路径 scheduler.py drift_monitoring_check_impl)
        await db.commit()
        for result in results:
            if result.should_rollback:
                logger.warning(
                    "Auto-rollback triggered for canary %d: %s",
                    result.canary_id,
                    result.reason,
                )
            else:
                logger.debug(
                    "Canary %d health check: %s (metrics: %s)",
                    result.canary_id,
                    result.reason,
                    result.metrics,
                )


# ============================================================================
# S4 P3: 漂移监测任务 (Celery beat 每小时触发)
# ============================================================================


@celery_app.task(
    bind=True, max_retries=1, default_retry_delay=60, time_limit=120, soft_time_limit=100
)
def drift_monitoring_check(self):
    """S4 P3: 漂移监测 — 计算 PSI/KL 并写入 DriftAlert + Gauge.

    每小时从 RiskAssessment 读取各模态评分, 计算 baseline(7d) vs current(24h) 的
    PSI/KL, 写入 model_drift_psi/model_drift_kl Gauge (Grafana) 和 DriftAlert 表 (auto-rollback).
    """
    logger.info("Starting drift monitoring check")
    try:
        _run_async(_drift_monitoring_check_impl())
    except Exception as exc:
        logger.warning("Drift monitoring check failed, will retry: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    logger.info("Drift monitoring check completed")


async def _drift_monitoring_check_impl():
    from app.services.drift_monitoring_service import drift_monitoring_service

    async with AsyncSessionLocal() as db:
        results = await drift_monitoring_service.check_all_modalities(db)
        for r in results:
            if r.psi > 0.25:
                logger.warning(
                    "Drift detected: modality=%s feature=%s PSI=%.4f KL=%.4f alert=%s",
                    r.modality, r.feature, r.psi, r.kl, r.alert_created,
                )
            else:
                logger.debug(
                    "Drift check: modality=%s PSI=%.4f (baseline=%d current=%d)",
                    r.modality, r.psi, r.baseline_n, r.current_n,
                )
        # S4 P4 修复: 提交事务, 确保 DriftAlert 记录持久化 (此前仅 flush 未 commit, 导致告警丢失)
        await db.commit()


# ============================================================================
# RES-P1-005/006/007: 资源清理任务 (Celery beat 周期触发)
# ============================================================================


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    time_limit=120,
    soft_time_limit=100,
)
def cleanup_training_jobs_task(self):
    """RES-P1-005: 清理 TRAINING_JOBS 字典中的旧任务 (每 6 小时).

    调用 model_predict_service.cleanup_old_training_jobs() 清理超出上限
    (TRAINING_JOBS_MAX_SIZE=100) 的已完成任务.
    """
    logger.info("Starting TRAINING_JOBS cleanup")
    try:
        from app.services.model_predict_service import cleanup_old_training_jobs

        removed = cleanup_old_training_jobs()
        logger.info("TRAINING_JOBS cleanup completed: removed=%d", removed)
    except Exception as exc:
        logger.warning("TRAINING_JOBS cleanup failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


def _collect_upload_ref(raw: str | None, referenced: set[str]) -> None:
    """从 URL/JSON 字符串中提取 ``{user_id}/{filename}`` 上传相对路径并加入集合.

    SEC-AUDIT-07: 清理前保护仍被 DB 引用的文件. 只识别 ``/uploads/{数字}/{文件名}``
    形态的私有文件引用; 公共目录 (audio/content) 不参与清理, 无需收集.
    """
    if not raw:
        return
    path = raw.split("?", 1)[0]
    parts = path.split("/")
    if len(parts) >= 4 and parts[1] == "uploads" and parts[2].isdigit():
        referenced.add("/".join(parts[2:]))


async def _load_referenced_upload_paths() -> set[str]:
    """从 DB 加载仍被引用的上传文件相对路径集合 (``{user_id}/{filename}``).

    引用来源:
    1. ``User.avatar_url`` (头像)
    2. ``CounselorProfile.certificate_url`` (咨询师证书)
    3. ``OperationLog`` ``user_file_upload`` 审计日志 (detail JSON 内 url 字段)

    SEC-AUDIT-07: 修复原实现"文档声称检查 DB 引用但实际未查询"的缺口.
    查询失败时降级为空集合 (仅凭过期时间清理, 保证定时任务不中断), 记录 warning.
    """
    referenced: set[str] = set()
    try:
        async with AsyncSessionLocal() as db:
            avatar_stmt = select(User.avatar_url).where(User.avatar_url.is_not(None))
            for (avatar_url,) in (await db.execute(avatar_stmt)).all():
                _collect_upload_ref(avatar_url, referenced)

            cert_stmt = select(CounselorProfile.certificate_url).where(
                CounselorProfile.certificate_url.is_not(None)
            )
            for (cert_url,) in (await db.execute(cert_stmt)).all():
                _collect_upload_ref(cert_url, referenced)

            log_stmt = select(OperationLog.detail).where(
                OperationLog.action_type == "user_file_upload",
                OperationLog.detail.is_not(None),
            )
            for (detail,) in (await db.execute(log_stmt)).all():
                try:
                    parsed = json.loads(detail)
                    if isinstance(parsed, dict):
                        _collect_upload_ref(parsed.get("url"), referenced)
                    else:
                        _collect_upload_ref(detail, referenced)
                except (json.JSONDecodeError, TypeError):
                    _collect_upload_ref(detail, referenced)
    except Exception as exc:
        logger.warning(
            "upload 引用查询失败, 降级为无引用清理 (仅按过期时间): %s", exc,
            exc_info=True,
        )
    return referenced


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=280,
)
def cleanup_uploads_dir_task(self):
    """RES-P1-006: 清理 uploads/ 目录中的过期文件 (每日 03:30).

    删除 uploads/{user_id}/ 下超过 30 天未访问的文件 (基于 mtime).
    公共目录 (audio/content) 不清理.
    SEC-AUDIT-07: 清理前先查询 DB 引用 (头像/证书/上传审计日志), 仍被引用的文件不清理.
    """
    logger.info("Starting uploads/ directory cleanup")
    try:
        # SEC-AUDIT-07: 加载 DB 引用集合 (失败时 _load_referenced_upload_paths 降级为空集)
        referenced = _run_async(_load_referenced_upload_paths())
        removed = _cleanup_uploads_dir_impl(referenced=referenced)
        logger.info(
            "uploads/ cleanup completed: removed=%d files (db-referenced=%d)",
            removed,
            len(referenced),
        )
    except Exception as exc:
        logger.warning("uploads/ cleanup failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


def _cleanup_uploads_dir_impl(max_age_days: int = 30, referenced: set[str] | None = None) -> int:
    """清理 uploads/ 目录的同步实现 (供 Celery 任务调用).

    Args:
        max_age_days: 文件最大保留天数 (默认 30 天)
        referenced: DB 中仍被引用的文件相对路径集合 (``{user_id}/{filename}``);
            None 或空集表示不启用 DB 引用保护.

    Returns:
        删除的文件数

    ISS-050 已知限制: 基于 st_mtime 清理，可被 touch 命令重置 (延长文件保留期)。
    生产环境如需强一致, 应在文件上传时记录创建时间到独立元数据表, 或改用
    DB 创建时间驱动清理 (SEC-AUDIT-07 已保证被引用的文件不会被误删).
    """
    from app.api.v1.uploads import PUBLIC_DIRS, _resolve_upload_dir

    uploads_dir = _resolve_upload_dir()
    if not uploads_dir.exists():
        logger.info("uploads/ directory does not exist, skip cleanup")
        return 0

    cutoff = datetime.now(UTC).timestamp() - max_age_days * 86400
    removed = 0
    referenced = referenced or set()

    for entry in uploads_dir.iterdir():
        if not entry.is_dir():
            continue
        # 跳过公共目录 (audio/content)
        if entry.name in PUBLIC_DIRS:
            continue
        # 仅清理数字命名的用户目录 (user_id)
        if not entry.name.isdigit():
            continue
        # 遍历用户目录中的文件
        for file_path in entry.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                rel_path = file_path.relative_to(uploads_dir).as_posix()
                # SEC-AUDIT-07: 跳过仍被 DB 引用的文件 (头像/证书/上传记录)
                if rel_path in referenced:
                    logger.debug("skip DB-referenced upload: %s", rel_path)
                    continue
                stat = file_path.stat()
                # 使用 mtime 作为删除依据 (atime 在很多 FS 上不可靠)
                # ISS-050 已知限制: mtime 可被 touch 命令重置，见函数 docstring 中的 TODO
                if stat.st_mtime < cutoff:
                    file_path.unlink(missing_ok=True)
                    removed += 1
            except OSError as exc:
                logger.debug("skip file %s: %s", file_path, exc)

        # 如果用户目录已空, 删除空目录
        try:
            if not any(entry.iterdir()):
                entry.rmdir()
        except OSError:
            pass

    return removed


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=280,
)
def cleanup_experiment_artifacts_task(self):
    """RES-P1-007: 清理 experiment_trainer artifact (每周一 04:00).

    删除 models/trained/ 下超出保留数量的旧训练产物目录.
    保留最近 10 个 model_name 目录, 按 saved_at 排序.
    """
    logger.info("Starting experiment artifacts cleanup")
    try:
        removed = _cleanup_experiment_artifacts_impl()
        logger.info("experiment artifacts cleanup completed: removed=%d dirs", removed)
    except Exception as exc:
        logger.warning("experiment artifacts cleanup failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


def _cleanup_experiment_artifacts_impl(keep_recent: int = 10) -> int:
    """清理 experiment_trainer artifact 的同步实现.

    Args:
        keep_recent: 保留最近 N 个训练产物目录 (默认 10)

    Returns:
        删除的目录数
    """
    from app.core.config import settings
    from app.core.model_registry import MODEL_PATHS

    trained_root = Path(settings.model_dir) / "trained"
    if not trained_root.exists():
        logger.info("trained/ directory does not exist, skip cleanup")
        return 0

    # 收集所有训练产物目录
    artifacts: list[tuple[Path, float]] = []
    for entry in trained_root.iterdir():
        if not entry.is_dir():
            continue
        # 用 mtime 作为排序依据
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        artifacts.append((entry, mtime))

    if len(artifacts) <= keep_recent:
        return 0

    # 按 mtime 降序排序 (最新的在前), 保留前 keep_recent 个
    artifacts.sort(key=lambda x: x[1], reverse=True)
    to_remove = artifacts[keep_recent:]

    # 收集所有注册的模型路径 (绝对路径), 防止误删 active 模型
    active_paths: set[str] = set()
    for model_path_str in MODEL_PATHS.values():
        try:
            active_paths.add(str(Path(model_path_str).resolve()))
        except Exception:
            pass

    removed = 0
    for entry, _ in to_remove:
        try:
            # 安全检查: 如果目录中的文件被注册为 active 模型, 跳过
            is_active = False
            for file_path in entry.rglob("*"):
                if file_path.is_file():
                    try:
                        if str(file_path.resolve()) in active_paths:
                            is_active = True
                            break
                    except Exception:
                        pass
            if is_active:
                logger.info("skip cleanup: %s contains active model artifact", entry)
                continue
            import shutil

            shutil.rmtree(entry, ignore_errors=False)
            removed += 1
        except OSError as exc:
            logger.warning("failed to remove artifact dir %s: %s", entry, exc)

    return removed
