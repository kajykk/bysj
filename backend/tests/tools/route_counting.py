"""有效路由计数 —— 跨 fastapi 版本同形的 `app.routes` 读数（ROUND_22 / T4）。

为什么需要这一层
----------------
2026-10-21 实测（CI `backend-coverage` 红项复盘）：CI 用 `requirements.txt`
（无上界）装到 **fastapi 0.151.0 + starlette 1.9.0** 后，`include_router()`
不再把子路由扁平拷贝进 `app.routes`，而是往 `routes` 里挂一个
`_IncludedRouter` 标记对象（带 `original_router` 属性），请求匹配时再递归
展开。于是「数 `app.routes` 里 `isinstance(r, APIRoute)` 的个数」在新版本下
只剩 `app/main.py` 自注册的部分：

    fastapi 0.135.3（本地 venv 实测）  flat=206 REST + 3 WS（include 已扁平化）
    fastapi 0.151.0（影子安装实测）    flat=  5 REST + 3 WS（3 个 _IncludedRouter 标记）

同一个交付物在两个依赖版本下读出两个数 —— 以此为准的闸门必然随版本漂移
（CI 红项正是如此：子进程隔离解决了进程内污染，却没解决表示变更）。

本模块把「运行时真实注册的路由」定义为**有效路由**（effective routes）：
沿 `_IncludedRouter.original_router`（以及 Mount 类对象的 `.routes`）递归
展开后得到的路由集合。该定义在两个版本下同形（实测）：

    0.135.3：flat=206/3，effective=206/3（展开是恒等变换，无标记可展开）
    0.151.0：flat= 5/3，effective=206/3（展开 3 个顶层标记及其嵌套标记）

即 README 声称的「运行时 206 个 REST 端点 + 3 个 WebSocket」本身是版本
稳定的事实，旧指针方法只是被新表示打破。两个 fastapi 大版本下 docs 路由
（`/openapi.json`、`/docs`、`/redoc`、`/swagger-redirect`）都是普通
starlette `Route`（各 4 条），不计入 REST/WS，进 `unknown` 桶留痕 ——
不静默丢弃，也不冒充端点。

失败策略：数不出来就说数不出来。嵌套超过 `_MAX_DEPTH` 层直接抛错，
**不返回 0、不返回部分读数**。
"""

from __future__ import annotations

import typing

from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute

# 真实嵌套深度：app → api_router → 子路由 ≈ 2~3 层；32 层足够宽容，
# 超过即判定为异常结构（如自引用标记），抛错而不是静默截断。
_MAX_DEPTH = 32


def iter_effective_routes(
    routes: typing.Iterable[typing.Any], *, _depth: int = 0
) -> typing.Iterator[typing.Any]:
    """展开 include 标记 / Mount，产出有效路由。

    两种「容器」形状都要认：
    - fastapi >= 0.151 的 `_IncludedRouter`：只有 `original_router` 一个属性
      被展开契约用到（鸭子类型，不 import 私有类）；
    - starlette `Mount` / `Host`：带 `.routes` 的子路由表。

    不按 id 去重：同一 router 被 include 两次时，旧版 fastapi 会在
    `app.routes` 里留下两份扁平路由（匹配时前者生效），展开也应数两份 ——
    否则两个版本的读数会再次分叉。
    """
    if _depth > _MAX_DEPTH:
        raise RuntimeError(
            f"路由嵌套超过 {_MAX_DEPTH} 层，判定为异常结构（如自引用 include）；"
            "不返回 0、不返回部分读数"
        )
    for route in routes:
        marker_router = getattr(route, "original_router", None)
        if marker_router is not None:
            yield from iter_effective_routes(marker_router.routes, _depth=_depth + 1)
            continue
        nested = getattr(route, "routes", None)
        if nested is not None and not isinstance(route, (APIRoute, WebSocketRoute)):
            yield from iter_effective_routes(nested, _depth=_depth + 1)
            continue
        yield route


def count_app_routes(app: typing.Any) -> dict[str, int]:
    """数一个 ASGI 应用的有效路由。

    Args:
        app: 任何带 `.routes` 的对象（FastAPI app；测试里用 SimpleNamespace）。

    Returns:
        ``{"rest": int, "ws": int, "unknown": int, "markers": int}``。
        ``markers`` 只数**顶层** `app.routes` 里的 include 标记（0.135 为 0、
        0.151 为 3），用于在 CI 日志里留证「展开确实发生过」；不参与判据。
    """
    routes = list(app.routes)
    markers = sum(
        1 for route in routes if getattr(route, "original_router", None) is not None
    )
    rest = ws = unknown = 0
    for route in iter_effective_routes(routes):
        if isinstance(route, APIRoute):
            rest += 1
        elif isinstance(route, WebSocketRoute):
            ws += 1
        else:
            unknown += 1
    return {"rest": rest, "ws": ws, "unknown": unknown, "markers": markers}
