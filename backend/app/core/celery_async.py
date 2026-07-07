"""RES-P1-003: Celery 任务公共异步执行工具.

提供进程级事件循环复用, 避免 4 个 Celery 任务模块 (alerts/anomaly_detection/
observability/scheduler) 各自维护重复的 _get_loop() / _run_async() 代码.

设计:
- 每个 Celery worker 进程维护一个 asyncio 事件循环, 所有任务共用
- threading.Lock 保护竞态创建 (Celery thread 模式兼容, H-1 修复)
- is_closed() 检查避免使用已关闭的循环
- 替代方案评估:
  - celery[asyncio]: 非官方推荐, 增加依赖复杂度, 无明显收益
  - asyncio.Task: 不适用于 Celery 同步任务上下文 (Celery 任务是同步函数)
  - 当前方案 (进程级单例 + 锁): 简单可靠, 与 Celery prefork/thread 模式兼容

ISS-047 线程安全说明:
- 进程级事件循环单例在 Celery thread 模式下需保证线程安全。
- 已通过 ``_event_loop_lock`` (threading.Lock) 保护 ``_event_loop`` 的读写，
  确保多线程并发调用 ``get_celery_loop()`` 时不会竞态创建多个事件循环。
- 已知局限: ``run_async`` 调用 ``loop.run_until_complete`` 时仍依赖 GIL 串行化，
  不支持多线程同时在同一事件循环上运行协程（Celery prefork 模式无此问题）。
- TODO(多线程并发): 若需多线程同时执行异步任务，应改为每线程独立事件循环
  或使用 ``asyncio.Runner`` (Python 3.12+)。

用法:
    from app.core.celery_async import run_async

    @celery_app.task
    def my_task():
        result = run_async(my_async_impl())
"""

from __future__ import annotations

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

# 进程级事件循环单例 (Celery worker 进程内所有任务共用)
_event_loop: asyncio.AbstractEventLoop | None = None
# H-1 修复: 保护 _get_loop 的锁, 避免 Celery thread 模式下竞态创建多个事件循环
_event_loop_lock = threading.Lock()


def get_celery_loop() -> asyncio.AbstractEventLoop:
    """获取 Celery worker 进程级事件循环 (单例, 线程安全).

    首次调用创建新事件循环, 后续调用复用.
    若循环已关闭 (如异常终止), 自动重建新循环.

    Returns:
        asyncio.AbstractEventLoop: 进程级事件循环
    """
    global _event_loop
    with _event_loop_lock:
        if _event_loop is None or _event_loop.is_closed():
            _event_loop = asyncio.new_event_loop()
            logger.debug("Created new celery event loop: %s", id(_event_loop))
        return _event_loop


def run_async(coro):
    """在 Celery 同步任务中运行异步协程.

    复用进程级事件循环, 避免每次创建新循环的开销.

    Args:
        coro: asyncio 协程对象

    Returns:
        协程执行结果
    """
    loop = get_celery_loop()
    return loop.run_until_complete(coro)
