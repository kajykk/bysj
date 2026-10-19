from __future__ import annotations

import json

import pytest

from app.core import tenant_status
from app.core import ws as ws_module


class FakeWebSocket:
    def __init__(
        self,
        messages: list[str] | None = None,
        query_params: dict[str, str] | None = None,
    ):
        self.messages = list(messages or [])
        self.query_params = query_params or {}
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = (code, reason)

    async def receive_text(self):
        if not self.messages:
            from fastapi import WebSocketDisconnect

            raise WebSocketDisconnect()
        return self.messages.pop(0)

    async def send_text(self, payload: str):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_websocket_rejects_token_in_query_params():
    ws = FakeWebSocket(query_params={"token": "secret"})

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4001, "Token禁止通过URL参数传递")


@pytest.mark.asyncio
async def test_websocket_requires_first_auth_message():
    ws = FakeWebSocket(messages=['{"type":"ping"}'])

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4001, "缺少认证Token")


@pytest.mark.asyncio
async def test_websocket_accepts_token_from_first_auth_message(monkeypatch):
    ws = FakeWebSocket(messages=['{"type":"auth","token":"Bearer access-token"}'])

    monkeypatch.setattr(
        ws_module, "decode_token", lambda token: {"type": "access", "sub": "1"}
    )

    class _Result:
        def scalar_one_or_none(self):
            # REV-2026-10-20 (S7)：WS 握手现在会读 user.tenant_id 做租户封禁校验
            # （ws.py:461）。假对象必须补齐该属性，否则 AttributeError 会被外层
            # 兜底成 4503「服务暂不可用」，把一个测试夹具缺陷伪装成服务故障。
            return type("User", (), {"status": "active", "tenant_id": 1})()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, _stmt):
            return _Result()

    monkeypatch.setattr(ws_module, "AsyncSessionLocal", lambda: _Session())

    # S7：租户未封禁 ⇒ 放行（反向对照：与下方 suspended 用例配对，证明
    # 4003 不是无条件返回）。
    async def _not_suspended(db, tenant_id):
        return False

    monkeypatch.setattr(tenant_status, "is_tenant_suspended", _not_suspended)

    # M-Core-15 修复：connect 已改为 async，monkeypatch 需使用 async 函数
    async def _fake_connect(user_id, websocket):
        return True

    monkeypatch.setattr(ws_module.ws_manager, "connect", _fake_connect)

    # P0-FIX-2026-10-11: disconnect 已改为 async（加锁以消除与 connect 的 lost-update
    # 竞态），monkeypatch 需同步使用 async 函数，否则 `await None` 抛 TypeError。
    async def _fake_disconnect(user_id, websocket):
        return None

    monkeypatch.setattr(ws_module.ws_manager, "disconnect", _fake_disconnect)

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed is None


@pytest.mark.asyncio
async def test_websocket_rejects_suspended_tenant(monkeypatch):
    """REV-2026-10-20 (S7)：租户被封禁时，WS 握手必须被拒（4003）。

    背景：S7 已把「租户封禁」校验接入 WS 握手（ws.py:454-484），但
    《CODE_REVIEW_FIX_2026-10-20》§五.1 自记「WS 租户校验无自动化用例」。
    本条补齐：**封禁开关的价值在于「能真正止血」，而 WS 是高风险预警的推送
    通道** —— 漏掉它等于止血漏一路，且事后无法从回归集发现。

    反向对照：同文件 ``test_websocket_accepts_token_from_first_auth_message``
    走「未封禁 ⇒ 放行」分支；两条配对才能证明 4003 是**由封禁状态驱动**，
    而不是无条件返回。
    """
    ws = FakeWebSocket(messages=['{"type":"auth","token":"Bearer access-token"}'])

    monkeypatch.setattr(
        ws_module, "decode_token", lambda token: {"type": "access", "sub": "1"}
    )

    class _Result:
        def scalar_one_or_none(self):
            return type("User", (), {"status": "active", "tenant_id": 7})()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, _stmt):
            return _Result()

    monkeypatch.setattr(ws_module, "AsyncSessionLocal", lambda: _Session())

    async def _suspended(db, tenant_id):
        return True

    monkeypatch.setattr(tenant_status, "is_tenant_suspended", _suspended)

    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4003, "租户已暂停，请联系平台管理员")


