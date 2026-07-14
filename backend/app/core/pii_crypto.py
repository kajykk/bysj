"""应用级 PII 字段加密层 (v1.27 安全加固).

SEC-P2-004: 加密算法从 Fernet (AES-128-CBC + HMAC-SHA256) 升级到 AES-256-GCM.
- 新数据使用 `enc:v2:` 前缀 (AES-256-GCM, 12 字节 nonce + 密文 + 16 字节 tag)
- 旧数据 `enc:v1:` 前缀仍可解密 (向后兼容 Fernet, 便于平滑迁移)
- encrypt_field 默认输出 v2 密文; decrypt_field 双前缀自动识别

密钥管理:
- 生产环境必须显式设置 PII_ENCRYPTION_KEY (44 字节 base64 Fernet 密钥 或 >= 32 字节任意字符串)
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
import hmac
import logging
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

logger = logging.getLogger(__name__)

# 密文前缀 (用于检测/迁移)
# SEC-P2-004: v1 = Fernet (AES-128-CBC), v2 = AES-256-GCM
ENCRYPTED_PREFIX = "enc:v1:"
ENCRYPTED_PREFIX_V2 = "enc:v2:"
# 支持的前缀集合 (用于 _is_encrypted 判断)
_ENCRYPTED_PREFIXES = (ENCRYPTED_PREFIX, ENCRYPTED_PREFIX_V2)

# AES-GCM 参数
_AESGCM_NONCE_BYTES = 12  # 96-bit nonce (NIST 推荐)
_AESGCM_KEY_BYTES = 32  # 256-bit key (AES-256)

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
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return _derive_fernet_key_with_base(field, base)


def _derive_fernet_key_with_base(field: str, base_key: str) -> bytes:
    """P2-4: 基于指定密钥派生字段级 Fernet 密钥 (用于旧密钥解密回退)."""
    salt = _FIELD_SALTS.get(field, b"bysj-pii-default-v1")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"bysj-pii-fernet-key",
    )
    derived = hkdf.derive(base_key.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def _get_fernet(field: str) -> Fernet:
    return Fernet(_derive_fernet_key(field))


def _get_previous_fernets(field: str) -> list[Fernet]:
    """P2-4: 获取旧密钥的 Fernet 实例列表 (用于解密回退).

    从 settings.pii_previous_keys (逗号分隔) 加载旧密钥,
    为每个旧密钥派生字段级 Fernet 实例.
    """
    previous_keys_str = settings.pii_previous_keys
    if not previous_keys_str:
        return []
    fernets: list[Fernet] = []
    seen_keys: set[str] = set()
    for key in previous_keys_str.split(","):
        key = key.strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        try:
            derived = _derive_fernet_key_with_base(field, key)
            fernets.append(Fernet(derived))
        except Exception as exc:
            logger.warning(
                "Failed to derive previous Fernet key for field=%s: %s", field, exc
            )
    return fernets


def _is_encrypted(value: str | None) -> bool:
    """SEC-P2-004: 检测 v1 (Fernet) 或 v2 (AES-256-GCM) 密文前缀."""
    return bool(value) and value.startswith(_ENCRYPTED_PREFIXES)


def _derive_aes_key_with_base(field: str, base_key: str) -> bytes:
    """SEC-P2-004: 基于指定主密钥派生字段级 AES-256 密钥 (32 字节).

    使用与 Fernet 不同的 HKDF info 字符串, 确保两套密钥相互独立,
    即使主密钥相同, 也不会派生出相同的字段密钥.
    """
    salt = _FIELD_SALTS.get(field, b"bysj-pii-default-v1")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_AESGCM_KEY_BYTES,
        salt=salt,
        info=b"bysj-pii-aes-gcm-key-v2",
    )
    return hkdf.derive(base_key.encode("utf-8"))


def _derive_aes_key(field: str) -> bytes:
    """SEC-P2-004: 基于当前主密钥派生字段级 AES-256 密钥."""
    base = settings.pii_encryption_key
    if not base:
        raise RuntimeError(
            "PII_ENCRYPTION_KEY 未配置。请在 .env 设置: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return _derive_aes_key_with_base(field, base)


def _get_aes_gcm(field: str) -> AESGCM:
    """SEC-P2-004: 获取当前主密钥派生的 AES-256-GCM 实例."""
    return AESGCM(_derive_aes_key(field))


def _get_previous_aes_gcms(field: str) -> list[AESGCM]:
    """SEC-P2-004: 获取旧主密钥派生的 AES-GCM 实例列表 (密钥轮换回退)."""
    previous_keys_str = settings.pii_previous_keys
    if not previous_keys_str:
        return []
    instances: list[AESGCM] = []
    seen_keys: set[str] = set()
    for key in previous_keys_str.split(","):
        key = key.strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        try:
            instances.append(AESGCM(_derive_aes_key_with_base(field, key)))
        except Exception as exc:
            logger.warning(
                "Failed to derive previous AES-GCM key for field=%s: %s", field, exc
            )
    return instances


def _encrypt_aes_gcm(plaintext: str, field: str) -> str:
    """SEC-P2-004: AES-256-GCM 加密, 输出 `enc:v2:` + base64(nonce || ciphertext_and_tag).

    - nonce: 12 字节随机数 (每次加密使用新随机 nonce, NIST SP 800-38D 推荐 96-bit)
    - AESGCM.encrypt 返回 ciphertext || tag (tag 为最后 16 字节)
    - 完整密文 = base64(nonce + ciphertext_and_tag)
    """
    aesgcm = _get_aes_gcm(field)
    nonce = os.urandom(_AESGCM_NONCE_BYTES)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    blob = nonce + ciphertext_and_tag
    return ENCRYPTED_PREFIX_V2 + base64.urlsafe_b64encode(blob).decode("ascii")


def _decrypt_aes_gcm_with_key(token_str: str, aesgcm: AESGCM) -> str:
    """SEC-P2-004: 使用指定 AESGCM 实例解密 v2 密文, 失败抛 InvalidTag."""
    raw = base64.urlsafe_b64decode(token_str.encode("ascii"))
    if len(raw) < _AESGCM_NONCE_BYTES + 16:  # nonce + 至少 16 字节 tag
        raise InvalidTag("AES-GCM ciphertext too short")
    nonce = raw[:_AESGCM_NONCE_BYTES]
    ciphertext_and_tag = raw[_AESGCM_NONCE_BYTES:]
    plain = aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=None)
    return plain.decode("utf-8")


def _decrypt_aes_gcm(token_str: str, field: str) -> str:
    """SEC-P2-004: AES-256-GCM 解密, 支持当前密钥 + 旧密钥回退."""
    # 1. 当前密钥优先
    try:
        return _decrypt_aes_gcm_with_key(token_str, _get_aes_gcm(field))
    except InvalidTag:
        pass
    # 2. 旧密钥回退
    previous_aesgcms = _get_previous_aes_gcms(field)
    for idx, old_aesgcm in enumerate(previous_aesgcms):
        try:
            plain = _decrypt_aes_gcm_with_key(token_str, old_aesgcm)
            logger.info(
                "PII v2 decryption succeeded via previous key fallback: field=%s, key_index=%d/%d",
                field,
                idx + 1,
                len(previous_aesgcms),
            )
            return plain
        except InvalidTag:
            continue
    raise InvalidTag("AES-GCM decryption exhausted current + previous keys")


def is_encrypted_with_current_key(ciphertext: str | None, field: str) -> bool:
    """P2-4: 检查密文是否用当前 PII_ENCRYPTION_KEY 加密.

    用于密钥轮换脚本判断是否需要重新加密某行数据.
    Fernet/AES-GCM 每次加密使用随机 IV/nonce, 密文不可直接比较, 必须通过尝试解密判断.

    SEC-P2-004: 同时支持 v1 (Fernet) 和 v2 (AES-256-GCM) 前缀.

    Returns:
        True: 密文能用当前密钥解密 (无需轮换), 或为 NULL/空/明文 (无需处理)
        False: 密文当前密钥解不开, 可能需要用旧密钥回退 + 重新加密
    """
    if ciphertext is None or ciphertext == "":
        return True  # NULL/空不需要轮换
    if not _is_encrypted(ciphertext):
        return True  # 未加密明文不需要轮换 (避免误加密非 PII 数据)
    # SEC-P2-004: 根据前缀选择解密算法
    if ciphertext.startswith(ENCRYPTED_PREFIX_V2):
        token_str = ciphertext[len(ENCRYPTED_PREFIX_V2) :]
        try:
            _decrypt_aes_gcm_with_key(token_str, _get_aes_gcm(field))
            return True
        except InvalidTag:
            return False
    # v1 Fernet 路径
    token_str = ciphertext[len(ENCRYPTED_PREFIX) :]
    try:
        _get_fernet(field).decrypt(token_str.encode("ascii"))
        return True
    except InvalidToken:
        return False


def encrypt_field(plaintext: str | None, field: str) -> str | None:
    """加密 PII 字段值.

    SEC-P2-004: 默认使用 AES-256-GCM (enc:v2:) 加密新数据.
    旧密文 (enc:v1: Fernet) 仍可由 decrypt_field 解密, 平滑迁移.

    Args:
        plaintext: 明文（None 返回 None）
        field: 字段名（用于密钥派生）

    Returns:
        密文字符串（带 enc:v2: 前缀），失败时抛 RuntimeError
    """
    if plaintext is None or plaintext == "":
        return plaintext
    if _is_encrypted(plaintext):
        return plaintext  # 已是密文，避免重复加密
    try:
        return _encrypt_aes_gcm(plaintext, field)
    except Exception as exc:
        logger.error("PII encryption failed for field=%s: %s", field, exc)
        raise RuntimeError("PII 加密失败") from exc


def decrypt_field(ciphertext: str | None, field: str) -> str | None:
    """解密 PII 字段值.

    SEC-P2-004: 双前缀自动识别解密.
    - `enc:v2:` → AES-256-GCM 解密 (当前密钥优先, 旧密钥回退)
    - `enc:v1:` → Fernet 解密 (当前密钥优先, 旧密钥回退)

    Args:
        ciphertext: 密文（带前缀）或明文
        field: 字段名

    Returns:
        明文（None 返回 None）

    P2-4: 支持密钥轮换 - 当前密钥优先解密, 失败时按顺序尝试旧密钥回退.
    成功回退时记录 info 日志 (运维侧可通过日志发现未迁移的旧密文).
    """
    if ciphertext is None or ciphertext == "":
        return ciphertext
    if not _is_encrypted(ciphertext):
        return ciphertext  # 兼容未加密的旧数据
    # SEC-P2-004: 根据前缀分发到对应算法
    if ciphertext.startswith(ENCRYPTED_PREFIX_V2):
        token_str = ciphertext[len(ENCRYPTED_PREFIX_V2) :]
        try:
            return _decrypt_aes_gcm(token_str, field)
        except InvalidTag:
            logger.error(
                "PII v2 decryption failed (exhausted current + previous keys): field=%s, len=%d",
                field,
                len(ciphertext),
            )
            raise ValueError("PII 解密失败（密钥错误或数据损坏）") from None
    # v1 Fernet 路径 (保留向后兼容)
    token_str = ciphertext[len(ENCRYPTED_PREFIX) :]
    token_bytes = token_str.encode("ascii")
    # 1. 优先使用当前密钥解密
    try:
        plain = _get_fernet(field).decrypt(token_bytes)
        return plain.decode("utf-8")
    except InvalidToken:
        pass  # 落入下方旧密钥回退
    # 2. P2-4: 旧密钥回退解密 (密钥轮换场景)
    previous_fernets = _get_previous_fernets(field)
    for idx, old_fernet in enumerate(previous_fernets):
        try:
            plain = old_fernet.decrypt(token_bytes)
            logger.info(
                "PII v1 decryption succeeded via previous key fallback: field=%s, key_index=%d/%d",
                field,
                idx + 1,
                len(previous_fernets),
            )
            return plain.decode("utf-8")
        except InvalidToken:
            continue
    # 3. 全部密钥都失败
    logger.error(
        "PII v1 decryption failed (exhausted current + %d previous keys): field=%s, len=%d",
        len(previous_fernets),
        field,
        len(ciphertext),
    )
    raise ValueError("PII 解密失败（密钥错误或数据损坏）")


# ── SQLAlchemy TypeDecorator (供 ORM 直接使用加密列) ──────────────────

from sqlalchemy.types import String, TypeDecorator  # noqa: E402


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
        # 密文比明文长（base64 扩展 + 前缀），先计算实际所需列长度
        self.field = field
        self.impl_length = length * 2 + len(ENCRYPTED_PREFIX) + 50
        super().__init__(length=self.impl_length, **kwargs)

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
        except ValueError as exc:
            # M-Core-3 修复：解密失败时记录错误日志，便于发现密钥轮换导致的数据丢失
            logger.error(
                "PII decryption failed for field: %s", self.field, exc_info=exc
            )
            return "[DECRYPTION_FAILED]"


def mask_pii(value: str | None, *, keep_last: int = 0, keep_first: int = 0) -> str:
    """对 PII 脱敏（用于日志/审计）.

    注意: Python 中 -0 == 0, 所以 value[-0:] == value, 因此 keep_last=0 必须特判.

    Args:
        value: 待脱敏的原始值。
        keep_last: 保留末尾 N 个字符，其余用 * 替换。
        keep_first: 保留开头 N 个字符，其余用 * 替换。keep_first 与 keep_last 不可同时大于 0。
    """
    if not value:
        return ""
    if keep_first > 0 and keep_last > 0:
        # 优先使用 keep_first，避免歧义
        keep_last = 0
    if keep_first > 0:
        if len(value) <= keep_first:
            return "*" * len(value)
        return value[:keep_first] + ("*" * (len(value) - keep_first))
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
        # C-Core-1 修复：移除硬编码 fallback 密钥 "dev-only-fallback-key"。
        # 原实现使开发环境所有盲索引（email_hash、phone_hash）基于公开密钥，
        # 攻击者可对已知明文批量计算反查 PII。
        # config.py 的 Settings.model_validator 已保证非生产环境自动生成随机密钥，
        # 到达此处说明 Settings 初始化异常，应直接失败而非降级到已知弱密钥。
        raise RuntimeError(
            "PII_ENCRYPTION_KEY 未配置。Settings.model_validator 应在非生产环境自动生成随机密钥；"
            "生产环境请设置 PII_ENCRYPTION_KEY 环境变量。"
        )
    salt = _FIELD_SALTS.get(field, b"bysj-pii-default-v1")
    # 使用真正的 HMAC-SHA256（非拼接式 SHA256），防止长度扩展攻击
    return hmac.new(
        base.encode("utf-8"), salt + plaintext.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def ensure_pii_key() -> None:
    """启动时检查 PII 密钥。生产环境缺失则启动失败。

    C-02 修复：开发环境的密钥自动生成已迁移到 Settings.model_validator (config.py)，
    在 Settings 初始化时完成，避免运行时通过 object.__setattr__ 突变（线程不安全）。
    此处仅保留生产环境的安全网检查。

    P0-1.2: 增加密钥强度校验 (>= 32 bytes) 和已知弱密钥检测.
    """
    if not settings.pii_encryption_key:
        if settings.app_env.lower() == "production":
            raise RuntimeError(
                "PII_ENCRYPTION_KEY must be set in production. "
                'Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        # 开发环境下密钥应由 Settings.model_validator 已生成；若此处仍为空，
        # 说明 Settings 初始化异常，显式生成作为最后兜底（不再使用 object.__setattr__）。
        logger.warning(
            "⚠️ PII_ENCRYPTION_KEY 在 ensure_pii_key 时仍为空, 已生成临时密钥. "
            "重启后失效, 仅用于本地开发. 生产环境必须显式配置."
        )
        settings.pii_encryption_key = Fernet.generate_key().decode()
        return

    # P0-1.2: 密钥强度校验 (生产环境强制, 开发环境警告)
    _validate_pii_key_strength(settings.pii_encryption_key)


# P0-1.2: 已知弱密钥集合 (禁止在生产环境使用)
_INSECURE_PII_KEYS = {
    "",
    "test",
    "dev",
    "changeme",
    "secret",
    "password",
    "pii-encryption-key",
    "change-this-to-a-random-key",
}


def _validate_pii_key_strength(key: str) -> None:
    """校验 PII 密钥强度 (P0-1.2).

    - 生产环境: 密钥长度 < 32 字节或匹配已知弱密钥时, 启动失败
    - 开发环境: 仅记录警告, 不阻断启动
    """
    is_production = settings.app_env.lower() == "production"
    key_bytes = key.encode("utf-8")

    # 已知弱密钥检测
    if key in _INSECURE_PII_KEYS:
        msg = f"PII_ENCRYPTION_KEY is a known weak value (len={len(key)}). Use a strong random key."
        if is_production:
            raise RuntimeError(msg)
        logger.warning("⚠️ %s", msg)
        return

    # 密钥长度校验 (Fernet 密钥 = 44 bytes base64 = 32 bytes entropy;
    # 自定义密钥应 >= 32 bytes 原始长度以提供足够熵)
    min_bytes = 32
    if len(key_bytes) < min_bytes:
        msg = (
            f"PII_ENCRYPTION_KEY too short (got {len(key_bytes)} bytes, minimum {min_bytes} bytes). "
            'Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
        if is_production:
            raise RuntimeError(msg)
        logger.warning("⚠️ %s", msg)
