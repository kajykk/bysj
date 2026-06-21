from __future__ import annotations

import logging
import os

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
)

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
}

celery_app.autodiscover_tasks(["app.tasks"])


# P1-D-7: DLQ - 任务失败信号处理器
# 当任务超过最大重试次数后, 记录完整的失败上下文到日志, 便于后续排查
@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None,
                    args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """P1-D-7: DLQ 信号处理器 - 记录任务失败完整上下文.

    当任务抛出异常 (包括重试耗尽后) 时触发, 记录:
    - task_name: 任务名称
    - task_id: 任务 ID
    - args/kwargs: 任务参数 (脱敏后)
    - exception: 异常类型和消息
    - traceback: 堆栈信息

    这些日志可被日志收集系统 (如 ELK/Loki) 捕获, 作为 DLQ 的替代方案.
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
_SENSITIVE_KEYS = {
    "password", "token", "secret", "email", "phone", "ssn", "api_key", "authorization",
}


def _mask_sensitive(value):
    """递归遍历参数, 对敏感键的值替换为 ***MASKED***."""
    if isinstance(value, dict):
        return {
            k: ("***MASKED***" if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS else _mask_sensitive(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        masked = [_mask_sensitive(item) for item in value]
        return type(value)(masked) if isinstance(value, tuple) else masked
    return value
