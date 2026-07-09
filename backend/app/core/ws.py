from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from jwt import PyJWTError
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.user import User

logger = logging.getLogger(__name__)

# P2-1: Redis pubsub channel 前缀.
# 完整 channel 格式: "ws:user:{user_id}",消息体为 JSON: {"node_id": "...", "message": {...}}
WS_PUBSUB_CHANNEL_PREFIX = "ws:user:"


class ConnectionManager:
    MAX_CONNECTIONS_PER_USER = 5

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}
        # M-Core-15 修复：使用 asyncio.Lock 保护 connections 字典的读写，
        # 防止多协程并发 connect 导致连接数统计错乱。
        self._lock = asyncio.Lock()
        # P2-1: 节点唯一标识,用于避免 pubsub 回环 (本节点发布的消息被本节点订阅后重复投递)
        self._node_id = uuid.uuid4().hex
        # P2-1: 后台 pubsub 订阅任务句柄
        self._pubsub_task: asyncio.Task | None = None

    async def connect(self, user_id: int, ws: WebSocket) -> bool:
        """尝试建立连接。如果用户连接数已达上限，返回False。"""
        async with self._lock:
            current_connections = self._connections.get(user_id, [])
            if len(current_connections) >= self.MAX_CONNECTIONS_PER_USER:
                logger.warning(
                    "WebSocket connection limit reached for user_id=%d (max=%d)",
                    user_id,
                    self.MAX_CONNECTIONS_PER_USER,
                )
                return False

            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(ws)
            try:
                from app.core.metrics import websocket_connections_active

                websocket_connections_active.inc()
            except Exception as exc:
                # P1-E 修复：监控指标采集失败必须记录日志，便于发现指标系统异常
                logger.warning("websocket_connections_active.inc failed: %s", exc)
            logger.info(
                "WebSocket connected for user_id=%d, total=%d",
                user_id,
                len(self._connections[user_id]),
            )
            return True

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id] = [
                w for w in self._connections[user_id] if w is not ws
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
            try:
                from app.core.metrics import websocket_connections_active

                websocket_connections_active.dec()
            except Exception as exc:
                # P1-E 修复：监控指标采集失败必须记录日志，便于发现指标系统异常
                logger.warning("websocket_connections_active.dec failed: %s", exc)
        logger.info("WebSocket disconnected for user_id=%d", user_id)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        """P2-1: 跨进程发送消息给指定用户的所有 WebSocket 连接.

        行为:
            1. 本地进程内立即投递 (覆盖本 worker 上的连接)
            2. 通过 Redis pubsub 发布到 ``ws:user:{user_id}`` channel,
               其他 FastAPI worker 的订阅者收到后投递给它们本地的连接.
            3. Redis 不可用时仅本地发送,保持现状行为 (降级).

        使用 node_id 区分消息 originator,避免本节点订阅到自己发布的消息后重复本地投递.

        典型场景:
            - Celery worker 调用 notify_warning: 本地 dict 为空 (Celery 不持有 WS),
              仅依赖 Redis publish 通知 FastAPI workers.
            - FastAPI worker 调用: 本地直接发送 + Redis publish 通知其他 workers.
        """
        # 步骤 1: 本地进程内投递 (覆盖本节点上的所有连接)
        await self._local_send_to_user(user_id, message)
        # 步骤 2: 通过 Redis pubsub 发布给其他 workers
        await self._publish_to_redis(user_id, message)

    async def _local_send_to_user(self, user_id: int, message: dict) -> None:
        """P2-1: 仅本进程内投递消息. 不触发 Redis pubsub."""
        connections = self._connections.get(user_id, [])
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(json.dumps(message, default=str, ensure_ascii=False))
            except Exception as exc:
                # L-06 修复：扩大异常捕获范围，避免未捕获异常导致后续连接无法收到消息
                # 常见异常：RuntimeError, WebSocketDisconnect, ConnectionClosedError, OSError 等
                logger.debug("WebSocket send failed for user_id=%d: %s", user_id, exc)
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def _publish_to_redis(self, user_id: int, message: dict) -> bool:
        """P2-1: 通过 Redis pubsub 发布消息. 失败时返回 False (调用方仅记录,不阻塞).

        使用共享 Redis 客户端 (app.core.cache.get_redis_client),复用连接池.
        """
        try:
            from app.core.cache import get_redis_client

            client = await get_redis_client()
            if client is None:
                # Redis 未配置或断路器打开 - 静默跳过,本地发送已经覆盖本 worker
                return False
            payload = json.dumps(
                {"node_id": self._node_id, "message": message},
                default=str,
                ensure_ascii=False,
            )
            await client.publish(f"{WS_PUBSUB_CHANNEL_PREFIX}{user_id}", payload)
            return True
        except Exception as exc:
            # Redis 操作失败 - 仅记录,不抛出. 本地发送已经完成,不影响本 worker 的连接.
            logger.debug("Redis pubsub publish failed for user_id=%d: %s", user_id, exc)
            return False

    async def broadcast(self, message: dict) -> None:
        """P2-1: 广播给所有在线用户 (跨进程)."""
        # 本地广播
        for user_id in list(self._connections.keys()):
            await self._local_send_to_user(user_id, message)
        # 跨进程广播: 发布到 ws:broadcast channel,订阅者收到后本地投递
        try:
            from app.core.cache import get_redis_client

            client = await get_redis_client()
            if client is None:
                return
            payload = json.dumps(
                {"node_id": self._node_id, "message": message, "broadcast": True},
                default=str,
                ensure_ascii=False,
            )
            await client.publish(f"{WS_PUBSUB_CHANNEL_PREFIX}broadcast", payload)
        except Exception as exc:
            logger.debug("Redis pubsub broadcast failed: %s", exc)

    async def start_pubsub_subscriber(self) -> None:
        """P2-1: 启动后台 pubsub 订阅任务 (应用启动时调用).

        订阅 ``ws:user:*`` pattern,收到消息后投递给本地连接.
        幂等: 多次调用只启动一个订阅任务.
        """
        if self._pubsub_task is not None and not self._pubsub_task.done():
            return
        self._pubsub_task = asyncio.create_task(self._pubsub_loop())
        logger.info("WebSocket pubsub subscriber started (node_id=%s)", self._node_id)

    async def stop_pubsub_subscriber(self) -> None:
        """P2-1: 停止 pubsub 订阅任务 (应用关闭时调用)."""
        if self._pubsub_task is None:
            return
        self._pubsub_task.cancel()
        try:
            await self._pubsub_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning(
                "WebSocket pubsub subscriber stop encountered error", exc_info=True
            )
        self._pubsub_task = None
        logger.info("WebSocket pubsub subscriber stopped")

    async def _pubsub_loop(self) -> None:
        """P2-1: 后台订阅循环. 自动重连,Redis 不可用时退避等待.

        错误处理策略:
            - Redis 不可用: 1 秒退避后重试
            - 订阅异常: 关闭当前 pubsub,1 秒后重连
            - 消息处理异常: 仅记录,不退出循环
        """
        from app.core.cache import get_redis_client

        logger.info("WebSocket pubsub loop started (node_id=%s)", self._node_id)
        while True:
            pubsub = None
            try:
                client = await get_redis_client()
                if client is None:
                    # Redis 未配置 - 等待并重试 (不抛异常,允许应用在无 Redis 时继续运行)
                    await asyncio.sleep(1.0)
                    continue
                pubsub = client.pubsub()
                # 使用 pattern subscribe,匹配所有 ws:user:* 频道 (包括 ws:user:broadcast)
                await pubsub.psubscribe(f"{WS_PUBSUB_CHANNEL_PREFIX}*")
                async for msg in pubsub.listen():
                    if msg.get("type") != "pmessage":
                        continue
                    try:
                        await self._handle_pubsub_message(msg)
                    except Exception:
                        logger.exception("WebSocket pubsub message handling failed")
            except asyncio.CancelledError:
                logger.info("WebSocket pubsub loop cancelled")
                break
            except Exception:
                logger.exception("WebSocket pubsub loop crashed, restarting in 1s")
                await asyncio.sleep(1.0)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass

    async def _handle_pubsub_message(self, msg: dict) -> None:
        """P2-1: 处理 pubsub 消息. 跳过本节点发布的消息 (避免回环)."""
        raw_data = msg.get("data")
        if raw_data is None:
            return
        # aioredis 返回的数据可能是 bytes 或 str,统一解码
        if isinstance(raw_data, (bytes, bytearray)):
            raw_data = raw_data.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "WebSocket pubsub received malformed payload: %r", raw_data[:200]
            )
            return
        node_id = payload.get("node_id")
        # 回环保护: 本节点发布的消息已经本地投递过,跳过
        if node_id == self._node_id:
            return
        message = payload.get("message")
        if message is None:
            return
        # broadcast 消息: 本地广播给所有用户
        if payload.get("broadcast"):
            for user_id in list(self._connections.keys()):
                await self._local_send_to_user(user_id, message)
            return
        # 点对点消息: 从 channel 名称提取 user_id
        channel = msg.get("channel")
        if isinstance(channel, (bytes, bytearray)):
            channel = channel.decode("utf-8", errors="replace")
        if isinstance(channel, str) and channel.startswith(WS_PUBSUB_CHANNEL_PREFIX):
            try:
                user_id = int(channel[len(WS_PUBSUB_CHANNEL_PREFIX) :])
            except ValueError:
                logger.warning("WebSocket pubsub invalid channel: %s", channel)
                return
            await self._local_send_to_user(user_id, message)

    @property
    def online_count(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


ws_manager = ConnectionManager()


def _normalize_websocket_token(token: str | None) -> str:
    candidate = token or ""
    if candidate.lower().startswith("bearer "):
        candidate = candidate[7:].strip()
    return candidate.strip()


async def _receive_auth_token(ws: WebSocket, timeout_seconds: float = 10.0) -> str:
    """接收客户端发送的认证 token。

    M8 修复：增加超时机制，防止攻击者建立连接后不发送认证消息占用资源。

    Args:
        ws: WebSocket 连接。
        timeout_seconds: 认证超时时间（秒），默认 10 秒。

    Raises:
        asyncio.TimeoutError: 认证超时。
        WebSocketDisconnect: 客户端断开连接。
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=timeout_seconds)
        data = json.loads(raw)
    except WebSocketDisconnect:
        raise
    except json.JSONDecodeError:
        return ""

    if data.get("type") != "auth":
        return ""
    return _normalize_websocket_token(data.get("token"))


async def websocket_endpoint(ws: WebSocket, user_id: int) -> None:
    # M8 修复：先检查 URL 参数中的 token（禁止通过 URL 传递），
    # 再 accept 连接，避免在认证前分配服务器资源
    if ws.query_params.get("token"):
        await ws.accept()
        await ws.close(code=4001, reason="Token禁止通过URL参数传递")
        return

    await ws.accept()

    try:
        # M8 修复：认证阶段增加 10 秒超时，防止 DoS 攻击
        token = await _receive_auth_token(ws, timeout_seconds=10.0)
    except asyncio.TimeoutError:
        await ws.close(code=4001, reason="认证超时")
        return
    except WebSocketDisconnect:
        return
    if not token:
        await ws.close(code=4001, reason="缺少认证Token")
        return

    try:
        token_data = decode_token(token)
        token_type = token_data.get("type")
        if token_type != "access":
            await ws.close(
                code=4001,
                reason=f"无效的Token类型: 需要access，实际为{token_type or 'unknown'}",
            )
            return
        if token_data.get("sub") != str(user_id):
            await ws.close(code=4001, reason="Token用户ID不匹配")
            return
    except (PyJWTError, ValueError, TypeError):
        await ws.close(code=4001, reason="无效的Token")
        return
    except Exception:
        logger.exception("websocket.auth.unexpected_error user_id=%s", user_id)
        await ws.close(code=4001, reason="WebSocket认证失败")
        return

    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.id == user_id)
        user = (await db.execute(stmt)).scalar_one_or_none()
        if user is None or user.status != "active":
            await ws.close(code=4003, reason="用户不存在或已被禁用")
            return

    if not await ws_manager.connect(user_id, ws):
        await ws.close(code=4009, reason="连接数已达上限，请稍后重试")
        return

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=300)
            except asyncio.TimeoutError:
                # P0-P2 修复：idle timeout 后必须从 ws_manager 移除连接，否则连接已关闭
                # 但仍保留在 _connections 字典中，导致内存泄漏和 online_count 统计错误
                ws_manager.disconnect(user_id, ws)
                await ws.close(code=4000, reason="idle timeout")
                break
            try:
                data = json.loads(raw)
                msg_type = data.get("type", "ping")
                if msg_type == "ping":
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "pong",
                                "ts": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    )
                else:
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"不支持的消息类型: {msg_type}",
                            },
                            ensure_ascii=False,
                        )
                    )
            except json.JSONDecodeError:
                await ws.send_text(
                    json.dumps(
                        {"type": "error", "message": "消息格式错误"}, ensure_ascii=False
                    )
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, ws)
    except Exception:
        logger.exception("websocket.runtime.error user_id=%s", user_id)
        ws_manager.disconnect(user_id, ws)


async def notify_warning(
    user_id: int, warning_id: int, risk_level: str, trigger_reason: str
) -> None:
    await ws_manager.send_to_user(
        user_id,
        {
            "type": "warning",
            "data": {
                "warning_id": warning_id,
                "risk_level": risk_level,
                "trigger_reason": trigger_reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )


async def notify_counselor(
    counselor_id: int, user_id: int, warning_id: int, risk_level: str
) -> None:
    await ws_manager.send_to_user(
        counselor_id,
        {
            "type": "counselor_warning",
            "data": {
                "warning_id": warning_id,
                "user_id": user_id,
                "risk_level": risk_level,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )


async def notify_task_progress(
    user_id: int,
    job_id: str,
    status: str,
    progress: int,
    job_type: str = "pdf",
    error: str | None = None,
) -> None:
    """推送异步任务进度到用户的所有 WebSocket 连接.

    Args:
        user_id: 接收进度的用户 ID
        job_id: 任务 ID (前端用于关联轮询/订阅)
        status: 任务状态 (queued | running | completed | failed)
        progress: 进度百分比 0-100
        job_type: 任务类型 (pdf | excel | training), 默认 pdf
        error: 失败时的错误信息
    """
    await ws_manager.send_to_user(
        user_id,
        {
            "type": "task_progress",
            "data": {
                "job_id": job_id,
                "job_type": job_type,
                "status": status,
                "progress": progress,
                "error": error,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )
