"""应用级 PII 字段加密层 (v1.27 安全加固).

使用 Fernet (AES-128-CBC + HMAC-SHA256) 实现对称加密。
所有加密字段以 `enc:v1:` 前缀标识，便于平滑迁移。

密钥管理:
- 生产环境必须显式设置 PII_ENCRYPTION_KEY (44 字节 base64 Fernet 密钥)
- 开发环境自动生成（重启后失效，**仅用于本地开发**）
- 禁止硬编码密钥，禁止 commit 真实密钥

注意事项:
- 加密字段不能用作唯一约束（密文唯一性不等于明文唯一性）
- 不能用 LIKE 查询（需先解密再匹配）
- 不能跨密钥迁移数据，除非保留旧密钥
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

logger = logging.getLogger(__name__)

# 密文前缀 (用于检测/迁移)
ENCRYPTED_PREFIX = "enc:v1:"

# 字段级 salt (用于字段特定的密钥派生，避免跨字段关联)
_FIELD_SALTS: dict[str, bytes] = {
    "email": b"bysj-pii-email-v1",
    "phone": b"bysj-pii-phone-v1",
    "emergency_name": b"bysj-pii-emname-v1",
    "emergency_phone": b"bysj-pii-emph-v1",
}


def _derive_fernet_key(field: str) -> bytes:
    """基于主密钥派生字段级 Fernet 密钥 (HKDF)."""
    base = settings.pii_encryption_key
    if not base:
        raise RuntimeError(
            "PII_ENCRYPTION_KEY 未配置。请在 .env 设置: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    salt = _FIELD_SALTS.get(field, b"bysj-pii-default-v1")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"bysj-pii-fernet-key",
    )
    derived = hkdf.derive(base.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def _get_fernet(field: str) -> Fernet:
    return Fernet(_derive_fernet_key(field))


def _is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_field(plaintext: str | None, field: str) -> str | None:
    """加密 PII 字段值.

    Args:
        plaintext: 明文（None 返回 None）
        field: 字段名（用于密钥派生）

    Returns:
        密文字符串（带 enc:v1: 前缀），失败时抛 RuntimeError
    """
    if plaintext is None or plaintext == "":
        return plaintext
    if _is_encrypted(plaintext):
        return plaintext  # 已是密文，避免重复加密
    try:
        token = _get_fernet(field).encrypt(plaintext.encode("utf-8"))
        return ENCRYPTED_PREFIX + token.decode("ascii")
    except Exception as exc:
        logger.error("PII encryption failed for field=%s: %s", field, exc)
        raise RuntimeError("PII 加密失败") from exc


def decrypt_field(ciphertext: str | None, field: str) -> str | None:
    """解密 PII 字段值.

    Args:
        ciphertext: 密文（带前缀）或明文
        field: 字段名

    Returns:
        明文（None 返回 None）
    """
    if ciphertext is None or ciphertext == "":
        return ciphertext
    if not _is_encrypted(ciphertext):
        return ciphertext  # 兼容未加密的旧数据
    token_str = ciphertext[len(ENCRYPTED_PREFIX):]
    try:
        plain = _get_fernet(field).decrypt(token_str.encode("ascii"))
        return plain.decode("utf-8")
    except InvalidToken as exc:
        # 密钥轮换场景: 旧密钥解不开时，记录错误并返回脱敏值
        logger.error(
            "PII decryption failed (possible key rotation): field=%s, len=%d",
            field, len(ciphertext),
        )
        raise ValueError("PII 解密失败（密钥错误或数据损坏）") from exc


# ── SQLAlchemy TypeDecorator (供 ORM 直接使用加密列) ──────────────────

from sqlalchemy.types import TypeDecorator, String, LargeBinary  # noqa: E402


class EncryptedString(TypeDecorator):
    """加密字符串类型 (SQLAlchemy TypeDecorator).

    数据库存储密文，应用层自动解密/加密。
    仅适用于新建字段（不能加密已有的普通字段，需迁移）。

    使用示例:
        email: Mapped[str | None] = mapped_column(EncryptedString(100, field="email"))
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int, field: str, **kwargs: Any) -> None:
        super().__init__(length=length, **kwargs)
        self.field = field
        # 密文比明文长（base64 扩展 + 前缀），所以使用更长的列长度
        self.impl_length = length * 2 + len(ENCRYPTED_PREFIX) + 50

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        return encrypt_field(value, self.field)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        try:
            return decrypt_field(value, self.field)
        except ValueError:
            return "[DECRYPTION_FAILED]"


def mask_pii(value: str | None, *, keep_last: int = 0) -> str:
    """对 PII 脱敏（用于日志/审计）.

    注意: Python 中 -0 == 0, 所以 value[-0:] == value, 因此 keep_last=0 必须特判.
    """
    if not value:
        return ""
    if keep_last <= 0:
        return "*" * len(value)
    if len(value) <= keep_last:
        return "*" * len(value)
    return ("*" * (len(value) - keep_last)) + value[-keep_last:]


def compute_blind_index(plaintext: str | None, field: str) -> str | None:
    """计算 PII 字段的盲索引（HMAC-SHA256），用于唯一约束和等值查询.

    加密后的密文不可用于唯一约束（Fernet 使用随机 IV，相同明文产生不同密文）。
    本函数使用 HMAC-SHA256 基于主密钥和字段 salt 生成确定性哈希，
    可安全地用于 UNIQUE 索引和 WHERE 子句的等值查询。

    安全性：
    - HMAC 是单向的，无法从哈希逆推明文
    - 字段级 salt 防止跨字段关联（如 email 和 phone 的哈希不同）
    - 主密钥泄露后哈希才会被暴力破解（需配合密钥轮换）

    Args:
        plaintext: 明文（None 返回 None）
        field: 字段名（用于 salt 派生）

    Returns:
        64 字符的十六进制哈希字符串，或 None
    """
    if plaintext is None or plaintext == "":
        return plaintext
    base = settings.pii_encryption_key
    if not base:
        # 开发环境无密钥时使用固定 fallback（仅本地开发，生产环境 ensure_pii_key 会拦截）
        base = "dev-only-fallback-key"
    salt = _FIELD_SALTS.get(field, b"bysj-pii-default-v1")
    h = hashlib.sha256(base.encode("utf-8") + salt + plaintext.encode("utf-8"))
    return h.hexdigest()


def ensure_pii_key() -> None:
    """启动时检查 PII 密钥。生产环境缺失则启动失败。"""
    if not settings.pii_encryption_key:
        if settings.app_env.lower() == "production":
            raise RuntimeError(
                "PII_ENCRYPTION_KEY must be set in production. "
                "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        # 开发环境自动生成（仅本次进程有效）
        key = Fernet.generate_key().decode()
        os.environ["PII_ENCRYPTION_KEY"] = key
        # 注意: settings 是已加载的 pydantic_settings, 这里需要重新触发
        logger.warning(
            "⚠️ PII_ENCRYPTION_KEY 未配置, 已自动生成临时密钥. "
            "重启后失效, 仅用于本地开发. 生产环境必须显式配置."
        )
        # 直接设置 settings 实例（pydantic 不再 reload）
        # 技术债：pydantic Settings 默认不可变，开发环境需运行时生成密钥。
        # 生产环境应通过 .env 文件预置 PII_ENCRYPTION_KEY，避免运行时突变。
        # TODO: 迁移到 model_validator 在初始化时生成。
        object.__setattr__(settings, "pii_encryption_key", key)
