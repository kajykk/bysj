"""R-C: EventBus 单元测试.

测试范围 (对应 SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md 3.6.2 Step 5):
- test_subscribe_publish: 基本订阅/发布
- test_multiple_subscribers: 多订阅者
- test_queue_full_drops_event: 队列满丢弃
- test_handler_exception_isolated: 异常隔离
- test_observability_exporter_realtime_update: 实时指标更新
- test_end_to_end_latency: 端到端延迟 < 5s
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.core import metrics
from app.core.event_bus import EventBus

# 模块加载时捕获真实 ObservabilityExporter 类引用.
# conftest.py 的 autouse fixture mock_observability_exporter 会在测试运行时
# 替换 app.services.observability_exporter.ObservabilityExporter 模块符号,
# 但本文件在模块加载时已捕获真实类引用, 测试内仍可创建真实实例.
from app.services.observability_exporter import ObservabilityExporter


def _reset_event_metrics() -> None:
    """重置 R-C 事件驱动 Prometheus 指标."""
    metrics.event_alerts_fired_total._values.clear()
    metrics.event_alerts_resolved_total._values.clear()
    metrics.event_alerts_escalated_total._values.clear()
    metrics.event_warnings_created_total._values.clear()
    metrics.event_reviews_submitted_total._values.clear()
    metrics.event_bus_dropped_total._values.clear()


class TestEventBusBasic:
    """EventBus 基本功能测试."""

    @pytest.mark.asyncio
    async def test_subscribe_publish(self) -> None:
        """测试基本订阅/发布: 单订阅者收到事件数据."""
        received: list[dict] = []

        async def handler(data: dict) -> None:
            received.append(data)

        bus = EventBus(max_queue_size=100)
        bus.subscribe("alert.fired", handler)
        await bus.start()

        await bus.publish("alert.fired", {"alert_id": 123, "severity": "HIGH"})
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["alert_id"] == 123
        assert received[0]["severity"] == "HIGH"
        assert bus.events_published == 1
        assert bus.events_processed == 1
        assert bus.events_dropped == 0

        await bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        """测试多订阅者: 同一事件类型的多个 handler 都被调用."""
        calls: list[str] = []

        async def handler1(data: dict) -> None:
            calls.append("handler1")

        async def handler2(data: dict) -> None:
            calls.append("handler2")

        bus = EventBus(max_queue_size=100)
        bus.subscribe("alert.fired", handler1)
        bus.subscribe("alert.fired", handler2)
        await bus.start()

        await bus.publish("alert.fired", {"alert_id": 1})
        await asyncio.sleep(0.1)

        assert len(calls) == 2
        assert "handler1" in calls
        assert "handler2" in calls

        await bus.stop()


class TestEventBusResilience:
    """EventBus 容错性测试."""

    @pytest.mark.asyncio
    async def test_queue_full_drops_event(self) -> None:
        """测试队列满时丢弃事件并递增 dropped 计数."""
        # 容量 1: 第一条进入队列, 第二条被丢弃
        bus = EventBus(max_queue_size=1)

        # 不订阅 handler, 事件留在队列中不被消费
        await bus.start()

        await bus.publish("alert.fired", {"id": 1})
        await bus.publish("alert.fired", {"id": 2})  # 应被丢弃

        assert bus.events_published == 1
        assert bus.events_dropped == 1

        await bus.stop()

    @pytest.mark.asyncio
    async def test_handler_exception_isolated(self) -> None:
        """测试异常隔离: 单个 handler 抛异常不影响其他 handler 执行."""
        results: list[str] = []

        async def failing_handler(data: dict) -> None:
            raise RuntimeError("handler failed")

        async def normal_handler(data: dict) -> None:
            results.append("normal_handler_called")

        bus = EventBus(max_queue_size=100)
        bus.subscribe("alert.fired", failing_handler)
        bus.subscribe("alert.fired", normal_handler)
        await bus.start()

        await bus.publish("alert.fired", {"alert_id": 1})
        await asyncio.sleep(0.1)

        # failing_handler 抛异常, normal_handler 仍应被调用
        assert len(results) == 1
        assert results[0] == "normal_handler_called"
        assert bus.handler_errors == 1
        assert bus.events_processed == 1

        await bus.stop()


class TestObservabilityRealtime:
    """ObservabilityExporter 实时指标更新测试."""

    @pytest.mark.asyncio
    async def test_observability_exporter_realtime_update(self, monkeypatch) -> None:
        """测试事件触发后 Prometheus 指标实时更新 (5 类事件)."""
        _reset_event_metrics()

        # 创建全新的 EventBus 实例, 替换 observability_exporter 模块中的 event_bus 引用,
        # 避免全局 event_bus 跨测试状态污染.
        fresh_bus = EventBus(max_queue_size=100)
        monkeypatch.setattr("app.services.observability_exporter.event_bus", fresh_bus)

        # 创建真实 ObservabilityExporter (注册 5 个事件处理器到 fresh_bus)
        ObservabilityExporter()

        # 仅启动 EventBus 消费循环, 不调用 exporter.start() (避免 60s 轮询和 DB 依赖)
        await fresh_bus.start()

        try:
            # 初始计数应为 0 (Counter 无数据)
            assert metrics.event_alerts_fired_total.collect() == []
            assert metrics.event_alerts_resolved_total.collect() == []
            assert metrics.event_alerts_escalated_total.collect() == []
            assert metrics.event_warnings_created_total.collect() == []
            assert metrics.event_reviews_submitted_total.collect() == []

            # 1. 发布 alert.fired 事件
            await fresh_bus.publish("alert.fired", {"alert_id": 1, "severity": "HIGH"})
            await asyncio.sleep(0.1)
            fired = metrics.event_alerts_fired_total.collect()
            assert len(fired) == 1
            assert fired[0][1] == 1.0

            # 2. 发布 alert.resolved 事件
            await fresh_bus.publish("alert.resolved", {"alert_id": 1})
            await asyncio.sleep(0.1)
            resolved = metrics.event_alerts_resolved_total.collect()
            assert len(resolved) == 1
            assert resolved[0][1] == 1.0

            # 3. 发布 alert.escalated 事件
            await fresh_bus.publish("alert.escalated", {"alert_id": 2})
            await asyncio.sleep(0.1)
            escalated = metrics.event_alerts_escalated_total.collect()
            assert len(escalated) == 1
            assert escalated[0][1] == 1.0

            # 4. 发布 warning.created 事件
            await fresh_bus.publish("warning.created", {"warning_id": 1, "user_id": 1})
            await asyncio.sleep(0.1)
            warnings = metrics.event_warnings_created_total.collect()
            assert len(warnings) == 1
            assert warnings[0][1] == 1.0

            # 5. 发布 review.submitted 事件
            await fresh_bus.publish("review.submitted", {"review_id": 1, "user_id": 1})
            await asyncio.sleep(0.1)
            reviews = metrics.event_reviews_submitted_total.collect()
            assert len(reviews) == 1
            assert reviews[0][1] == 1.0

            # 验证事件统计
            assert fresh_bus.events_published == 5
            assert fresh_bus.events_processed == 5
            assert fresh_bus.handler_errors == 0
        finally:
            await fresh_bus.stop()


class TestEventBusLatency:
    """EventBus 端到端延迟测试."""

    @pytest.mark.asyncio
    async def test_end_to_end_latency(self) -> None:
        """验证端到端延迟 < 5s (R-C 验收标准).

        实际单进程内延迟应远低于 1s, 验收阈值 5s 留充足余量.
        """
        processed_at: list[float] = []

        async def handler(data: dict) -> None:
            processed_at.append(time.monotonic())

        bus = EventBus(max_queue_size=100)
        bus.subscribe("alert.fired", handler)
        await bus.start()

        publish_time = time.monotonic()
        await bus.publish("alert.fired", {"alert_id": 1})

        # 等待处理完成 (最多 5s)
        deadline = publish_time + 5.0
        while not processed_at and time.monotonic() < deadline:
            await asyncio.sleep(0.01)

        await bus.stop()

        assert len(processed_at) == 1, "Event was not processed within 5s"
        latency = processed_at[0] - publish_time
        assert latency < 5.0, f"End-to-end latency {latency:.3f}s exceeds 5s threshold"
        # 单进程内延迟应远低于 1s
        assert (
            latency < 1.0
        ), f"End-to-end latency {latency:.3f}s exceeds 1s (in-process)"


class TestEventBusLifecycle:
    """EventBus 生命周期测试."""

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """测试重复调用 start() 是幂等的 (不会创建多个消费任务)."""
        bus = EventBus(max_queue_size=10)
        await bus.start()
        first_task = bus._consumer_task

        await bus.start()  # 幂等: 不应创建新任务
        assert bus._consumer_task is first_task

        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """测试在未启动状态下调用 stop() 不报错."""
        bus = EventBus(max_queue_size=10)
        # 未调用 start() 直接 stop(), 不应抛异常
        await bus.stop()
        assert bus._running is False
        assert bus._consumer_task is None

    @pytest.mark.asyncio
    async def test_publish_without_start_queues_event(self) -> None:
        """测试未启动时发布事件: 事件入队但不被消费."""
        bus = EventBus(max_queue_size=10)
        await bus.publish("alert.fired", {"id": 1})

        # 事件入队但未被消费
        assert bus.events_published == 1
        assert bus.events_processed == 0
        assert not bus._queue.empty()

        # 启动后应消费队列中的事件
        received: list[dict] = []

        async def handler(data: dict) -> None:
            received.append(data)

        bus.subscribe("alert.fired", handler)
        await bus.start()
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert bus.events_processed == 1

        await bus.stop()
