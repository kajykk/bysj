"""R-C: 轻量级进程内事件总线.

使用 asyncio.Queue 实现单进程内的事件订阅/发布.
跨进程事件通过 Redis pubsub (复用 ws.py 模式, 后续升级).

事件类型:
- alert.fired: 告警触发 (DriftAlert 创建/重开)
- alert.resolved: 告警恢复 (DriftAlert 状态置为 RESOLVED)
- alert.escalated: 告警升级 (DriftAlert 状态置为 ACKNOWLEDGED)
- warning.created: 风险预警创建 (WarningNotification 创建)
- review.submitted: 评估复核提交 (ReviewTask 创建)

设计要点:
- 队列容量 10000, 满时丢弃事件并告警 (避免 OOM)
- 单 handler 异常不影响其他 handler (异常隔离)
- 保留 60s 周期轮询作为兜底 (防止事件丢失)
- 非阻塞 publish (put_nowait), 不影响业务主流程
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# 事件处理器类型: async def handler(event_data: dict) -> None
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]

# 事件队列最大容量, 满时丢弃 (防止 OOM)
_MAX_QUEUE_SIZE = 10000


class EventBus:
    """进程内异步事件总线.

    Usage:
        # 订阅
        event_bus.subscribe("alert.fired", my_handler)

        # 发布
        await event_bus.publish("alert.fired", {"alert_id": 123})

        # 启动/停止消费循环
        await event_bus.start()
        await event_bus.stop()
    """

    def __init__(self, max_queue_size: int = _MAX_QUEUE_SIZE) -> None:
        self._max_queue_size = max_queue_size
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._running = False
        self._consumer_task: asyncio.Task[None] | None = None
        # 统计指标 (供 ObservabilityExporter 采集)
        self.events_published: int = 0
        self.events_dropped: int = 0
        self.events_processed: int = 0
        self.handler_errors: int = 0

    def _ensure_queue(self) -> asyncio.Queue[dict[str, Any]]:
        """惰性创建队列, 绑定到当前 event loop.

        修复测试隔离问题: 模块级单例的 asyncio.Queue 在 import 时创建,
        绑定到第一个 event loop。后续测试使用新 loop 时会报
        'attached to a different loop' 错误。
        """
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        return self._queue

    def reset(self) -> None:
        """重置全局状态, 供测试间隔离使用.

        清空 handlers / queue / consumer_task / 统计指标,
        使下次使用时惰性创建绑定到当前 event loop 的新队列。
        """
        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
        self._consumer_task = None
        self._running = False
        self._handlers.clear()
        self._queue = None
        self.events_published = 0
        self.events_dropped = 0
        self.events_processed = 0
        self.handler_errors = 0

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件.

        Args:
            event_type: 事件类型 (如 "alert.fired")
            handler: 异步处理函数, 接收 dict 参数
        """
        self._handlers[event_type].append(handler)
        logger.debug(
            "Subscribed handler %s to event type: %s", handler.__name__, event_type
        )

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """发布事件 (非阻塞, 队列满时丢弃并告警).

        Args:
            event_type: 事件类型
            data: 事件数据 (必须 JSON 可序列化)
        """
        event: dict[str, Any] = {"type": event_type, "data": data}
        try:
            self._ensure_queue().put_nowait(event)
            self.events_published += 1
        except asyncio.QueueFull:
            self.events_dropped += 1
            logger.warning(
                "Event bus queue full (%d events), dropping event: %s",
                self._queue.maxsize,
                event_type,
            )

    async def start(self) -> None:
        """启动事件消费循环."""
        if self._running:
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("EventBus started (queue_size=%d)", self._max_queue_size)

    async def stop(self) -> None:
        """停止事件消费循环."""
        self._running = False
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        logger.info(
            "EventBus stopped (published=%d, processed=%d, dropped=%d, errors=%d)",
            self.events_published,
            self.events_processed,
            self.events_dropped,
            self.handler_errors,
        )

    async def _consume_loop(self) -> None:
        """消费队列中的事件并分发给订阅者."""
        queue = self._ensure_queue()
        while self._running:
            try:
                event = await queue.get()
                event_type: str = event["type"]
                event_data: dict[str, Any] = event["data"]
                handlers = self._handlers.get(event_type, [])
                for handler in handlers:
                    try:
                        await handler(event_data)
                    except Exception:
                        self.handler_errors += 1
                        logger.exception(
                            "Event handler failed for type=%s, handler=%s",
                            event_type,
                            getattr(handler, "__name__", repr(handler)),
                        )
                self.events_processed += 1
            except asyncio.CancelledError:
                break
            except Exception:
                # 不应到达此处, 但防御性捕获以防 _queue.get() 异常导致循环退出
                logger.exception("Event consume loop unexpected error")


# 全局事件总线实例
event_bus = EventBus()
