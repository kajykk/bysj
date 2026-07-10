"""PII 加密辅助函数单元测试.

覆盖范围:
1. mask_pii - 脱敏函数 (keep_first/keep_last/edge cases)
2. compute_blind_index - HMAC-SHA256 盲索引 (空值/None/字段 salt 区分/确定性)
3. _is_encrypted - 密文前缀检测
4. encrypt_field / decrypt_field 基础往返 (与 test_pii_key_rotation 互补)
5. EncryptedString TypeDecorator - process_bind_param / process_result_value
6. ensure_pii_key / _validate_pii_key_strength 启动检查
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# 在导入被测模块前确保 PII 密钥存在 (与 conftest 一致)
os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "test-pii-key-for-pii-crypto-helpers-tests-1234"
)


# ──────────────────────────────────────────────────────────────────
# 1. mask_pii 脱敏函数
# ──────────────────────────────────────────────────────────────────


class TestMaskPii:
    """PII 脱敏函数测试 (用于日志/审计)."""

    def test_mask_empty_string(self) -> None:
        """空字符串 → 空字符串."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii("") == ""

    def test_mask_none(self) -> None:
        """None → 空字符串 (避免 None 引发 AttributeError)."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii(None) == ""

    def test_mask_full_replace_default(self) -> None:
        """默认参数 (keep_last=0, keep_first=0) → 全部用 * 替换."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii("13800001234") == "***********"
        assert mask_pii("user@example.com") == "*" * 16

    def test_mask_keep_last(self) -> None:
        """keep_last=N → 保留末尾 N 字符, 前面用 * 替换."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii("13800001234", keep_last=4) == "*******1234"
        assert mask_pii("abcdef", keep_last=2) == "****ef"

    def test_mask_keep_first(self) -> None:
        """keep_first=N → 保留开头 N 字符, 后面用 * 替换."""
        from app.core.pii_crypto import mask_pii

        # "user@example.com" 长度 16, keep_first=4 → "user" + "*" * 12
        assert mask_pii("user@example.com", keep_first=4) == "user" + "*" * 12
        # "abcdef" 长度 6, keep_first=2 → "ab" + "*" * 4
        assert mask_pii("abcdef", keep_first=2) == "ab" + "*" * 4

    def test_mask_keep_first_takes_priority(self) -> None:
        """keep_first > 0 时忽略 keep_last (避免歧义)."""
        from app.core.pii_crypto import mask_pii

        result = mask_pii("abcdef", keep_first=2, keep_last=3)
        # keep_first 优先, "abcdef" 长度 6, 保留前 2 字符
        assert result == "ab" + "*" * 4

    def test_mask_value_shorter_than_keep_last(self) -> None:
        """值长度 <= keep_last → 全部替换为 * (避免返回明文)."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii("ab", keep_last=4) == "**"
        assert mask_pii("abc", keep_last=3) == "***"

    def test_mask_value_shorter_than_keep_first(self) -> None:
        """值长度 <= keep_first → 全部替换为 *."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii("ab", keep_first=4) == "**"

    def test_mask_chinese_characters(self) -> None:
        """中文字符串脱敏 (UTF-8 多字节, 但 Python 字符串以 Unicode 字符计)."""
        from app.core.pii_crypto import mask_pii

        # 中文按字符计算长度
        # "张三丰" 长度 3, keep_last=1 → 2 个 * + "丰" = "**丰"
        assert mask_pii("张三丰", keep_last=1) == "**丰"
        # "李四老师" 长度 4, keep_first=1 → "李" + 3 个 * = "李***"
        assert mask_pii("李四老师", keep_first=1) == "李***"


# ──────────────────────────────────────────────────────────────────
# 2. compute_blind_index HMAC-SHA256
# ──────────────────────────────────────────────────────────────────


class TestComputeBlindIndex:
    """compute_blind_index HMAC 盲索引测试."""

    def test_none_returns_none(self) -> None:
        """None → None (避免对空值计算)."""
        from app.core.pii_crypto import compute_blind_index

        assert compute_blind_index(None, "email") is None

    def test_empty_string_returns_empty(self) -> None:
        """空字符串 → 空字符串 (不抛错)."""
        from app.core.pii_crypto import compute_blind_index

        assert compute_blind_index("", "email") == ""

    def test_returns_64_char_hex(self) -> None:
        """返回 64 字符十六进制 (SHA-256 hex)."""
        from app.core.pii_crypto import compute_blind_index

        result = compute_blind_index("user@example.com", "email")
        assert result is not None
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_same_input(self) -> None:
        """相同明文 + 字段 → 相同索引 (用于唯一约束)."""
        from app.core.pii_crypto import compute_blind_index

        h1 = compute_blind_index("user@example.com", "email")
        h2 = compute_blind_index("user@example.com", "email")
        assert h1 == h2

    def test_different_field_different_hash(self) -> None:
        """相同明文 + 不同字段 → 不同索引 (字段 salt 隔离)."""
        from app.core.pii_crypto import compute_blind_index

        h_email = compute_blind_index("13800001234", "email")
        h_phone = compute_blind_index("13800001234", "phone")
        assert h_email != h_phone

    def test_different_value_different_hash(self) -> None:
        """不同明文 → 不同索引."""
        from app.core.pii_crypto import compute_blind_index

        h1 = compute_blind_index("user1@example.com", "email")
        h2 = compute_blind_index("user2@example.com", "email")
        assert h1 != h2

    def test_unknown_field_uses_default_salt(self) -> None:
        """未知字段使用 default salt, 仍能计算索引."""
        from app.core.pii_crypto import compute_blind_index

        h = compute_blind_index("test_value", "unknown_field")
        assert h is not None
        assert len(h) == 64

    def test_unicode_input_supported(self) -> None:
        """Unicode 输入 (中文) 应正确处理."""
        from app.core.pii_crypto import compute_blind_index

        h = compute_blind_index("中文测试", "email")
        assert h is not None
        assert len(h) == 64


# ──────────────────────────────────────────────────────────────────
# 3. _is_encrypted 内部辅助
# ──────────────────────────────────────────────────────────────────


class TestIsEncrypted:
    """_is_encrypted 密文前缀检测."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted(None) is False

    def test_empty_string_returns_false(self) -> None:
        """空字符串 → False."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted("") is False

    def test_plaintext_returns_false(self) -> None:
        """明文 → False."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted("user@example.com") is False

    def test_encrypted_with_prefix_returns_true(self) -> None:
        """带 enc:v1: 前缀 → True."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted("enc:v1:somemaskedtoken") is True

    def test_partial_prefix_returns_false(self) -> None:
        """部分前缀 (enc:) → False (必须完整匹配)."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted("enc:user@example.com") is False


