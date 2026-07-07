import asyncio
import logging
import smtplib
import threading
import time
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import settings
from app.core.db_breaker import CircuitBreakerOpenError
from app.core.smtp_breaker import call_with_smtp_breaker

logger = logging.getLogger(__name__)

# L-12 修复：SMTP 重试配置
# H-Svc-11 修复：_send_smtp 在 asyncio.to_thread 中执行，time.sleep 会阻塞线程池中的工作线程。
# 高并发密码重置下，过多重试 + 长 sleep 会耗尽线程池。将重试次数从 3 降为 2，最大阻塞 1s。
# 完全重构为 async 需要改动调用方，不在本次范围。
_SMTP_MAX_RETRIES = 2
_SMTP_RETRY_BASE_DELAY = 1.0  # 基础重试延迟（秒）

# RES-P1-009 修复: 线程本地 SMTP 连接复用, 避免每次发送邮件都新建连接 (1-3s 开销).
# _send_smtp 通过 asyncio.to_thread 在线程池中执行, 每个线程维护自己的 SMTP 连接.
# 发送前用 NOOP 检查连接活性, 失败则重建连接并重试.
_SMTP_TLS = threading.local()


def _get_thread_smtp() -> smtplib.SMTP | None:
    """获取当前线程的缓存 SMTP 连接, 无则返回 None."""
    return getattr(_SMTP_TLS, "conn", None)


def _close_thread_smtp() -> None:
    """关闭并清理当前线程的 SMTP 连接."""
    conn = getattr(_SMTP_TLS, "conn", None)
    if conn is not None:
        try:
            conn.quit()
        except Exception:
            pass
        _SMTP_TLS.conn = None


def _create_thread_smtp() -> smtplib.SMTP:
    """为当前线程创建新的 SMTP 连接并完成登录, 存入 thread-local 后返回."""
    conn = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    if settings.smtp_use_tls:
        conn.starttls()
    if settings.smtp_user and settings.smtp_password:
        conn.login(settings.smtp_user, settings.smtp_password)
    _SMTP_TLS.conn = conn
    return conn


def _mask_email(email: str) -> str:
    """将邮箱转换为掩码形式，如 a***@example.com，防止 PII 在日志中泄露。"""
    if not email or "@" not in email:
        return "<invalid>"
    local, domain = email.split("@", 1)
    if not local:
        return "<invalid>"
    return f"{local[0]}***@{domain}"


class EmailService:
    async def send_password_reset_email(self, email: str, token: str) -> None:
        # SEC-P1-002 修复：运行时防御 - 拒绝通过非 HTTPS 链接发送含 token 的重置邮件
        # 生产环境已由 config.py model_validator 启动时拦截, 此处为开发/staging 环境的
        # 额外防御, 防止误将含 token 的 HTTP 链接发送到非 localhost 域名 (中间人攻击风险)
        base_url = settings.password_reset_base_url
        if not base_url.lower().startswith("https://"):
            # 提取 host 部分判断是否为本地地址 (允许开发环境 HTTP 调试)
            from urllib.parse import urlparse

            parsed = urlparse(base_url)
            host = (parsed.hostname or "").lower()
            is_local_host = host in ("localhost", "127.0.0.1", "::1", "")
            if is_local_host:
                # 本地开发环境: 仅记录 warning, 不阻断邮件发送 (便于调试)
                logger.warning(
                    "email.reset_link_insecure_http user=%s host=%s "
                    "(HTTP reset link allowed only for local development)",
                    _mask_email(email),
                    host or "<unknown>",
                )
            else:
                # 非 localhost 的 HTTP 链接: 拒绝发送, 防止 token 泄露
                logger.error(
                    "email.reset_link_blocked user=%s host=%s "
                    "(refused to send password reset token over HTTP to non-localhost host)",
                    _mask_email(email),
                    host or "<unknown>",
                )
                raise ValueError(
                    "密码重置链接必须使用 HTTPS, 拒绝通过 HTTP 向非本地主机发送含 token 的重置邮件"
                )

        reset_link = f"{base_url}?token={quote(token)}&email={quote(email)}"

        if not settings.smtp_host or not settings.smtp_from_email:
            # P1-E 修复：日志中不记录完整 reset_link（含 token），防止敏感信息泄露
            logger.warning(
                "email.smtp_not_configured user=%s (token generated but not delivered)",
                _mask_email(email),
            )
            return

        message = EmailMessage()
        message["Subject"] = "密码重置通知"
        message["From"] = settings.smtp_from_email
        message["To"] = email
        message.set_content(
            "我们收到了一次密码重置请求。\n"
            f"请在 {settings.password_reset_token_expire_minutes} 分钟内打开以下链接完成重置：\n"
            f"{reset_link}\n\n"
            "如果这不是你的操作，请忽略本邮件。"
        )

        try:
            # STAB-P1-004 修复：用 SMTP 熔断器包装 to_thread 调用
            # - 熔断器 OPEN 时直接抛 CircuitBreakerOpenError (503 快速失败)
            # - 失败时由 _is_smtp_failure 分类器判定是否计数 (业务异常不计数)
            # - 熔断器包在 to_thread 外层, 使原始 SMTP 异常被分类器看到
            await call_with_smtp_breaker(asyncio.to_thread(self._send_smtp, message))
        except CircuitBreakerOpenError:
            # 熔断器打开: SMTP 服务持续不可用, 快速失败避免级联阻塞
            logger.warning("email.smtp_circuit_open user=%s", _mask_email(email))
            raise ValueError("邮件服务暂时不可用，请稍后重试") from None
        except Exception as exc:
            logger.exception(
                "email.send_password_reset_failed user=%s", _mask_email(email)
            )
            # L-9 修复：添加 from exc 保留原始异常链，便于排查根因
            raise ValueError("重置邮件发送失败，请稍后重试") from exc

    def _send_smtp(self, message: EmailMessage) -> None:
        """同步 SMTP 发送逻辑，供 asyncio.to_thread 调用。

        L-12 修复：添加重试机制，最多重试 3 次，应对 SMTP 服务器暂时不可用或网络抖动。
        RES-P1-009 修复：使用线程本地 SMTP 连接复用, 避免每次发送都新建连接.
        发送前用 NOOP 检查连接活性, 失败则重建连接并重试.
        """
        last_exc: Exception | None = None
        for attempt in range(1, _SMTP_MAX_RETRIES + 1):
            try:
                conn = _get_thread_smtp()
                if conn is not None:
                    # 复用已有连接: 先 NOOP 检查活性, 避免向已关闭的连接写入
                    try:
                        code, _ = conn.noop()
                        if not (200 <= code < 400):
                            raise OSError("NOOP returned non-success code")
                    except Exception:
                        # 连接已失效, 清理后重建
                        _close_thread_smtp()
                        conn = None
                if conn is None:
                    conn = _create_thread_smtp()
                conn.send_message(message)
                return  # 发送成功，直接返回
            except (smtplib.SMTPException, OSError, ConnectionError) as exc:
                # 连接可能已失效, 清理以便下次重连
                _close_thread_smtp()
                last_exc = exc
                if attempt < _SMTP_MAX_RETRIES:
                    delay = _SMTP_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "SMTP send attempt %d/%d failed: %s, retrying in %.1fs",
                        attempt,
                        _SMTP_MAX_RETRIES,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "SMTP send failed after %d attempts: %s", _SMTP_MAX_RETRIES, exc
                    )
        if last_exc:
            raise last_exc
