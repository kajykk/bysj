from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from jwt import PyJWTError

from app.core.config import settings

MAX_PASSWORD_BYTES = 72


def validate_password_bytes(password: str) -> None:
    byte_len = len(password.encode("utf-8"))
    if byte_len > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"密码不能超过{MAX_PASSWORD_BYTES}字节（当前{byte_len}字节）。"
            f"中文字符按UTF-8编码可能占用3字节，请使用较短密码。"
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt 限制 72 字节，截断后编码为 bytes
    truncated = plain_password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    # bcrypt 限制 72 字节，截断后编码为 bytes
    truncated = password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    if "type" not in payload:
        payload["type"] = "access"
    payload["jti"] = uuid4().hex
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any], jti: str | None = None) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    if "type" not in payload:
        payload["type"] = "refresh"
    payload["jti"] = jti or uuid4().hex
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_password_reset_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)
    payload["type"] = "password_reset"
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except PyJWTError as exc:
        raise ValueError("Invalid token") from exc
