"""P0-FIX-2026-10-11: ConnectionManager 连接注销的并发安全与幂等性。

背景（来自 2026-10-11 全量源码审查）：

``ConnectionManager.disconnect`` 原先是**同步** ``def`` 且**不加锁**，而 ``connect``
在 ``async with self._lock`` 内做 ``self._connections[user_id].append(ws)``。

其中**可在单事件循环内稳定复现**的缺陷是指标递减不幂等：原实现只要 ``user_id``
仍在字典里就 ``websocket_connections_active.dec()``，即使本次并未真正移除任何连接。
``_local_send_to_user`` 标记死连接后调用一次，``websocket_endpoint`` 的收尾分支
（WebSocketDisconnect / 通用异常 / idle timeout）会再调用一次 —— 同一 ``ws`` 被
``disconnect`` 两次时必然重复递减，``websocket_connections_active`` 一路走负，
进而让 ``max_global_connections`` 的判满逻辑提前触发，**永久拒绝所有新连接**。

``connect``/``disconnect`` 的互斥在单事件循环内不是必需的（``disconnect`` 体内无
``await``，本身是原子的），但一旦从 ``asyncio.to_thread`` 或 Celery 侧另一个事件
循环（``app/core/celery_async.py::get_celery_loop``）调用同一单例，
``asyncio.Lock`` 的 ``_waiters`` 就不是线程安全的，届时会出现真正的 lost update。
因此本修复同时保留「async + 加锁」作为防御，但**下面只对可稳定复现的部分做断言**。
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.ws import ConnectionManager


class _FakeWS:
    """最小 WebSocket 替身，只需支持 send_text。"""

    def __init__(self, tag: str = "") -> None:
        self.tag = tag
        self.sent: list[str] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(data)


def _make_manager() -> ConnectionManager:
    mgr = ConnectionManager()
    # 放宽上限，避免测试被全局/单用户连接上限干扰
    mgr.max_connections_per_user = 1000
    mgr.max_global_connections = 1000
    return mgr


@pytest.mark.asyncio
async def test_disconnect_is_coroutine_function():
    """disconnect 必须是协程函数 —— 否则调用方无法 await，加锁也就无从谈起。"""
    assert asyncio.iscoroutinefunction(
        ConnectionManager.disconnect
    ), "disconnect 必须是 async def，调用方已在 await"


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_no_double_decrement(monkeypatch):
    """同一 ws 被 disconnect 两次时，指标只能递减一次。

    这是原实现在单事件循环内即可稳定复现的缺陷：第二次 disconnect 时 ``user_id``
    仍在 ``_connections`` 里（该用户还有别的连接），于是重复 ``dec()``。
    """
    mgr = _make_manager()
    calls: list[str] = []

    class _Gauge:
        def inc(self, amount: float = 1) -> None:
            calls.append("inc")

        def dec(self, amount: float = 1) -> None:
            calls.append("dec")

    import app.core.ws as ws_module

    monkeypatch.setattr(
        ws_module,
        "websocket_connections_active",
        _Gauge(),
        raising=False,
    )
    # connect 内部是延迟导入 app.core.metrics，这里一并打桩
    import app.core.metrics as metrics_module

    monkeypatch.setattr(
        metrics_module, "websocket_connections_active", _Gauge(), raising=False
    )

    ws1, ws2 = _FakeWS("1"), _FakeWS("2")
    await mgr.connect(1, ws1)
    await mgr.connect(1, ws2)

    await mgr.disconnect(1, ws1)
    first_pass = list(calls)
    await mgr.disconnect(1, ws1)  # 重复调用：应为空操作
    second_pass = list(calls)

    assert [
        c for c in first_pass if c == "dec"
    ] == ["dec"], f"首次 disconnect 应递减一次，实际: {first_pass}"
    assert (
        len([c for c in second_pass if c == "dec"]) == 1
    ), f"重复的 disconnect 不应再次递减（幂等），实际累计: {second_pass}"

    live = mgr._connections.get(1, [])
    assert ws1 not in live and ws2 in live, "ws1 应被移除，ws2 应保留"


@pytest.mark.asyncio
async def test_disconnect_removes_only_target_connection():
    """多连接场景下 disconnect 只移除目标 ws，不误伤同用户的其它连接。"""
    mgr = _make_manager()
    ws1, ws2, ws3 = _FakeWS("1"), _FakeWS("2"), _FakeWS("3")
    for w in (ws1, ws2, ws3):
        await mgr.connect(7, w)

    await mgr.disconnect(7, ws2)

    live = mgr._connections[7]
    assert live == [ws1, ws3], f"应只剩 ws1/ws3，实际: {[w.tag for w in live]}"


@pytest.mark.asyncio
async def test_disconnect_last_connection_cleans_up_user_key():
    """移除用户最后一条连接时，必须从字典中删除该 user_id（否则空列表泄漏）。"""
    mgr = _make_manager()
    ws1 = _FakeWS("1")
    await mgr.connect(9, ws1)
    await mgr.disconnect(9, ws1)

    assert 9 not in mgr._connections, "用户最后一条连接移除后应删除 user_id 键"
    assert mgr.online_count == 0


@pytest.mark.asyncio
async def test_concurrent_connect_and_disconnect_no_lost_update():
    """并发 connect / disconnect 不得丢失新建立的连接（防御性断言）。

    说明：在单事件循环内 disconnect 无 await，本身是原子的，因此本用例在修复前
    也可能通过。保留它是为了在将来引入 ``to_thread`` / 多事件循环调用时第一时间
    暴露 lost update。
    """
    mgr = _make_manager()
    ws_a = _FakeWS("a")
    await mgr.connect(1, ws_a)

    new_conns = [_FakeWS(f"n{i}") for i in range(20)]
    stale = [_FakeWS(f"s{i}") for i in range(10)]  # 从未 connect 过

    await asyncio.gather(
        *[mgr.connect(1, w) for w in new_conns],
        *[mgr.disconnect(1, w) for w in stale],
    )

    live = mgr._connections[1]
    assert ws_a in live, "原有连接被误删"
    for w in new_conns:
        assert w in live, "并发新建的连接被 disconnect 的旧快照覆盖（lost update）"
    for w in stale:
        assert w not in live