# ──────────────────────────────────────────────────────────────────
# 4. encrypt_field / decrypt_field 基础往返
# ──────────────────────────────────────────────────────────────────


class TestEncryptDecryptRoundtrip:
    """encrypt_field + decrypt_field 基础往返测试."""

    def test_basic_roundtrip(self) -> None:
        """加密后解密应得到原始明文."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        plain = "user@example.com"
        enc = encrypt_field(plain, "email")
        assert enc is not None
        assert enc.startswith("enc:v1:")
        assert decrypt_field(enc, "email") == plain

    def test_encrypt_none_returns_none(self) -> None:
        """加密 None → None."""
        from app.core.pii_crypto import encrypt_field

        assert encrypt_field(None, "email") is None

    def test_encrypt_empty_returns_empty(self) -> None:
        """加密空字符串 → 空字符串."""
        from app.core.pii_crypto import encrypt_field

        assert encrypt_field("", "email") == ""

    def test_encrypt_idempotent(self) -> None:
        """对已加密密文再次 encrypt_field 不重复加密."""
        from app.core.pii_crypto import encrypt_field

        enc1 = encrypt_field("user@example.com", "email")
        enc2 = encrypt_field(enc1, "email")
        # 第二次应直接返回原密文
        assert enc1 == enc2

    def test_decrypt_none_returns_none(self) -> None:
        """解密 None → None."""
        from app.core.pii_crypto import decrypt_field

        assert decrypt_field(None, "email") is None

    def test_decrypt_empty_returns_empty(self) -> None:
        """解密空字符串 → 空字符串."""
        from app.core.pii_crypto import decrypt_field

        assert decrypt_field("", "email") == ""

    def test_decrypt_plaintext_returns_as_is(self) -> None:
        """解密未加密明文 → 原样返回 (向后兼容)."""
        from app.core.pii_crypto import decrypt_field

        plain = "user@example.com"
        assert decrypt_field(plain, "email") == plain

    def test_decrypt_invalid_token_raises(self) -> None:
        """解密错误前缀 + 无效 token → ValueError."""
        from app.core.pii_crypto import decrypt_field

        with pytest.raises(ValueError, match="PII 解密失败"):
            decrypt_field("enc:v1:invalid_base64_token_!@#$%^&*()", "email")

    def test_different_fields_use_different_keys(self) -> None:
        """同一明文在不同字段加密 → 不同密文 (字段 salt 隔离)."""
        from app.core.pii_crypto import encrypt_field

        enc_email = encrypt_field("13800001234", "email")
        enc_phone = encrypt_field("13800001234", "phone")
        assert enc_email != enc_phone

    def test_fernet_random_iv_produces_different_ciphertexts(self) -> None:
        """Fernet 使用随机 IV, 相同明文两次加密密文不同."""
        from app.core.pii_crypto import encrypt_field

        enc1 = encrypt_field("same@text.com", "email")
        enc2 = encrypt_field("same@text.com", "email")
        # Fernet 每次 IV 不同 → 密文不同
        assert enc1 != enc2

    def test_roundtrip_unicode(self) -> None:
        """Unicode 字符串往返."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        plain = "测试用户@例子.公司"
        enc = encrypt_field(plain, "email")
        assert decrypt_field(enc, "email") == plain


