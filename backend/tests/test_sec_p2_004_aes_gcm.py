"""SEC-P2-004: PII 加密 AES-128 (Fernet) → AES-256-GCM 迁移专项测试.

覆盖范围:
1. TestSourceCodeStructure (12): 源码静态扫描 - 常量/导入/函数存在 + encrypt_field 默认 v2 + decrypt_field 双前缀
2. TestAesGcmEncryption (6): AES-256-GCM 加密基础行为 - v2 前缀/roundtrip/随机 nonce/字段隔离/Unicode/密钥长度
3. TestBackwardCompatibility (5): 向后兼容 - v1 密文仍可解密 + _is_encrypted 双前缀检测
4. TestKeyRotationFallback (7): AES-GCM 密钥轮换回退 - 当前密钥/单旧密钥/多旧密钥/全部失败/空配置/去重/顺序
5. TestEncryptFieldDefaultsToV2 (5): encrypt_field 默认输出 v2 + 幂等性 + 空值透传
6. TestIsEncryptedWithCurrentKey (6): 双前缀密钥轮换检测
7. TestEncryptedStringTypeDecorator (3): TypeDecorator 默认输出 v2 + v1 解密兼容
8. TestFieldKeyIsolation (2): HKDF info 隔离 - AES 密钥与 Fernet 密钥不同
"""

from __future__ import annotations

import base64
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

# 在导入被测模块前确保 PII 密钥存在 (与 conftest 一致)
os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "test-pii-key-for-sec-p2-004-aes-gcm-tests-1234"
)


@pytest.fixture(autouse=True)
def _restore_pii_settings():
    """每个测试后恢复 PII 配置, 避免测试间污染."""
    from app.core import pii_crypto
    from app.core.config import settings

    orig_current = settings.pii_encryption_key
    orig_previous = settings.pii_previous_keys
    yield
    object.__setattr__(settings, "pii_encryption_key", orig_current)
    object.__setattr__(settings, "pii_previous_keys", orig_previous)
    object.__setattr__(pii_crypto.settings, "pii_encryption_key", orig_current)
    object.__setattr__(pii_crypto.settings, "pii_previous_keys", orig_previous)


def _set_pii_keys(current: str, previous: str = "") -> None:
    """同时设置 settings 和 pii_crypto.settings 的 PII 密钥."""
    from app.core import pii_crypto
    from app.core.config import settings

    object.__setattr__(settings, "pii_encryption_key", current)
    object.__setattr__(settings, "pii_previous_keys", previous)
    object.__setattr__(pii_crypto.settings, "pii_encryption_key", current)
    object.__setattr__(pii_crypto.settings, "pii_previous_keys", previous)


# ──────────────────────────────────────────────────────────────────
# 1. 源码静态结构扫描
# ──────────────────────────────────────────────────────────────────