# ── M2（ROUND_18）：握手阶段校验 jti 撤销 ────────────────────────────────


def _stub_ws_backend(monkeypatch, tenant_id: int = 1) -> None:
    """把握手后续依赖（DB / 租户状态 / 连接管理）换成最小可用桩。

    M2 的判据在 jti 检查上，撤销通过与否决定了是否走到这里；桩只负责让
    "通过撤销检查"的用例能走完全流程，不参与撤销语义。
    """

    class _Result:
        def scalar_one_or_none(self):
            return type("User", (), {"status": "active", "tenant_id": tenant_id})()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, _stmt):
            return _Result()

    monkeypatch.setattr(ws_module, "AsyncSessionLocal", lambda: _Session())

    async def _not_suspended(db, tid):
        return False

    monkeypatch.setattr(tenant_status, "is_tenant_suspended", _not_suspended)

    async def _connect(user_id, websocket):
        return True

    async def _disconnect(user_id, websocket):
        return None

    monkeypatch.setattr(ws_module.ws_manager, "connect", _connect)
    monkeypatch.setattr(ws_module.ws_manager, "disconnect", _disconnect)


@pytest.mark.asyncio
async def test_websocket_rejects_jti_revoked_after_logout(monkeypatch):
    """M2：登出撤销 access jti 后，同一 token 不得再建长连接。

    走真实链路：``create_access_token`` 签发 → ``revoke_token``（登出端点调用的
    同一原语，见 ``AuthService.logout``）写入 blocklist → 真实
    ``websocket_endpoint`` 在握手阶段读回。仅把缓存后端切成内存
    （``_get_redis_url → None``，单进程部署形态），**不替换**
    ``is_token_revoked`` —— 缺陷就在"少调一次撤销检查"，替身会把这一层抹掉。
    """
    from app.core import cache as cache_module
    from app.core.security import create_access_token, decode_token
    from app.core.token_blocklist import revoke_token

    monkeypatch.setattr(cache_module, "_get_redis_url", lambda: None)

    token = create_access_token({"sub": "1", "role": "user", "tenant_id": 1})
    jti = decode_token(token)["jti"]
    assert await revoke_token(jti, ttl=60) is True

    ws = FakeWebSocket(messages=[json.dumps({"type": "auth", "token": token})])
    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4001, "Token已被撤销")


@pytest.mark.asyncio
async def test_websocket_accepts_token_with_live_jti(monkeypatch):
    """反向对照：同一路径下未被撤销的 jti 仍然放行。

    与上一条配对，证明 4001 是**由撤销状态驱动**，而不是加了检查就无条件拒。
    """
    from app.core import cache as cache_module
    from app.core.security import create_access_token

    monkeypatch.setattr(cache_module, "_get_redis_url", lambda: None)
    _stub_ws_backend(monkeypatch)

    token = create_access_token({"sub": "1", "role": "user", "tenant_id": 1})
    ws = FakeWebSocket(messages=[json.dumps({"type": "auth", "token": token})])
    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed is None


@pytest.mark.asyncio
async def test_websocket_fails_closed_when_blocklist_unavailable(monkeypatch):
    """撤销检查基础设施不可用 ⇒ 4503（与 HTTP 侧 503 同语义）。

    若这里放宽成"查不到就放行"，登出撤销会在 Redis 抖动期间整体失效，
    而长连接正是危机预警的推送通道 —— 这是本任务要求 fail-closed 的原因。
    """
    from app.core import token_blocklist
    from app.core.cache import CacheUnavailableError

    async def _boom(_jti: str) -> bool:
        raise CacheUnavailableError("[cache] redis down")

    monkeypatch.setattr(token_blocklist, "is_token_revoked", _boom)
    monkeypatch.setattr(
        ws_module,
        "decode_token",
        lambda token: {"type": "access", "sub": "1", "jti": "j-r18-boom"},
    )

    ws = FakeWebSocket(messages=[json.dumps({"type": "auth", "token": "Bearer t"})])
    await ws_module.websocket_endpoint(ws, user_id=1)

    assert ws.accepted is True
    assert ws.closed == (4503, "认证服务暂时不可用，请稍后重试")
