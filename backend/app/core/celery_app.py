from __future__ import annotations

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "depression_system",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    # P1-D-7: DLQ 配置 - 任务失败后保留结果更久便于排查
    task_default_max_retries=2,
    task_default_retry_delay=60,
    # RES-P2-001: Worker 并发参数 - 防止内存泄漏与任务堆积
    # worker_max_tasks_per_child: 每个 worker 子进程执行指定任务数后重启, 释放内存 (防止 PDF/模型加载等内存泄漏)
    # worker_max_memory_per_child: 单个子进程内存上限 (KB), 超过后重启 (400MB, 适配容器化部署)
    worker_max_tasks_per_child=200,
    worker_max_memory_per_child=400 * 1024,
    # RES-P2-001: 任务时间限制 - 防止单任务卡死 worker
    # task_time_limit: 硬超时 (秒), 超过后 worker 强制终止任务
    # task_soft_time_limit: 软超时 (秒), 超过后任务可捕获 SoftTimeLimitExceeded 自行清理
    task_time_limit=600,
    task_soft_time_limit=540,
    # RES-P2-001: 队列分离 - 不同优先级任务路由到不同队列
    # task_routes: 默认路由表, 任务名匹配 pattern → 指定 queue
    # - celery: 默认队列 (普通任务: daily_risk_scan, stale_warning_reminder 等)
    # - celery:high_prio: 高优先级队列 (用户触发的同步任务, 如 generate_pdf_report)
    # - celery:low_prio: 低优先级队列 (清理类任务, 如 cleanup_*, archive_*)
    task_routes={
        "app.tasks.scheduler.daily_risk_scan": {"queue": "celery"},
        "app.tasks.scheduler.stale_warning_reminder": {"queue": "celery"},
        "app.tasks.scheduler.daily_intervention_check": {"queue": "celery"},
        # 用户触发任务 → high_prio
        "app.tasks.scheduler.generate_pdf_report*": {"queue": "celery:high_prio"},
        # 清理类任务 → low_prio
        "app.tasks.scheduler.weekly_log_archive": {"queue": "celery:low_prio"},
        "app.tasks.scheduler.mask_old_ips_task": {"queue": "celery:low_prio"},
        "app.tasks.scheduler.cleanup_*": {"queue": "celery:low_prio"},
        "app.tasks.scheduler.weekly_risk_assessment_archive": {"queue": "celery:low_prio"},
        "app.tasks.scheduler.weekly_monitoring_logs_archive": {"queue": "celery:low_prio"},
        "app.tasks.alerts.archive_old_alerts_task": {"queue": "celery:low_prio"},
    },
    # PERF-P3-003: 为短任务设置更短的时间限制, 避免卡住 worker
    # 这些任务每 30-60s 执行一次, 应在 30s 内完成. 默认 600s/540s 时间限制过长,
    # 任务卡住时会长时间占用 worker, 影响其他任务调度.
    task_annotations={
        "app.tasks.scheduler.canary_auto_rollback_check": {
            "soft_time_limit": 20,
            "time_limit": 30,
        },
        "app.tasks.alerts.escalate_pending_alerts_task": {
            "soft_time_limit": 30,
            "time_limit": 60,
        },
        "app.tasks.observability.flush_lock_stats_task": {
            "soft_time_limit": 15,
            "time_limit": 30,
        },
        "app.tasks.anomaly_detection.detect_anomaly_access_task": {
            "soft_time_limit": 120,
            "time_limit": 180,
        },
    },
    # RES-P2-001: 默认队列名 (向后兼容: 未匹配 task_routes 的任务进入默认队列)
    task_default_queue="celery",
)
# PERF-P3-003 部署建议 (不在代码中强制, 由部署脚本配置):
# 生产环境建议为不同队列启动独立 worker, 配置不同的 prefetch_multiplier:
#   # 长任务队列 (PDF/模型训练): 低 prefetch, 防止积压
#   celery -A app.core.celery_app worker -Q celery --prefetch-multiplier=1
#   # 高优先级队列 (用户触发): 中 prefetch, 平衡响应速度与公平性
#   celery -A app.core.celery_app worker -Q celery:high_prio --prefetch-multiplier=2
#   # 低优先级队列 (清理/归档): 高 prefetch, 提高吞吐量
#   celery -A app.core.celery_app worker -Q celery:low_prio --prefetch-multiplier=4

