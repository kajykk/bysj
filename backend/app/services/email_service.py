import asyncio
import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import settings

logger = logging.getLogger(__name__)


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
        reset_link = f"{settings.password_reset_base_url}?token={quote(token)}&email={quote(email)}"

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
            # M11 修复：用 asyncio.to_thread 包装同步 SMTP 调用，避免阻塞事件循环
            await asyncio.to_thread(self._send_smtp, message)
        except Exception:
            logger.exception("email.send_password_reset_failed user=%s", _mask_email(email))
            raise ValueError("重置邮件发送失败，请稍后重试")

    def _send_smtp(self, message: EmailMessage) -> None:
        """同步 SMTP 发送逻辑，供 asyncio.to_thread 调用。"""
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