# ──────────────────────────────────────────────────────────────────
# 5. _derive_fernet_key_with_base 内部 HKDF
# ──────────────────────────────────────────────────────────────────


class TestDeriveFernetKeyWithBase:
    """HKDF 密钥派生测试."""

    def test_deterministic_output(self) -> None:
        """相同 field + base_key → 相同派生密钥."""
        from app.core.pii_crypto import _derive_fernet_key_with_base

        k1 = _derive_fernet_key_with_base("email", "test-base-key")
        k2 = _derive_fernet_key_with_base("email", "test-base-key")
        assert k1 == k2

    def test_different_field_different_key(self) -> None:
        """不同 field → 不同派生密钥 (因 salt 不同)."""
        from app.core.pii_crypto import _derive_fernet_key_with_base

        k_email = _derive_fernet_key_with_base("email", "test-base-key")
        k_phone = _derive_fernet_key_with_base("phone", "test-base-key")
        assert k_email != k_phone

    def test_different_base_different_key(self) -> None:
        """不同 base_key → 不同派生密钥."""
        from app.core.pii_crypto import _derive_fernet_key_with_base

        k1 = _derive_fernet_key_with_base("email", "base-key-1")
        k2 = _derive_fernet_key_with_base("email", "base-key-2")
        assert k1 != k2

    def test_uses_hkdf_sha256(self) -> None:
        """确认使用 HKDF-SHA256 算法 (与独立 HKDF 计算结果一致)."""
        from app.core import pii_crypto
        from app.core.pii_crypto import _derive_fernet_key_with_base

        base = "test-hkdf-key"
        salt = pii_crypto._FIELD_SALTS["email"]
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"bysj-pii-fernet-key",
        )
        import base64

        expected = base64.urlsafe_b64encode(hkdf.derive(base.encode("utf-8")))
        actual = _derive_fernet_key_with_base("email", base)
        assert actual == expected

    def test_output_is_valid_fernet_key(self) -> None:
        """派生密钥可用作 Fernet 密钥 (44 字节 base64)."""
        from app.core.pii_crypto import _derive_fernet_key_with_base

        key = _derive_fernet_key_with_base("email", "test-key")
        # Fernet 密钥必须是 44 字节 urlsafe base64-encoded 32 字节
        fernet = Fernet(key)
        # 加密/解密 round-trip
        token = fernet.encrypt(b"hello")
        assert fernet.decrypt(token) == b"hello"


# ──────────────────────────────────────────────────────────────────
# 6. _get_previous_fernets 旧密钥回退列表
# ──────────────────────────────────────────────────────────────────