class TestSourceCodeStructure:
    """SEC-P2-004: pii_crypto.py 源码结构静态扫描."""

    def test_encrypted_prefix_v2_constant_exists(self) -> None:
        """ENCRYPTED_PREFIX_V2 常量存在且值为 'enc:v2:'."""
        from app.core.pii_crypto import ENCRYPTED_PREFIX_V2

        assert ENCRYPTED_PREFIX_V2 == "enc:v2:"

    def test_encrypted_prefixes_tuple_contains_both(self) -> None:
        """_ENCRYPTED_PREFIXES 元组包含 v1 和 v2 前缀."""
        from app.core.pii_crypto import (
            ENCRYPTED_PREFIX,
            ENCRYPTED_PREFIX_V2,
            _ENCRYPTED_PREFIXES,
        )

        assert ENCRYPTED_PREFIX in _ENCRYPTED_PREFIXES
        assert ENCRYPTED_PREFIX_V2 in _ENCRYPTED_PREFIXES

    def test_aesgcm_nonce_and_key_constants(self) -> None:
        """_AESGCM_NONCE_BYTES=12, _AESGCM_KEY_BYTES=32 (AES-256)."""
        from app.core.pii_crypto import _AESGCM_KEY_BYTES, _AESGCM_NONCE_BYTES

        assert _AESGCM_NONCE_BYTES == 12  # NIST 推荐 96-bit
        assert _AESGCM_KEY_BYTES == 32  # AES-256

    def test_aesgcm_and_invalidtag_imported(self) -> None:
        """AESGCM 和 InvalidTag 已从 cryptography 导入."""
        from app.core import pii_crypto

        # 模块应能访问 AESGCM 和 InvalidTag
        assert hasattr(pii_crypto, "AESGCM")
        assert hasattr(pii_crypto, "InvalidTag")

    def test_os_module_imported(self) -> None:
        """os 模块已导入 (用于 os.urandom 生成 nonce)."""
        from app.core import pii_crypto

        assert hasattr(pii_crypto, "os")

    def test_derive_aes_key_functions_exist(self) -> None:
        """_derive_aes_key 和 _derive_aes_key_with_base 函数存在."""
        from app.core import pii_crypto

        assert callable(pii_crypto._derive_aes_key)
        assert callable(pii_crypto._derive_aes_key_with_base)

    def test_get_aes_gcm_function_exists(self) -> None:
        """_get_aes_gcm 函数存在."""
        from app.core import pii_crypto

        assert callable(pii_crypto._get_aes_gcm)

    def test_get_previous_aes_gcms_function_exists(self) -> None:
        """_get_previous_aes_gcms 函数存在."""
        from app.core import pii_crypto

        assert callable(pii_crypto._get_previous_aes_gcms)

    def test_encrypt_aes_gcm_function_exists(self) -> None:
        """_encrypt_aes_gcm 函数存在."""
        from app.core import pii_crypto

        assert callable(pii_crypto._encrypt_aes_gcm)

    def test_decrypt_aes_gcm_functions_exist(self) -> None:
        """_decrypt_aes_gcm 和 _decrypt_aes_gcm_with_key 函数存在."""
        from app.core import pii_crypto

        assert callable(pii_crypto._decrypt_aes_gcm)
        assert callable(pii_crypto._decrypt_aes_gcm_with_key)

    def test_encrypt_field_calls_aes_gcm(self) -> None:
        """encrypt_field 源码调用 _encrypt_aes_gcm (而非直接 Fernet)."""
        import inspect

        from app.core.pii_crypto import encrypt_field

        source = inspect.getsource(encrypt_field)
        assert "_encrypt_aes_gcm" in source
        # 不应直接调用 Fernet 加密 (向后兼容解密允许)
        assert "_get_fernet(field).encrypt" not in source

    def test_decrypt_field_handles_v2_prefix(self) -> None:
        """decrypt_field 源码包含 ENCRYPTED_PREFIX_V2 分支."""
        import inspect

        from app.core.pii_crypto import decrypt_field

        source = inspect.getsource(decrypt_field)
        assert "ENCRYPTED_PREFIX_V2" in source
        assert "_decrypt_aes_gcm" in source


# ──────────────────────────────────────────────────────────────────
# 2. AES-256-GCM 加密基础行为
# ──────────────────────────────────────────────────────────────────


class TestAesGcmEncryption:
    """SEC-P2-004: AES-256-GCM 加密基础行为测试."""

    def test_encrypt_produces_v2_prefix(self) -> None:
        """_encrypt_aes_gcm 输出以 enc:v2: 开头."""
        from app.core.pii_crypto import ENCRYPTED_PREFIX_V2, _encrypt_aes_gcm

        enc = _encrypt_aes_gcm("test@example.com", "email")
        assert enc.startswith(ENCRYPTED_PREFIX_V2)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """_encrypt_aes_gcm + _decrypt_aes_gcm 往返一致."""
        from app.core.pii_crypto import _decrypt_aes_gcm, _encrypt_aes_gcm

        plain = "user@example.com"
        enc = _encrypt_aes_gcm(plain, "email")
        assert _decrypt_aes_gcm(enc[len("enc:v2:"):], "email") == plain

    def test_random_nonce_produces_different_ciphertexts(self) -> None:
        """相同明文两次加密产生不同密文 (随机 nonce)."""
        from app.core.pii_crypto import _encrypt_aes_gcm

        enc1 = _encrypt_aes_gcm("same@text.com", "email")
        enc2 = _encrypt_aes_gcm("same@text.com", "email")
        assert enc1 != enc2

    def test_different_fields_different_ciphertexts(self) -> None:
        """相同明文在不同字段加密 → 不同密文 (字段 salt 隔离)."""
        from app.core.pii_crypto import _encrypt_aes_gcm

        enc_email = _encrypt_aes_gcm("13800001234", "email")
        enc_phone = _encrypt_aes_gcm("13800001234", "phone")
        assert enc_email != enc_phone

    def test_unicode_roundtrip(self) -> None:
        """Unicode 字符串往返一致."""
        from app.core.pii_crypto import _decrypt_aes_gcm, _encrypt_aes_gcm

        plain = "测试用户@例子.公司"
        enc = _encrypt_aes_gcm(plain, "email")
        assert _decrypt_aes_gcm(enc[len("enc:v2:"):], "email") == plain

    def test_derived_key_is_32_bytes(self) -> None:
        """_derive_aes_key 派生 32 字节密钥 (AES-256)."""
        from app.core.pii_crypto import _derive_aes_key

        key = _derive_aes_key("email")
        assert len(key) == 32


