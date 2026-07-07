from __future__ import annotations

import logging

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_trusted_proxy_set() -> set[str]:
    """解析配置的受信代理 IP 集合。"""
    raw = settings.trusted_proxies
    if not raw:
        return set()
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def get_real_client_ip(request: Request) -> str:
    """获取真实客户端 IP。

    M5 修复：在反向代理（Nginx/ALB）后部署时，``request.client.host`` 始终是代理 IP，
    所有用户共享同一个限流桶，导致限流失效。本函数解析 ``X-Forwarded-For`` 头获取真实 IP。

    P0-S2 修复：原实现直接信任 X-Forwarded-For 头的第一个 IP，攻击者可伪造该头
    每次使用不同 IP 绕过限流。现在仅当直接连接来自受信代理（TRUSTED_PROXIES 配置）
    时才解析 X-Forwarded-For，否则使用直接连接 IP。

    安全说明：
    - 从右向左遍历 X-Forwarded-For，跳过所有受信代理 IP，取第一个非受信 IP 作为真实客户端 IP
    - 仅受信代理的请求才会解析 X-Forwarded-For，防止客户端伪造
    - 若未配置受信代理或头不存在，回退到 ``request.client.host``
    - 生产环境应配置 TRUSTED_PROXIES 为 nginx/ALB 的 IP
    """
    direct_ip = get_remote_address(request)
    trusted_proxies = _get_trusted_proxy_set()

    # 仅当直接连接来自受信代理时，才信任 X-Forwarded-For 头
    if trusted_proxies and direct_ip in trusted_proxies:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            # X-Forwarded-For 格式: "client_ip, proxy1, proxy2" (左侧最原始，右侧最近一跳)
            # H-Core-4 修复：从右向左遍历，跳过所有受信代理 IP，第一个非受信代理 IP 才是真实客户端 IP。
            # 防止攻击者通过受信代理发送 "X-Forwarded-For: fake_ip, real_ip"
            # 使 split(",")[0] 返回 fake_ip 绕过限流。
            ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
            if ips:
                for ip in reversed(ips):
                    if ip not in trusted_proxies:
                        return ip
                # 全部都是受信代理 IP (罕见)，回退到最左侧 IP
                return ips[0]
    # 未配置受信代理或非受信代理请求时，使用直接连接 IP
    return direct_ip


def _build_limiter() -> Limiter:
    app_env = settings.app_env.lower()
    kwargs: dict = {}

    if app_env == "production":
        redis_url = settings.redis_url
        if redis_url and redis_url.startswith("redis"):
            kwargs["storage_uri"] = redis_url
            logger.info("Rate limiter using Redis backend: %s", redis_url)
        else:
            logger.warning(
                "PRODUCTION environment but REDIS_URL not properly configured. "
                "Rate limiter will use in-memory storage (state lost on restart)."
            )

    # v1.27 安全加固: 开发/测试环境也启用限流（更宽松），以便发现集成问题
    # 生产环境: 60/minute
    # 开发/测试环境: 600/minute（仅用于本地开发，不影响生产行为）
    if app_env == "production":
        default_limits = ["60/minute"]
    else:
        default_limits = ["600/minute"]
        if app_env in ("development", "test"):
            logger.info(
                "Rate limiter enabled in %s mode with relaxed limits (600/min). "
                "Production uses 60/min.",
                app_env,
            )

    # M5 修复：使用 get_real_client_ip 替代 get_remote_address，
    # 在反向代理后正确识别真实客户端 IP
    limiter = Limiter(
        key_func=get_real_client_ip, default_limits=default_limits, **kwargs
    )
    # v1.27: 限流始终启用（不再仅在生产环境），但 dev/test 有更宽松的限制
    limiter.enabled = True
    return limiter


limiter = _build_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    from fastapi.responses import JSONResponse

    # STAB-P1-001: 统一响应体为 {code, message, data, error} 结构
    return JSONResponse(
        status_code=429,
        content={
            "code": 429,
            "message": "请求过于频繁，请稍后再试",
            "data": None,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "请求过于频繁，请稍后再试",
            },
        },
    )


def install_rate_limiter(app) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    # M-02 修复：生产环境下显式校验 Redis 连通性，避免 slowapi 静默降级到内存存储
    # 导致多实例部署时限流计数相互独立而失效。
    _verify_redis_backend()


def _verify_redis_backend() -> None:
    """生产环境校验 Redis 限流后端连通性，失败时发出告警。

    slowapi 在 Redis 不可用时会静默降级到进程内内存存储，多实例部署下
    每个实例独立计数，限流将完全失效。此处显式 ping 一次 Redis，
    让运维人员能在日志中看到降级事件。
    """
    if settings.app_env.lower() != "production":
        return
    redis_url = settings.redis_url
    if not redis_url or not redis_url.startswith("redis"):
        logger.warning(
            "Rate limiter has no Redis backend configured in production. "
            "Multi-instance deployments will have per-instance rate limits."
        )
        return
    # L-8 修复：将 client.close() 放入 finally 块，确保 ping() 抛异常时 client 被正确关闭
    import redis

    client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.ping()
        logger.info("Rate limiter Redis backend connectivity verified.")
    except Exception as exc:
        # 不阻止启动（允许降级运行），但发出 critical 告警以便监控告警系统捕获
        logger.critical(
            "Rate limiter Redis backend is UNREACHABLE (%s). "
            "slowapi will silently degrade to in-memory storage, causing rate limits "
            "to be per-instance in multi-instance deployments. "
            "Please verify REDIS_URL=%s and Redis service health.",
            exc,
            redis_url,
        )
    finally:
        client.close()