class TestGetPreviousFernets:
    """_get_previous_fernets 旧密钥列表解析测试."""

    def test_empty_config_returns_empty(self) -> None:
        """空配置 → 空列表."""
        from app.core import pii_crypto

        with patch.object(pii_crypto.settings, "pii_previous_keys", ""):
            fernets = pii_crypto._get_previous_fernets("email")
        assert fernets == []

    def test_dedup_duplicate_keys(self) -> None:
        """重复的旧密钥去重."""
        from app.core import pii_crypto

        same_key = "duplicate-key-1234567890123456789012=="
        with patch.object(pii_crypto.settings, "pii_previous_keys", f"{same_key},{same_key}"):
            fernets = pii_crypto._get_previous_fernets("email")
        # 去重后只有 1 个
        assert len(fernets) == 1

    def test_skip_empty_segments(self) -> None:
        """逗号分隔中的空段 (如 ",,key") 跳过."""
        from app.core import pii_crypto

        key = "valid-key-12345678901234567890123=="
        with patch.object(pii_crypto.settings, "pii_previous_keys", f",,{key},"):
            fernets = pii_crypto._get_previous_fernets("email")
        # 只应有 1 个有效密钥
        assert len(fernets) == 1

    def test_multiple_keys_preserve_order(self) -> None:
        """多密钥按顺序返回."""
        from app.core import pii_crypto

        k1 = "key-aa-12345678901234567890123456=="
        k2 = "key-bb-12345678901234567890123456=="
        with patch.object(
            pii_crypto.settings, "pii_previous_keys", f"{k1},{k2}"
        ):
            fernets = pii_crypto._get_previous_fernets("email")
        assert len(fernets) == 2


# ──────────────────────────────────────────────────────────────────
# 7. is_encrypted_with_current_key 密钥轮换检测
# ──────────────────────────────────────────────────────────────────


class TestIsEncryptedWithCurrentKey:
    """is_encrypted_with_current_key 轮换检测测试."""

    def test_none_returns_true(self) -> None:
        """None/空值不需要轮换 → True."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        assert is_encrypted_with_current_key(None, "email") is True
        assert is_encrypted_with_current_key("", "email") is True

    def test_plaintext_returns_true(self) -> None:
        """明文不需要轮换 → True (避免误加密)."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        assert is_encrypted_with_current_key("plain@text.com", "email") is True

    def test_encrypted_with_current_key_returns_true(self) -> None:
        """当前密钥能解密的密文 → True (不需要轮换)."""
        from app.core.pii_crypto import (
            encrypt_field,
            is_encrypted_with_current_key,
        )

        enc = encrypt_field("test@text.com", "email")
        assert is_encrypted_with_current_key(enc, "email") is True

    def test_encrypted_with_other_key_returns_false(self) -> None:
        """其他密钥加密的密文 → False (需要轮换)."""
        from app.core import pii_crypto
        from app.core.pii_crypto import _derive_fernet_key_with_base
        from app.core.pii_crypto import is_encrypted_with_current_key

        # 用其他 base_key 加密
        other_key = _derive_fernet_key_with_base("email", "totally-different-base-key-1234567890")
        other_fernet = Fernet(other_key)
        token = other_fernet.encrypt(b"test@text.com").decode("ascii")

        # 当前密钥下应解不开 → False
        with patch.object(
            pii_crypto.settings, "pii_encryption_key", "current-test-key-different-from-other"
        ):
            assert is_encrypted_with_current_key(f"enc:v1:{token}", "email") is False


# ──────────────────────────────────────────────────────────────────
# 8. EncryptedString TypeDecorator
# ──────────────────────────────────────────────────────────────────