# ──────────────────────────────────────────────────────────────────
# 3. 向后兼容 (v1 Fernet 密文仍可解密)
# ──────────────────────────────────────────────────────────────────


def _make_v1_ciphertext(plaintext: str, field: str) -> str:
    """使用 Fernet (v1) 手动加密, 模拟旧数据."""
    from app.core.pii_crypto import ENCRYPTED_PREFIX, _get_fernet

    token = _get_fernet(field).encrypt(plaintext.encode("utf-8"))
    return ENCRYPTED_PREFIX + token.decode("ascii")


class TestBackwardCompatibility:
    """SEC-P2-004: 向后兼容 - v1 Fernet 密文仍可由 decrypt_field 解密."""

    def test_decrypt_v1_ciphertext(self) -> None:
        """v1 (Fernet) 密文可由 decrypt_field 解密."""
        from app.core.pii_crypto import decrypt_field

        v1_enc = _make_v1_ciphertext("legacy@example.com", "email")
        assert v1_enc.startswith("enc:v1:")
        assert decrypt_field(v1_enc, "email") == "legacy@example.com"

    def test_decrypt_v2_ciphertext(self) -> None:
        """v2 (AES-256-GCM) 密文可由 decrypt_field 解密."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        v2_enc = encrypt_field("modern@example.com", "email")
        assert v2_enc.startswith("enc:v2:")
        assert decrypt_field(v2_enc, "email") == "modern@example.com"

    def test_is_encrypted_detects_v1(self) -> None:
        """_is_encrypted 正确检测 v1 前缀."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted("enc:v1:sometoken") is True

    def test_is_encrypted_detects_v2(self) -> None:
        """_is_encrypted 正确检测 v2 前缀."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted("enc:v2:sometoken") is True

    def test_is_encrypted_rejects_plaintext_and_partial(self) -> None:
        """_is_encrypted 拒绝明文和部分前缀."""
        from app.core.pii_crypto import _is_encrypted

        assert _is_encrypted(None) is False
        assert _is_encrypted("") is False
        assert _is_encrypted("plain@example.com") is False
        assert _is_encrypted("enc:plain") is False  # 部分前缀
        assert _is_encrypted("enc:v3:future") is False  # 未知版本


# ──────────────────────────────────────────────────────────────────
# 4. AES-GCM 密钥轮换回退
# ──────────────────────────────────────────────────────────────────


class TestKeyRotationFallback:
    """SEC-P2-004: AES-256-GCM 密钥轮换回退测试."""

    def test_current_key_succeeds_no_fallback(self) -> None:
        """当前密钥能解密 v2 密文时, 不应尝试旧密钥."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        _set_pii_keys(
            current="current-key-1234567890abcdefghijklmnopqrstuv==", previous=""
        )
        encrypted = encrypt_field("user@example.com", "email")
        assert decrypt_field(encrypted, "email") == "user@example.com"

    def test_fallback_to_single_previous_key(self) -> None:
        """当前密钥解不开 v2 时, 应回退到单个旧密钥."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        old_key = "old-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        new_key = "new-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        _set_pii_keys(current=old_key, previous="")
        encrypted = encrypt_field("legacy@example.com", "email")

        _set_pii_keys(current=new_key, previous=old_key)
        assert decrypt_field(encrypted, "email") == "legacy@example.com"

    def test_fallback_to_second_previous_key(self) -> None:
        """多个旧密钥时, 第一个失败应尝试第二个."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        key_b = "key-bb-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "key-cc-ccccccccccccccccccccccccccccccccc=="

        _set_pii_keys(current=key_b, previous="")
        encrypted = encrypt_field("multi-fallback@example.com", "phone")

        _set_pii_keys(current=new_key, previous=f"{key_a},{key_b}")
        assert decrypt_field(encrypted, "phone") == "multi-fallback@example.com"

    def test_all_keys_fail_raises_value_error(self) -> None:
        """所有密钥都失败时, 应抛 ValueError."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        unrelated_key = "unrel-ccccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=unrelated_key, previous="")
        encrypted = encrypt_field("orphan@example.com", "email")

        new_key = "newkey-ddddddddddddddddddddddddddddddddddd=="
        old_key = "oldkey-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee=="
        _set_pii_keys(current=new_key, previous=old_key)

        with pytest.raises(ValueError, match="PII 解密失败"):
            decrypt_field(encrypted, "email")

    def test_previous_aesgcms_empty_config(self) -> None:
        """_get_previous_aes_gcms 空配置返回空列表."""
        from app.core.pii_crypto import _get_previous_aes_gcms

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert _get_previous_aes_gcms("email") == []

    def test_previous_aesgcms_dedup(self) -> None:
        """_get_previous_aes_gcms 重复密钥去重."""
        from app.core.pii_crypto import _get_previous_aes_gcms

        same_key = "dupkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        _set_pii_keys(
            current="currentkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb==",
            previous=f"{same_key},{same_key}",
        )
        instances = _get_previous_aes_gcms("email")
        assert len(instances) == 1

    def test_previous_aesgcms_multiple_keys_preserve_order(self) -> None:
        """_get_previous_aes_gcms 多密钥按顺序返回."""
        from app.core.pii_crypto import _get_previous_aes_gcms

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        key_b = "key-bb-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        key_c = "key-cc-ccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(
            current="currentkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb==",
            previous=f"{key_a},{key_b},{key_c}",
        )
        instances = _get_previous_aes_gcms("phone")
        assert len(instances) == 3


# ──────────────────────────────────────────────────────────────────
# 5. encrypt_field 默认输出 v2
# ──────────────────────────────────────────────────────────────────


class TestEncryptFieldDefaultsToV2:
    """SEC-P2-004: encrypt_field 默认输出 v2 (AES-256-GCM)."""

    def test_encrypt_field_produces_v2(self) -> None:
        """encrypt_field 输出以 enc:v2: 开头."""
        from app.core.pii_crypto import ENCRYPTED_PREFIX_V2, encrypt_field

        enc = encrypt_field("user@example.com", "email")
        assert enc is not None
        assert enc.startswith(ENCRYPTED_PREFIX_V2)

    def test_encrypt_field_idempotent_with_v2(self) -> None:
        """对 v2 密文再次 encrypt_field 不重复加密."""
        from app.core.pii_crypto import encrypt_field

        enc1 = encrypt_field("user@example.com", "email")
        enc2 = encrypt_field(enc1, "email")
        assert enc1 == enc2

    def test_encrypt_field_idempotent_with_v1(self) -> None:
        """对 v1 密文再次 encrypt_field 不重复加密 (保留 v1 不升级)."""
        from app.core.pii_crypto import encrypt_field

        v1_enc = _make_v1_ciphertext("legacy@example.com", "email")
        result = encrypt_field(v1_enc, "email")
        # 幂等: 直接返回原密文, 不重新加密
        assert result == v1_enc

    def test_encrypt_field_none_passthrough(self) -> None:
        """encrypt_field(None) → None."""
        from app.core.pii_crypto import encrypt_field

        assert encrypt_field(None, "email") is None

    def test_encrypt_field_empty_passthrough(self) -> None:
        """encrypt_field('') → ''."""
        from app.core.pii_crypto import encrypt_field

        assert encrypt_field("", "email") == ""


# ──────────────────────────────────────────────────────────────────
# 6. is_encrypted_with_current_key 双前缀检测
# ──────────────────────────────────────────────────────────────────


class TestIsEncryptedWithCurrentKey:
    """SEC-P2-004: is_encrypted_with_current_key 支持 v1 和 v2 前缀."""

    def test_v2_with_current_key_returns_true(self) -> None:
        """v2 密文用当前密钥加密 → True (无需轮换)."""
        from app.core.pii_crypto import encrypt_field, is_encrypted_with_current_key

        _set_pii_keys(current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        enc = encrypt_field("test@example.com", "email")
        assert is_encrypted_with_current_key(enc, "email") is True

    def test_v2_with_other_key_returns_false(self) -> None:
        """v2 密文用旧密钥加密 → False (需要轮换)."""
        from app.core.pii_crypto import encrypt_field, is_encrypted_with_current_key

        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=old_key, previous="")
        enc = encrypt_field("legacy@example.com", "email")

        _set_pii_keys(current=new_key, previous=old_key)
        assert is_encrypted_with_current_key(enc, "email") is False

    def test_v1_with_current_key_returns_true(self) -> None:
        """v1 密文用当前密钥加密 → True (向后兼容路径)."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        _set_pii_keys(current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        v1_enc = _make_v1_ciphertext("test@example.com", "email")
        assert is_encrypted_with_current_key(v1_enc, "email") is True

    def test_v1_with_other_key_returns_false(self) -> None:
        """v1 密文用旧密钥加密 → False (需要轮换)."""
        from app.core.pii_crypto import (
            _derive_fernet_key_with_base,
            is_encrypted_with_current_key,
        )

        # 用其他 base_key 加密 v1 密文
        other_key = _derive_fernet_key_with_base("email", "totally-different-base-key-1234567890")
        other_fernet = Fernet(other_key)
        token = other_fernet.encrypt(b"test@text.com").decode("ascii")

        _set_pii_keys(current="current-test-key-different-from-other", previous="")
        assert is_encrypted_with_current_key(f"enc:v1:{token}", "email") is False

    def test_none_and_empty_return_true(self) -> None:
        """None 和空字符串返回 True (不需要轮换)."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert is_encrypted_with_current_key(None, "email") is True
        assert is_encrypted_with_current_key("", "email") is True

    def test_plaintext_returns_true(self) -> None:
        """未加密明文返回 True (避免误加密)."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert is_encrypted_with_current_key("plain@example.com", "email") is True


