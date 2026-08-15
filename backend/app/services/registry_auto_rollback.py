"""R2 训练产物自动回退监控: PRODUCTION 产物回退率超阈值时自动降级.

原理:
    predict 路径记录每个 model_id 的推理/回退事件 (shadow_comparison_service.record_inference),
    本服务定期检查 registry 中 PRODUCTION 状态且由训练注册的记录:
    - 回退率 > max_fallback_rate 且样本足够 -> 自动降级为 CANDIDATE,
      推理链 (resolve_model_path) 随即回退静态模型路径
- 人工可由 API 触发单次检查, 或由后台周期任务 (lifespan) 驱动
- 降级动作经 registry 磁盘持久化
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_rollback_task: asyncio.Task | None = None


def _is_test_environment() -> bool:
    return os.environ.get("PYTEST_CURRENT_TEST") is not None


def check_auto_rollback() -> list[dict[str, Any]]:
    """检查所有 PRODUCTION 训练产物的回退率, 超阈值则自动降级.

    返回结果列表 (含触发回退的记录).
    """
    from app.core.model_registry_v2 import (
        ModelStatus,
        get_registry,
        rollback_training_model,
    )
    from app.services.shadow_comparison_service import (
        get_shadow_comparison_service,
    )

    shadow = get_shadow_comparison_service()
    registry = get_registry()
    results: list[dict[str, Any]] = []

    for record in registry.get_models_by_status(ModelStatus.PRODUCTION):
        # 仅检查训练注册的产物 (人工静态注册的记录不受自动回退影响)
        if not record.training_config:
            continue
        should, reason = shadow.should_auto_rollback(record.model_id)
        if not should:
            results.append(
                {
                    "model_id": record.model_id,
                    "action": "keep",
                    "reason": reason,
                }
            )
            continue
        demoted = rollback_training_model(record.model_id)
        if demoted is None:
            logger.error(
                "auto-rollback: fail to demote model %s (%s)",
                record.model_id,
                reason,
            )
            results.append(
                {"model_id": record.model_id, "action": "failed", "reason": reason}
            )
            continue
        logger.warning(
            "auto-rollback: model %s demoted to CANDIDATE (%s)",
            record.model_id,
            reason,
        )
        demoted.metrics["auto_rollback_reason"] = reason
        demoted.metrics["auto_rollback_at"] = datetime.now(timezone.utc).isoformat()
        registry._save_registry()
        shadow.reset_health(record.model_id)
        results.append(
            {
                "model_id": record.model_id,
                "action": "rollback",
                "reason": reason,
                "status": demoted.status.value,
            }
        )
    return results


async def _rollback_loop() -> None:
    while True:
        try:
            if settings.registry_auto_rollback_enabled:
                check_auto_rollback()
        except Exception as exc:
            logger.error("auto-rollback: check failed: %s", exc, exc_info=True)
        await asyncio.sleep(int(settings.registry_auto_rollback_interval))


async def start_auto_rollback_monitor(app: "FastAPI") -> None:
    global _rollback_task
    if _is_test_environment():
        logger.info("auto-rollback: skipped in test environment")
        return
    if _rollback_task is not None and not _rollback_task.done():
        logger.warning("auto-rollback: already running, skip duplicate start")
        return
    _rollback_task = asyncio.create_task(_rollback_loop())
    app.state.auto_rollback_task = _rollback_task
    logger.info(
        "auto-rollback: monitor started (interval=%ds, max_fallback_rate=%.2f)",
        settings.registry_auto_rollback_interval,
        settings.registry_auto_rollback_max_fallback_rate,
    )


async def stop_auto_rollback_monitor() -> None:
    global _rollback_task
    if _rollback_task is None:
        return
    _rollback_task.cancel()
    try:
        await _rollback_task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("auto-rollback: error during stop: %s", exc, exc_info=True)
    _rollback_task = None
    logger.info("auto-rollback: monitor stopped")


def is_auto_rollback_running() -> bool:
    return _rollback_task is not None and not _rollback_task.done()
