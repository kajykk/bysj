"""SEC-P1-005 修复：异常访问检测 Celery 周期任务 (v1.40)

周期扫描 OperationLog，调用 anomaly_detection_service.detect_all() 检测异常访问模式，
将检测结果写入 OperationLog (action_type=anomaly_detected) 并递增 Prometheus 指标。

调度: celery_app.beat_schedule 中的 "detect-anomaly-access" 任务，默认每 5 分钟一次。
关联: alert_rules.py AR-303~AR-306, metrics.py anomaly_access_detected_total

任务范式 (与 tasks/alerts.py 一致):
- _run_async + _get_loop 复用 app.core.celery_async 进程级事件循环
- @celery_app.task(bind=True, max_retries=2, ...) + self.retry()
- _utcnow_naive() 处理时区
- 失败时记录日志并重试，重试耗尽返回 {"error": ...}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.celery_async import run_async as _run_async
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=180,
    soft_time_limit=150,
    name="app.tasks.anomaly_detection.detect_anomaly_access_task",
)
def detect_anomaly_access_task(self):
    """SEC-P1-005: 周期扫描 OperationLog 检测异常访问.

    流程:
    1. 调用 anomaly_detection_service.detect_all() 扫描 4 类异常
    2. 将每条 finding 写入 OperationLog (action_type=anomaly_detected)
    3. 递增 Prometheus 指标 anomaly_access_detected_total{type=...}
    4. 更新 anomaly_access_last_detected_at Gauge

    Returns:
        {"detected": N} 或 {"error": "..."}
    """
    logger.info("[anomaly] detect_anomaly_access_task started")
    try:
        result = _run_async(_detect_impl())
        detected_count = result.get("detected", 0) if result else 0
        logger.info(
            "[anomaly] detect_anomaly_access_task completed: %d anomalies",
            detected_count,
        )
        return result
    except Exception as exc:
        logger.error("[anomaly] detect failed: %s", exc, exc_info=True)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[anomaly] detect max retries exceeded")
            return {"error": str(exc)}


async def _detect_impl() -> dict:
    """异常检测实现.

    1. 调用 detect_all() 获取所有 finding
    2. 写入 OperationLog (action_type=anomaly_detected)
    3. 递增 Prometheus 指标
    """
    import json

    from app.core.config import settings
    from app.core.metrics import (
        anomaly_access_detected_total,
        anomaly_access_last_detected_at,
    )
    from app.models.admin import OperationLog
    from app.services.anomaly_detection_service import detect_all

    if not settings.anomaly_detection_enabled:
        logger.debug("[anomaly] detection disabled, skip scan")
        return {"detected": 0, "skipped": "disabled"}

    async with AsyncSessionLocal() as db:
        try:
            findings = await detect_all(db)
            if not findings:
                # 仍更新 last_detected_at (表示扫描成功执行，无异常)
                anomaly_access_last_detected_at.set(0.0)
                return {"detected": 0}

            now_naive = _utcnow_naive()
            written_count = 0
            for finding in findings:
                # 写入 OperationLog (action_type=anomaly_detected)
                # 与 admin.py / gdpr.py 现有模式一致: 直接构造对象
                log_entry = OperationLog(
                    operator_id=finding.operator_id,
                    operator_role=finding.operator_role,
                    action_type="anomaly_detected",
                    target_type="anomaly_finding",
                    target_id=finding.operator_id,  # 异常主体即操作者自身
                    detail=finding.detail,
                    ip_address=finding.ip_address,
                )
                db.add(log_entry)
                written_count += 1

                # 递增 Prometheus 指标 (按 anomaly_type 分标签)
                try:
                    anomaly_access_detected_total.inc(type=finding.anomaly_type)
                except Exception as exc:
                    logger.debug(
                        "[anomaly] failed to inc metric for %s: %s",
                        finding.anomaly_type,
                        exc,
                    )

            await db.commit()

            # 更新最近检测时间戳 (Unix 秒)
            anomaly_access_last_detected_at.set(float(now_naive.timestamp()))

            logger.info(
                "[anomaly] scan completed: %d findings written (types: %s)",
                written_count,
                json.dumps(
                    {f.anomaly_type: 1 for f in findings},
                    ensure_ascii=False,
                ),
            )
            return {
                "detected": written_count,
                "types": list({f.anomaly_type for f in findings}),
            }
        except Exception as exc:
            await db.rollback()
            logger.error("[anomaly] detect transaction failed: %s", exc, exc_info=True)
            raise
