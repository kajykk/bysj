from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from jwt import PyJWTError

from app.core.config import settings

MAX_PASSWORD_BYTES = 72


@lru_cache(maxsize=1)
def _load_private_key() -> str:
    """SEC-P2-001: 加载 JWT 签名私钥 (RS256 模式).

    优先使用 jwt_private_key_pem (直接 PEM 内容),
    其次从 jwt_private_key_path 文件加载.

    Returns:
        PEM 格式私钥字符串.

    Raises:
        ValueError: RS256 模式但未配置私钥.
    """
    if settings.jwt_private_key_pem:
        return settings.jwt_private_key_pem
    if settings.jwt_private_key_path:
        with open(settings.jwt_private_key_path, "r", encoding="utf-8") as f:
            return f.read()
    raise ValueError(
        "RS256 mode requires JWT_PRIVATE_KEY_PEM or JWT_PRIVATE_KEY_PATH. "
        "Generate with: openssl genrsa -out private.pem 2048"
    )


@lru_cache(maxsize=1)
def _load_public_key() -> str:
    """SEC-P2-001: 加载 JWT 验证公钥 (RS256 模式).

    优先使用 jwt_public_key_pem (直接 PEM 内容),
    其次从 jwt_public_key_path 文件加载.

    Returns:
        PEM 格式公钥字符串.

    Raises:
        ValueError: RS256 模式但未配置公钥.
    """
    if settings.jwt_public_key_pem:
        return settings.jwt_public_key_pem
    if settings.jwt_public_key_path:
        with open(settings.jwt_public_key_path, "r", encoding="utf-8") as f:
            return f.read()
    raise ValueError(
        "RS256 mode requires JWT_PUBLIC_KEY_PEM or JWT_PUBLIC_KEY_PATH. "
        "Generate with: openssl rsa -in private.pem -pubout -out public.pem"
    )


def _get_signing_key() -> str:
    """SEC-P2-001: 获取 JWT 签名 key.

    HS256: 返回 jwt_secret_key (对称密钥).
    RS256: 返回 PEM 格式私钥 (非对称签名).

    Returns:
        签名 key (HS256: 对称密钥, RS256: PEM 私钥).
    """
    if settings.jwt_algorithm.upper() == "RS256":
        return _load_private_key()
    return settings.jwt_secret_key


def _get_verifying_key() -> str:
    """SEC-P2-001: 获取 JWT 验证 key.

    HS256: 返回 jwt_secret_key (对称密钥, 签名和验证用同一个 key).
    RS256: 返回 PEM 格式公钥 (非对称验证).

    Returns:
        验证 key (HS256: 对称密钥, RS256: PEM 公钥).
    """
    if settings.jwt_algorithm.upper() == "RS256":
        return _load_public_key()
    return settings.jwt_secret_key


def validate_password_bytes(password: str) -> None:
    byte_len = len(password.encode("utf-8"))
    if byte_len > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"密码不能超过{MAX_PASSWORD_BYTES}字节（当前{byte_len}字节）。"
            f"中文字符按UTF-8编码可能占用3字节，请使用较短密码。"
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # M-05 修复：与 get_password_hash 保持长度一致性。
    # get_password_hash 会拒绝超过 72 字节的密码（validate_password_bytes 抛异常），
    # 因此超长密码不可能被注册成功，验证时也应直接返回 False 而非静默截断。
    # 避免两个共享前 72 字节的超长密码被视为相同的安全风险。
    if len(plain_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return False
    truncated = plain_password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    # 拒绝超长密码而非静默截断，防止两个共享前 72 字节的密码被视为相同
    validate_password_bytes(password)
    truncated = password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    if "type" not in payload:
        payload["type"] = "access"
    payload["jti"] = uuid4().hex
    # SEC-P3-001: 添加 iss/aud 声明 (如已配置)
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    # SEC-P2-001: 根据 jwt_algorithm 选择签名 key (HS256 对称 / RS256 非对称)
    return jwt.encode(
        payload, _get_signing_key(), algorithm=settings.jwt_algorithm
    )


def create_refresh_token(data: dict[str, Any], jti: str | None = None) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    if "type" not in payload:
        payload["type"] = "refresh"
    payload["jti"] = jti or uuid4().hex
    # SEC-P3-001: 添加 iss/aud 声明 (如已配置)
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    return jwt.encode(
        payload, _get_signing_key(), algorithm=settings.jwt_algorithm
    )


def create_password_reset_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=settings.password_reset_token_expire_minutes
    )
    payload["type"] = "password_reset"
    # L-Core-1 修复：添加 jti（唯一 ID），支持后续基于 jti 单独吊销密码重置 token
    payload["jti"] = uuid4().hex
    # SEC-P3-001: 添加 iss/aud 声明 (如已配置)
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    return jwt.encode(
        payload, _get_signing_key(), algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        # SEC-P2-001: 根据 jwt_algorithm 选择验证 key (HS256 对称 / RS256 非对称)
        # SEC-P3-001: 如已配置 iss/aud 则验证 (向后兼容: 留空则不验证)
        decode_kwargs: dict[str, Any] = {
            "algorithms": [settings.jwt_algorithm],
        }
        if settings.jwt_issuer:
            decode_kwargs["issuer"] = settings.jwt_issuer
        if settings.jwt_audience:
            decode_kwargs["audience"] = settings.jwt_audience
        return jwt.decode(token, _get_verifying_key(), **decode_kwargs)
    except PyJWTError as exc:
        raise ValueError("Invalid token") from exc