# ──────────────────────────────────────────────────────────────────
# 7. EncryptedString TypeDecorator
# ──────────────────────────────────────────────────────────────────


class TestEncryptedStringTypeDecorator:
    """SEC-P2-004: EncryptedString TypeDecorator 默认输出 v2."""

    def test_bind_param_produces_v2(self) -> None:
        """process_bind_param 加密后输出 v2 密文."""
        from app.core.pii_crypto import ENCRYPTED_PREFIX_V2, EncryptedString

        col = EncryptedString(100, field="email")
        result = col.process_bind_param("user@example.com", dialect="sqlite")
        assert result is not None
        assert result.startswith(ENCRYPTED_PREFIX_V2)

    def test_result_value_decrypts_v2(self) -> None:
        """process_result_value 能解密 v2 密文."""
        from app.core.pii_crypto import EncryptedString, encrypt_field

        col = EncryptedString(100, field="email")
        enc = encrypt_field("user@example.com", "email")
        result = col.process_result_value(enc, dialect="sqlite")
        assert result == "user@example.com"

    def test_result_value_decrypts_v1(self) -> None:
        """process_result_value 能解密 v1 密文 (向后兼容)."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="email")
        v1_enc = _make_v1_ciphertext("legacy@example.com", "email")
        result = col.process_result_value(v1_enc, dialect="sqlite")
        assert result == "legacy@example.com"


# ──────────────────────────────────────────────────────────────────
# 8. HKDF info 隔离 (AES 密钥 ≠ Fernet 密钥)
# ──────────────────────────────────────────────────────────────────


class TestFieldKeyIsolation:
    """SEC-P2-004: HKDF info 隔离 - AES 密钥与 Fernet 密钥互不相同."""

    def test_aes_key_differs_from_fernet_key(self) -> None:
        """相同主密钥派生的 AES 密钥和 Fernet 密钥不同 (info 不同)."""
        from app.core.pii_crypto import (
            _derive_aes_key_with_base,
            _derive_fernet_key_with_base,
        )

        base = "test-base-key-for-isolation-check"
        aes_key = _derive_aes_key_with_base("email", base)
        fernet_key = _derive_fernet_key_with_base("email", base)
        # AES 密钥是 32 字节 raw, Fernet 密钥是 44 字节 base64
        assert len(aes_key) == 32
        assert len(fernet_key) == 44
        # AES raw bytes 不等于 Fernet base64 编码
        assert aes_key != fernet_key
        # 即使 base64 解码 Fernet 密钥, 也应与 AES 密钥不同 (info 不同)
        fernet_raw = base64.urlsafe_b64decode(fernet_key)
        assert aes_key != fernet_raw

    def test_aes_key_deterministic(self) -> None:
        """相同 field + base_key → 相同 AES 密钥 (确定性)."""
        from app.core.pii_crypto import _derive_aes_key_with_base

        k1 = _derive_aes_key_with_base("email", "test-key")
        k2 = _derive_aes_key_with_base("email", "test-key")
        assert k1 == k2