class TestEncryptedStringTypeDecorator:
    """SQLAlchemy EncryptedString TypeDecorator 测试."""

    def test_process_bind_param_none(self) -> None:
        """None → None (不加密)."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="email")
        assert col.process_bind_param(None, dialect="sqlite") is None

    def test_process_bind_param_string_encrypts(self) -> None:
        """字符串 → 加密后密文."""
        from app.core.pii_crypto import EncryptedString, decrypt_field

        col = EncryptedString(100, field="email")
        result = col.process_bind_param("user@example.com", dialect="sqlite")
        assert result is not None
        assert result.startswith("enc:v1:")
        # 可解密回原值
        assert decrypt_field(result, "email") == "user@example.com"

    def test_process_result_value_none(self) -> None:
        """None → None (不解密)."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="email")
        assert col.process_result_value(None, dialect="sqlite") is None

    def test_process_result_value_decrypts(self) -> None:
        """密文 → 明文 (DB 读取时自动解密)."""
        from app.core.pii_crypto import EncryptedString, encrypt_field

        col = EncryptedString(100, field="email")
        enc = encrypt_field("user@example.com", "email")
        result = col.process_result_value(enc, dialect="sqlite")
        assert result == "user@example.com"

    def test_process_bind_param_non_string_passthrough(self) -> None:
        """非字符串值 (如 int) → 原样返回 (避免误加密)."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="email")
        # TypeDecorator 应原样返回非字符串
        assert col.process_bind_param(123, dialect="sqlite") == 123

    def test_impl_length_includes_prefix_overhead(self) -> None:
        """impl_length 包含 enc:v1: 前缀和 base64 扩展的额外空间."""
        from app.core.pii_crypto import ENCRYPTED_PREFIX, EncryptedString

        col = EncryptedString(50, field="email")
        # 应大于原长度
        assert col.impl_length > 50
        # 应包含前缀长度
        assert col.impl_length >= 50 + len(ENCRYPTED_PREFIX)

    def test_field_attribute_set(self) -> None:
        """field 属性被正确设置."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="phone")
        assert col.field == "phone"

    def test_process_result_value_decryption_failure(self) -> None:
        """解密失败时返回 [DECRYPTION_FAILED] 占位 (M-Core-3 修复)."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="email")
        # 有效前缀但无效 token
        result = col.process_result_value(
            "enc:v1:invalid_token_!@#$%^&*()", dialect="sqlite"
        )
        assert result == "[DECRYPTION_FAILED]"


# ──────────────────────────────────────────────────────────────────
# 9. ensure_pii_key / _validate_pii_key_strength 启动检查
# ──────────────────────────────────────────────────────────────────


class TestEnsurePiiKey:
    """ensure_pii_key 启动时密钥检查."""

    def test_ensure_key_passes_with_strong_key(self) -> None:
        """已配置强密钥 → 不抛错."""
        from app.core.pii_crypto import ensure_pii_key

        # conftest 已设置 test 密钥 (32+ 字节), 不应抛错
        ensure_pii_key()

    def test_ensure_key_in_production_without_key_raises(self) -> None:
        """生产环境无密钥 → RuntimeError."""
        from app.core import pii_crypto

        with patch.object(pii_crypto.settings, "pii_encryption_key", ""), patch.object(
            pii_crypto.settings, "app_env", "production"
        ):
            with pytest.raises(RuntimeError, match="PII_ENCRYPTION_KEY must be set"):
                pii_crypto.ensure_pii_key()


class TestValidatePiiKeyStrength:
    """_validate_pii_key_strength 密钥强度校验 (P0-1.2)."""

    def test_known_weak_key_in_production_raises(self) -> None:
        """生产环境使用已知弱密钥 → RuntimeError."""
        from app.core import pii_crypto

        with patch.object(pii_crypto.settings, "app_env", "production"):
            with pytest.raises(RuntimeError, match="known weak value"):
                pii_crypto._validate_pii_key_strength("test")

    def test_known_weak_key_in_dev_warns_only(self) -> None:
        """开发环境使用已知弱密钥 → 仅警告, 不抛错."""
        from app.core import pii_crypto

        # 不应抛错
        with patch.object(pii_crypto.settings, "app_env", "development"):
            pii_crypto._validate_pii_key_strength("test")

    def test_short_key_in_production_raises(self) -> None:
        """生产环境短密钥 → RuntimeError."""
        from app.core import pii_crypto

        with patch.object(pii_crypto.settings, "app_env", "production"):
            with pytest.raises(RuntimeError, match="too short"):
                pii_crypto._validate_pii_key_strength("short")

    def test_short_key_in_dev_warns_only(self) -> None:
        """开发环境短密钥 → 仅警告."""
        from app.core import pii_crypto

        with patch.object(pii_crypto.settings, "app_env", "development"):
            # 不应抛错
            pii_crypto._validate_pii_key_strength("short")

    def test_strong_key_passes(self) -> None:
        """强密钥 (32+ 字节, 非已知弱密钥) → 通过."""
        from app.core import pii_crypto

        # 32+ 字节随机字符串
        pii_crypto._validate_pii_key_strength("x" * 40)
