from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from jwt import PyJWTError

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.user import User

logger = logging.getLogger(__name__)


class ConnectionManager:
    MAX_CONNECTIONS_PER_USER = 5

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}

    def connect(self, user_id: int, ws: WebSocket) -> bool:
        """尝试建立连接。如果用户连接数已达上限，返回False。"""
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
        logger.info("WebSocket connected for user_id=%d, total=%d", user_id, len(self._connections[user_id]))
        return True

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id] = [w for w in self._connections[user_id] if w is not ws]
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
        connections = self._connections.get(user_id, [])
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(json.dumps(message, default=str, ensure_ascii=False))
            except (RuntimeError, WebSocketDisconnect):
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast(self, message: dict) -> None:
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, message)

    @property
    def online_count(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


ws_manager = ConnectionManager()


def _normalize_websocket_token(token: str | None) -> str:
    candidate = token or ""
    if candidate.lower().startswith("bearer "):
        candidate = candidate[7:].strip()
    return candidate.strip()


async def _receive_auth_token(ws: WebSocket) -> str:
    try:
        raw = await ws.receive_text()
        data = json.loads(raw)
    except WebSocketDisconnect:
        raise
    except json.JSONDecodeError:
        return ""

    if data.get("type") != "auth":
        return ""
    return _normalize_websocket_token(data.get("token"))


async def websocket_endpoint(ws: WebSocket, user_id: int) -> None:
    await ws.accept()
    if ws.query_params.get("token"):
        await ws.close(code=4001, reason="Token禁止通过URL参数传递")
        return

    try:
        token = await _receive_auth_token(ws)
    except WebSocketDisconnect:
        return
    if not token:
        await ws.close(code=4001, reason="缺少认证Token")
        return

    try:
        token_data = decode_token(token)
        token_type = token_data.get("type")
        if token_type != "access":
            await ws.close(code=4001, reason=f"无效的Token类型: 需要access，实际为{token_type or 'unknown'}")
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

    if not ws_manager.connect(user_id, ws):
        await ws.close(code=4009, reason="连接数已达上限，请稍后重试")
        return

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=300)
            except asyncio.TimeoutError:
                await ws.close(code=4000, reason="idle timeout")
                break
            try:
                data = json.loads(raw)
                msg_type = data.get("type", "ping")
                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()}))
                else:
                    await ws.send_text(json.dumps({"type": "error", "message": f"不支持的消息类型: {msg_type}"}, ensure_ascii=False))
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "消息格式错误"}, ensure_ascii=False))
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, ws)
    except Exception:
        logger.exception("websocket.runtime.error user_id=%s", user_id)
        ws_manager.disconnect(user_id, ws)


async def notify_warning(user_id: int, warning_id: int, risk_level: str, trigger_reason: str) -> None:
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


async def notify_counselor(counselor_id: int, user_id: int, warning_id: int, risk_level: str) -> None:
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
