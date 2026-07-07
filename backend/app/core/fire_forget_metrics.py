"""R-005 修复: fire-and-forget 任务可观测性统一模块.

提供三个核心 API:
- ``record_scheduled(task_type)``: 调度时递增 ``fire_forget_tasks_total{status="scheduled"}``
- ``make_done_callback(task_type, start_time)``: 返回 done_callback, 根据任务结果
  递增 ``succeeded`` / ``failed`` / ``cancelled``, 同时 observe 耗时直方图
- ``register_task(task, task_type)``: 一站式注册 — 记录 scheduled + 添加 done_callback

设计原则:
- 零侵入: 不修改任务函数体, 仅通过 done_callback 采集指标
- 优雅降级: 指标采集失败仅 debug 日志, 不影响主流程
- 职责分离: 仅采集指标, 日志仍由各模块原有 ``_log_*_exception`` 处理
- 统一入口: 所有 fire-and-forget 任务通过此模块注册

覆盖的 task_type:
- ``assessment_save``: 评估结果保存 (model_predict/_common.py)
- ``review_task_create``: 复核任务创建 (model_predict/predict.py)
- ``warning_intervention``: 告警+干预触发 (risk_service.py)
- ``validation_job``: 模型验证任务 (validation.py)
- ``pdf_generation``: PDF 报告生成 (reports.py)
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


def record_scheduled(task_type: str) -> None:
    """记录 fire-and-forget 任务调度.

    在 ``asyncio.ensure_future`` / ``asyncio.create_task`` 成功后立即调用.
    """
    try:
        from app.core.metrics import fire_forget_tasks_total

        fire_forget_tasks_total.inc(task_type=task_type, status="scheduled")
    except Exception as exc:
        logger.debug("fire_forget record_scheduled failed: %s", exc)


def make_done_callback(task_type: str, start_time: float | None = None):
    """创建 done_callback, 根据任务结果递增 succeeded/failed/cancelled.

    Args:
        task_type: 任务类型标签 (见模块文档)
        start_time: 任务调度时的 ``time.perf_counter()`` 时间戳; 若提供则同时
            observe ``fire_forget_task_duration_seconds`` 直方图

    Usage::

        start = time.perf_counter()
        task = asyncio.ensure_future(my_coro())
        task.add_done_callback(make_done_callback("assessment_save", start))
    """

    def _callback(task: asyncio.Task) -> None:
        if task.cancelled():
            status = "cancelled"
        elif task.exception() is not None:
            status = "failed"
        else:
            status = "succeeded"
        try:
            from app.core.metrics import (
                fire_forget_task_duration_seconds,
                fire_forget_tasks_total,
            )

            fire_forget_tasks_total.inc(task_type=task_type, status=status)
            if start_time is not None:
                duration = time.perf_counter() - start_time
                fire_forget_task_duration_seconds.observe(duration, task_type=task_type)
        except Exception as exc:
            logger.debug("fire_forget done_callback inc failed: %s", exc)

    return _callback


def register_task(task: asyncio.Task, task_type: str) -> asyncio.Task:
    """一站式注册: 记录 scheduled + 添加 done_callback (含耗时).

    Usage::

        task = asyncio.ensure_future(my_coro())
        _task_set.add(task)
        task.add_done_callback(_task_set.discard)
        task.add_done_callback(_log_exception)  # 原有日志回调保留
        register_task(task, "assessment_save")

    Args:
        task: 已调度的 asyncio.Task
        task_type: 任务类型标签

    Returns:
        传入的 task (便于链式调用)
    """
    record_scheduled(task_type)
    task.add_done_callback(make_done_callback(task_type, time.perf_counter()))
    return task