celery_app.conf.beat_schedule = {
    "daily-risk-scan": {
        "task": "app.tasks.scheduler.daily_risk_scan",
        "schedule": crontab(hour=8, minute=0),
    },
    "stale-warning-reminder": {
        "task": "app.tasks.scheduler.stale_warning_reminder",
        "schedule": crontab(hour=9, minute=0),
    },
    "daily-intervention-check": {
        "task": "app.tasks.scheduler.daily_intervention_check",
        "schedule": crontab(hour=7, minute=30),
    },
    "weekly-log-archive": {
        "task": "app.tasks.scheduler.weekly_log_archive",
        "schedule": crontab(day_of_week=1, hour=3, minute=0),
    },
    # SEC-P2-008: OperationLog IP 掩码 (GDPR 合规) - 每日 03:30 掩码 30 天前的 IP
    # 与 weekly-log-archive 配合: 30 天后掩码 IP, 90 天后删除整条记录
    "daily-mask-old-ips": {
        "task": "app.tasks.scheduler.mask_old_ips_task",
        "schedule": crontab(hour=3, minute=30),
    },
    "canary-auto-rollback-check": {
        "task": "app.tasks.scheduler.canary_auto_rollback_check",
        "schedule": 30.0,  # Every 30 seconds
    },
    # v1.34: 告警升级 - 每分钟扫描
    "escalate-pending-alerts": {
        "task": "app.tasks.alerts.escalate_pending_alerts_task",
        "schedule": 60.0,  # Every 60 seconds
    },
    # v1.34: 告警归档 - 每日 03:00
    "archive-old-alerts": {
        "task": "app.tasks.alerts.archive_old_alerts_task",
        "schedule": crontab(hour=3, minute=0),
    },
    # v1.36: dedup_lock 统计 flush - 每分钟
    "flush-lock-stats": {
        "task": "app.tasks.observability.flush_lock_stats_task",
        "schedule": 60.0,  # Every 60 seconds
    },
    # RES-P1-005: TRAINING_JOBS 字典 LRU 清理 - 每 6 小时
    "cleanup-training-jobs": {
        "task": "app.tasks.scheduler.cleanup_training_jobs_task",
        "schedule": crontab(hour="*/6", minute=15),
    },
    # RES-P1-006: uploads/ 目录清理过期文件 - 每日 03:30
    "cleanup-uploads-dir": {
        "task": "app.tasks.scheduler.cleanup_uploads_dir_task",
        "schedule": crontab(hour=3, minute=30),
    },
    # RES-P1-007: experiment artifact 清理旧产物 - 每周一 04:00
    "cleanup-experiment-artifacts": {
        "task": "app.tasks.scheduler.cleanup_experiment_artifacts_task",
        "schedule": crontab(day_of_week=1, hour=4, minute=0),
    },
    # PERF-P2-003: risk_assessments 表归档 - 每周一 04:30 删除 365 天前的记录
    # 维护 is_latest 标志位, WarningNotification 外键 ondelete=SET NULL 自动处理
    "weekly-risk-assessment-archive": {
        "task": "app.tasks.scheduler.weekly_risk_assessment_archive",
        "schedule": crontab(day_of_week=1, hour=4, minute=30),
    },
    # RES-P2-005: monitoring_logs 表归档 - 每周一 05:00 删除 180 天前的记录
    # 与 weekly-risk-assessment-archive (04:30) 错开 30 分钟, 避免并发归档争抢资源
    "weekly-monitoring-logs-archive": {
        "task": "app.tasks.scheduler.weekly_monitoring_logs_archive",
        "schedule": crontab(day_of_week=1, hour=5, minute=0),
    },
    # SEC-P1-005: 异常访问检测 - 每 5 分钟扫描 OperationLog
    # 关联 alert_rules.py AR-303~AR-306 + services/anomaly_detection_service.py
    "detect-anomaly-access": {
        "task": "app.tasks.anomaly_detection.detect_anomaly_access_task",
        "schedule": 300.0,  # Every 300 seconds (5 minutes)
    },
}

celery_app.autodiscover_tasks(["app.tasks"])


# P1-D-7: DLQ - 任务失败信号处理器
# 当任务超过最大重试次数后, 记录完整的失败上下文到日志, 便于后续排查
@task_failure.connect
def on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **extra,
):
    """P1-D-7: DLQ 信号处理器 - 记录任务失败完整上下文.

    当任务抛出异常 (包括重试耗尽后) 时触发, 记录:
    - task_name: 任务名称
    - task_id: 任务 ID
    - args/kwargs: 任务参数 (脱敏后)
    - exception: 异常类型和消息
    - traceback: 堆栈信息

    这些日志可被日志收集系统 (如 ELK/Loki) 捕获, 作为 DLQ 的替代方案.

    STAB-P1-018 修复: 同时递增 celery_task_failures_total Prometheus 指标,
    配合 alert_rules.py AR-204 规则实现告警.
    """
    task_name = getattr(sender, "name", str(sender)) if sender else "unknown"
    # 脱敏: 避免在日志中泄露敏感参数 (如密码)
    safe_args = _sanitize_task_args(args)
    safe_kwargs = _sanitize_task_args(kwargs)

    logger.error(
        "[DLQ] task failure - name=%s id=%s exception=%s args=%s kwargs=%s",
        task_name,
        task_id,
        f"{type(exception).__name__}: {exception}" if exception else "unknown",
        safe_args,
        safe_kwargs,
        exc_info=exception,
    )

    # STAB-P1-018: 递增 Prometheus 失败计数指标, 触发 AR-204 告警
    try:
        from app.core.metrics import celery_task_failures_total

        celery_task_failures_total.inc(task_name=task_name)
    except Exception as exc:
        logger.debug("celery_task_failures_total inc failed: %s", exc)


def _sanitize_task_args(args) -> str:
    """P1-D-7: 脱敏任务参数, 避免在 DLQ 日志中泄露敏感信息."""
    if args is None:
        return "None"
    try:
        masked = _mask_sensitive(args)
        repr_str = repr(masked)
        if len(repr_str) > 500:
            return repr_str[:500] + "...(truncated)"
        return repr_str
    except Exception:
        return "<unreprable>"


# 敏感键集合 (小写匹配): 密码/令牌/密钥/PII 等
# L-12 修复：补充 jwt/bearer/credit_card 等常见敏感关键词，避免在 DLQ 日志中泄露
_SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "email",
    "phone",
    "ssn",
    "api_key",
    "authorization",
    "jwt",
    "bearer",
    "credit_card",
    "credit_card_number",
    "cvv",
}


def _mask_sensitive(value):
    """递归遍历参数, 对敏感键的值替换为 ***MASKED***."""
    if isinstance(value, dict):
        return {
            k: (
                "***MASKED***"
                if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS
                else _mask_sensitive(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        masked = [_mask_sensitive(item) for item in value]
        # L-Core-2 修复：tuple 子类（如 namedtuple）的 type(value)(masked) 可能失败，
        # 因为 namedtuple 构造函数接受位置参数而非可迭代对象。统一返回 tuple。
        return tuple(masked) if isinstance(value, tuple) else masked
    return value
