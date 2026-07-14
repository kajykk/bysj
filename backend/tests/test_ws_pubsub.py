"""P2-1: WebSocket 多 worker 支持 (Redis pubsub) 单元测试.

覆盖场景:
    - send_to_user: 本地发送 + Redis publish 双触发
    - Redis 不可用时降级为仅本地发送 (不抛异常)
    - _handle_pubsub_message 回环保护 (跳过本节点消息)
    - _handle_pubsub_message 处理点对点 / broadcast / bytes / 畸形 payload
    - start_pubsub_subscriber / stop_pubsub_subscriber 生命周期
    - 跨进程消息流端到端模拟 (两个 ConnectionManager 共享 mock Redis)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.ws import WS_PUBSUB_CHANNEL_PREFIX, ConnectionManager


class _FakeWebSocket:
    """轻量 WebSocket mock,记录所有 send_text 调用."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, data: str) -> None:
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        self.sent.append(data)


class _FakePubSub:
    """模拟 aioredis pubsub 对象,可控的消息队列."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self.closed = False
        self.subscribed_patterns: list[str] = []

    async def psubscribe(self, *patterns: str) -> None:
        self.subscribed_patterns.extend(patterns)

    async def listen(self):
        while not self.closed:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if self.closed:
                    break
                continue
            if msg is None:
                break
            yield msg

    async def close(self) -> None:
        self.closed = True
        await self._queue.put(None)

    # aioredis 5.x 使用 aclose() 替代 close()
    async def aclose(self) -> None:
        await self.close()

    async def push_message(self, msg: dict) -> None:
        await self._queue.put(msg)


class _FakeRedisClient:
    """模拟 aioredis Redis 客户端,记录 publish 调用,提供 pubsub() 工厂.

    publish 时同时将消息推入 pubsub 队列,模拟真实 Redis pub/sub 行为:
    publish(channel, payload) -> 所有订阅匹配 pattern 的 subscriber 收到 pmessage.
    """

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self._pubsub = _FakePubSub()

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        # 模拟 Redis pubsub: 订阅者收到 pmessage
        await self._pubsub.push_message(
            {
                "type": "pmessage",
                "pattern": f"{WS_PUBSUB_CHANNEL_PREFIX}*",
                "channel": channel,
                "data": payload,
            }
        )
        return 1

    def pubsub(self) -> _FakePubSub:
        return self._pubsub

    async def aclose(self) -> None:
        await self._pubsub.close()


@pytest.fixture
def fake_ws_a() -> _FakeWebSocket:
    return _FakeWebSocket()


@pytest.fixture
def fake_ws_b() -> _FakeWebSocket:
    return _FakeWebSocket()


@pytest.fixture
def reset_ws_manager():
    """重置全局 ws_manager 的连接字典,确保测试隔离."""
    from app.core.ws import ws_manager

    old_connections = ws_manager._connections
    ws_manager._connections = {}
    yield ws_manager
    ws_manager._connections = old_connections


class TestSendToUserLocalAndPublish:
    """P2-1: send_to_user 双通道触发 (本地 + Redis publish)."""

    @pytest.mark.asyncio
    async def test_send_to_user_local_delivery_and_redis_publish(
        self, reset_ws_manager, fake_ws_a
    ):
        """send_to_user 同时本地投递 + Redis publish."""
        manager = reset_ws_manager
        await manager.connect(1, fake_ws_a)

        fake_redis = _FakeRedisClient()
        with patch(
            "app.core.cache.get_redis_client", AsyncMock(return_value=fake_redis)
        ):
            await manager.send_to_user(1, {"type": "warning", "data": {"id": 42}})

        # 本地投递: WebSocket 收到消息
        assert len(fake_ws_a.sent) == 1
        msg = json.loads(fake_ws_a.sent[0])
        assert msg["type"] == "warning"
        assert msg["data"]["id"] == 42

        # Redis publish: 调用一次,channel = ws:user:1
        assert len(fake_redis.published) == 1
        channel, payload = fake_redis.published[0]
        assert channel == f"{WS_PUBSUB_CHANNEL_PREFIX}1"
        payload_dict = json.loads(payload)
        assert payload_dict["node_id"] == manager._node_id
        assert payload_dict["message"]["type"] == "warning"

    @pytest.mark.asyncio
    async def test_send_to_user_redis_unavailable_falls_back_to_local(
        self, reset_ws_manager, fake_ws_a
    ):
        """Redis 不可用时 (get_redis_client 返回 None) 仅本地发送,不抛异常."""
        manager = reset_ws_manager
        await manager.connect(2, fake_ws_a)

        with patch("app.core.cache.get_redis_client", AsyncMock(return_value=None)):
            # 不应抛异常
            await manager.send_to_user(2, {"type": "ping"})

        # 本地仍然收到消息
        assert len(fake_ws_a.sent) == 1
        assert json.loads(fake_ws_a.sent[0])["type"] == "ping"

    @pytest.mark.asyncio
    async def test_send_to_user_redis_exception_does_not_block_local(
        self, reset_ws_manager, fake_ws_a
    ):
        """Redis publish 抛异常时本地发送仍然完成."""
        manager = reset_ws_manager
        await manager.connect(3, fake_ws_a)

        async def _raise(*args, **kwargs):
            raise ConnectionError("Redis is down")

        with patch("app.core.cache.get_redis_client", AsyncMock(side_effect=_raise)):
            await manager.send_to_user(3, {"type": "ping"})

        # 本地仍然收到消息 (Redis 异常被吞掉)
        assert len(fake_ws_a.sent) == 1

    @pytest.mark.asyncio
    async def test_send_to_user_unknown_user_still_publishes(self, reset_ws_manager):
        """本地无该用户连接时,仍尝试 publish (Celery 跨进程场景)."""
        manager = reset_ws_manager
        # 不 connect 任何 WebSocket,模拟 Celery worker 调用

        fake_redis = _FakeRedisClient()
        with patch(
            "app.core.cache.get_redis_client", AsyncMock(return_value=fake_redis)
        ):
            await manager.send_to_user(99, {"type": "warning"})

        # 本地无连接,但 publish 仍调用一次
        assert len(fake_redis.published) == 1
        assert fake_redis.published[0][0] == f"{WS_PUBSUB_CHANNEL_PREFIX}99"


class TestHandlePubsubMessage:
    """P2-1: _handle_pubsub_message 消息处理逻辑."""

    @pytest.mark.asyncio
    async def test_skip_own_node_message_avoids_loopback(
        self, reset_ws_manager, fake_ws_a
    ):
        """本节点发布的消息 (node_id 匹配) 被跳过,避免回环."""
        manager = reset_ws_manager
        await manager.connect(1, fake_ws_a)

        msg = {
            "type": "pmessage",
            "pattern": f"{WS_PUBSUB_CHANNEL_PREFIX}*",
            "channel": f"{WS_PUBSUB_CHANNEL_PREFIX}1",
            "data": json.dumps(
                {"node_id": manager._node_id, "message": {"type": "warning"}}
            ),
        }
        await manager._handle_pubsub_message(msg)

        # 不应投递 (回环保护)
        assert len(fake_ws_a.sent) == 0

    @pytest.mark.asyncio
    async def test_other_node_message_delivered_locally(
        self, reset_ws_manager, fake_ws_a
    ):
        """其他节点发布的消息被本地投递."""
        manager = reset_ws_manager
        await manager.connect(5, fake_ws_a)

        msg = {
            "type": "pmessage",
            "pattern": f"{WS_PUBSUB_CHANNEL_PREFIX}*",
            "channel": f"{WS_PUBSUB_CHANNEL_PREFIX}5",
            "data": json.dumps(
                {
                    "node_id": "other-node-id",
                    "message": {"type": "warning", "data": {"id": 1}},
                }
            ),
        }
        await manager._handle_pubsub_message(msg)

        assert len(fake_ws_a.sent) == 1
        delivered = json.loads(fake_ws_a.sent[0])
        assert delivered["type"] == "warning"
        assert delivered["data"]["id"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_message_delivered_to_all_local_users(
        self, reset_ws_manager, fake_ws_a, fake_ws_b
    ):
        """broadcast 消息被投递给本地所有在线用户."""
        manager = reset_ws_manager
        await manager.connect(10, fake_ws_a)
        await manager.connect(20, fake_ws_b)

        msg = {
            "type": "pmessage",
            "pattern": f"{WS_PUBSUB_CHANNEL_PREFIX}*",
            "channel": f"{WS_PUBSUB_CHANNEL_PREFIX}broadcast",
            "data": json.dumps(
                {
                    "node_id": "other-node-id",
                    "broadcast": True,
                    "message": {"type": "system"},
                }
            ),
        }
        await manager._handle_pubsub_message(msg)

        assert len(fake_ws_a.sent) == 1
        assert len(fake_ws_b.sent) == 1
        assert json.loads(fake_ws_a.sent[0])["type"] == "system"

    @pytest.mark.asyncio
    async def test_bytes_data_decoded_correctly(self, reset_ws_manager, fake_ws_a):
        """aioredis 返回 bytes 数据时正确解码."""
        manager = reset_ws_manager
        await manager.connect(7, fake_ws_a)

        msg = {
            "type": "pmessage",
            "channel": f"{WS_PUBSUB_CHANNEL_PREFIX}7".encode("utf-8"),
            "data": json.dumps(
                {"node_id": "other", "message": {"type": "ping"}}
            ).encode("utf-8"),
        }
        await manager._handle_pubsub_message(msg)

        assert len(fake_ws_a.sent) == 1
        assert json.loads(fake_ws_a.sent[0])["type"] == "ping"

    @pytest.mark.asyncio
    async def test_malformed_payload_does_not_raise(self, reset_ws_manager, fake_ws_a):
        """畸形 payload 不抛异常,仅记录日志."""
        manager = reset_ws_manager
        await manager.connect(8, fake_ws_a)

        msg = {
            "type": "pmessage",
            "channel": f"{WS_PUBSUB_CHANNEL_PREFIX}8",
            "data": "not-json-at-all",
        }
        # 不应抛异常
        await manager._handle_pubsub_message(msg)
        assert len(fake_ws_a.sent) == 0

    @pytest.mark.asyncio
    async def test_invalid_channel_user_id_skipped(self, reset_ws_manager, fake_ws_a):
        """channel 名称中 user_id 非数字时跳过."""
        manager = reset_ws_manager
        await manager.connect(1, fake_ws_a)

        msg = {
            "type": "pmessage",
            "channel": f"{WS_PUBSUB_CHANNEL_PREFIX}not-a-number",
            "data": json.dumps({"node_id": "other", "message": {"type": "ping"}}),
        }
        await manager._handle_pubsub_message(msg)
        assert len(fake_ws_a.sent) == 0

    @pytest.mark.asyncio
    async def test_none_data_skipped(self, reset_ws_manager):
        """data 为 None 时静默跳过."""
        manager = reset_ws_manager
        await manager._handle_pubsub_message(
            {"type": "pmessage", "channel": "ws:user:1", "data": None}
        )


class TestPubsubLifecycle:
    """P2-1: start_pubsub_subscriber / stop_pubsub_subscriber 生命周期."""

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, reset_ws_manager):
        """多次调用 start 只启动一个订阅任务."""
        manager = reset_ws_manager

        async def _mock_get_redis_client():
            return None  # 让 _pubsub_loop 进入 sleep 分支,不真实订阅

        with patch("app.core.cache.get_redis_client", _mock_get_redis_client), patch(
    "app.core.cache.get_redis_pubsub_client", _mock_get_redis_client
):
            await manager.start_pubsub_subscriber()
            task1 = manager._pubsub_task
            assert task1 is not None
            assert not task1.done()

            # 再次调用不应创建新任务
            await manager.start_pubsub_subscriber()
            assert manager._pubsub_task is task1

        await manager.stop_pubsub_subscriber()
        assert manager._pubsub_task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_noop(self, reset_ws_manager):
        """未启动时调用 stop 不抛异常."""
        manager = reset_ws_manager
        assert manager._pubsub_task is None
        await manager.stop_pubsub_subscriber()  # 不应抛异常
        assert manager._pubsub_task is None

    @pytest.mark.asyncio
    async def test_stop_cancels_running_task(self, reset_ws_manager):
        """stop 取消正在运行的订阅任务."""
        manager = reset_ws_manager

        async def _mock_get_redis_client():
            return None

        with patch("app.core.cache.get_redis_client", _mock_get_redis_client), patch(
    "app.core.cache.get_redis_pubsub_client", _mock_get_redis_client
):
            await manager.start_pubsub_subscriber()
            assert manager._pubsub_task is not None
            await manager.stop_pubsub_subscriber()
            assert manager._pubsub_task is None
            # 任务应已取消完成
            # (退出 _pubsub_loop 后,CancelledError 被捕获)


class TestCrossProcessMessageFlow:
    """P2-1: 端到端跨进程消息流模拟.

    模拟两个 FastAPI worker 进程 (manager_a, manager_b) + 一个 Celery worker (manager_c)
    共享同一 Redis (fake_redis). 验证 Celery 发送的告警能到达任意 worker 上的连接.
    """

    @pytest.mark.asyncio
    async def test_celery_notify_reaches_fastapi_worker(
        self, reset_ws_manager, fake_ws_a
    ):
        """Celery worker (无本地连接) 通过 Redis 通知 FastAPI worker 上的连接."""
        fastapi_manager = reset_ws_manager
        await fastapi_manager.connect(100, fake_ws_a)

        # Celery worker 使用独立的 ConnectionManager (无本地连接)
        celery_manager = ConnectionManager()

        # 共享同一个 fake_redis
        fake_redis = _FakeRedisClient()

        async def _fake_get_redis():
            return fake_redis

        # FastAPI worker 启动订阅器
        with patch("app.core.cache.get_redis_client", _fake_get_redis), patch(
            "app.core.cache.get_redis_pubsub_client", _fake_get_redis
        ):
            await fastapi_manager.start_pubsub_subscriber()
            try:
                # 给订阅器一点时间完成 psubscribe
                await asyncio.sleep(0.05)

                # Celery 调用 send_to_user (本地无连接,仅依赖 Redis publish)
                with patch("app.core.cache.get_redis_client", _fake_get_redis):
                    await celery_manager.send_to_user(
                        100, {"type": "warning", "data": {"id": 1}}
                    )

                # 等待 pubsub 消息投递
                deadline = asyncio.get_event_loop().time() + 1.0
                while not fake_ws_a.sent and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.02)

                assert len(fake_ws_a.sent) == 1
                msg = json.loads(fake_ws_a.sent[0])
                assert msg["type"] == "warning"
                assert msg["data"]["id"] == 1
            finally:
                await fastapi_manager.stop_pubsub_subscriber()

    @pytest.mark.asyncio
    async def test_no_loopback_when_same_node_publishes(
        self, reset_ws_manager, fake_ws_a
    ):
        """同一节点的 send_to_user 不会导致本地连接收到两次消息.

        send_to_user 时本地已经发送一次,pubsub 回环时被 node_id 检查跳过.
        """
        manager = reset_ws_manager
        await manager.connect(200, fake_ws_a)

        fake_redis = _FakeRedisClient()

        async def _fake_get_redis():
            return fake_redis

        with patch("app.core.cache.get_redis_client", _fake_get_redis), patch(
            "app.core.cache.get_redis_pubsub_client", _fake_get_redis
        ):
            await manager.start_pubsub_subscriber()
            try:
                await asyncio.sleep(0.05)  # 等待 psubscribe 完成

                # 同一节点调用 send_to_user
                await manager.send_to_user(200, {"type": "ping"})

                # 等待可能的回环投递
                await asyncio.sleep(0.2)

                # 只应收到一次 (本地发送),pubsub 回环应被跳过
                assert len(fake_ws_a.sent) == 1
            finally:
                await manager.stop_pubsub_subscriber()

    @pytest.mark.asyncio
    async def test_broadcast_reaches_other_workers(
        self, reset_ws_manager, fake_ws_a, fake_ws_b
    ):
        """broadcast 跨进程: manager_a 广播, manager_b 上的连接也收到."""
        manager_a = reset_ws_manager
        await manager_a.connect(300, fake_ws_a)

        manager_b = ConnectionManager()
        await manager_b.connect(301, fake_ws_b)

        fake_redis = _FakeRedisClient()

        async def _fake_get_redis():
            return fake_redis

        # manager_b 启动订阅器
        with patch("app.core.cache.get_redis_client", _fake_get_redis), patch(
            "app.core.cache.get_redis_pubsub_client", _fake_get_redis
        ):
            await manager_b.start_pubsub_subscriber()
            try:
                await asyncio.sleep(0.05)

                # manager_a 广播
                with patch("app.core.cache.get_redis_client", _fake_get_redis):
                    await manager_a.broadcast({"type": "system"})

                deadline = asyncio.get_event_loop().time() + 1.0
                while not fake_ws_b.sent and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.02)

                # manager_a 本地连接收到
                assert len(fake_ws_a.sent) == 1
                # manager_b 通过 pubsub 收到
                assert len(fake_ws_b.sent) == 1
                assert json.loads(fake_ws_b.sent[0])["type"] == "system"
            finally:
                await manager_b.stop_pubsub_subscriber()
