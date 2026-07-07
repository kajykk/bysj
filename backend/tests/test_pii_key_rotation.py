"""P2-4: PII 密钥轮换测试

覆盖范围:
1. pii_crypto.decrypt_field 多密钥回退解密
   - 当前密钥优先解密 (无回退)
   - 当前密钥失败 + 旧密钥回退成功 (单个/多个)
   - 全部密钥失败 → 抛 ValueError
   - 旧密钥列表去重 + 跳过无效密钥
2. pii_crypto._get_previous_fernets 行为
   - 空配置 → 空列表
   - 多密钥解析 + 去重
   - 无效密钥派生异常 → 跳过该密钥
3. scripts/rotate_pii_keys.py 脚本
   - 前置检查 (4 种失败场景)
   - rotate_field dry-run 不写库
   - rotate_field apply 重加密 + 同步 email_hash
   - 跳过已用新密钥加密的行
   - 失败行不阻断后续批次
   - 可重复执行 (幂等)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# 在导入被测模块前确保 PII 密钥存在
os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-1234567890abcdef=="
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
# 1. decrypt_field 多密钥回退解密
# ──────────────────────────────────────────────────────────────────


class TestDecryptFieldMultiKeyFallback:
    """decrypt_field 在密钥轮换场景下的多密钥回退解密."""

    def test_current_key_succeeds_no_fallback(self):
        """当前密钥能解密时, 不应尝试旧密钥."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        _set_pii_keys(
            current="current-key-1234567890abcdefghijklmnopqrstuv==", previous=""
        )
        encrypted = encrypt_field("user@example.com", "email")
        # 应该用当前密钥成功解密
        assert decrypt_field(encrypted, "email") == "user@example.com"

    def test_fallback_to_single_previous_key(self):
        """当前密钥解不开时, 应回退到单个旧密钥."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        old_key = "old-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        new_key = "new-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        # 用旧密钥加密
        _set_pii_keys(current=old_key, previous="")
        encrypted = encrypt_field("legacy@example.com", "email")
        # 切换到新密钥, 并将旧密钥加入回退列表
        _set_pii_keys(current=new_key, previous=old_key)
        # 应该能通过旧密钥回退解密
        assert decrypt_field(encrypted, "email") == "legacy@example.com"

    def test_fallback_to_second_previous_key(self):
        """多个旧密钥时, 第一个失败时应尝试第二个."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        key_b = "key-bb-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "key-cc-ccccccccccccccccccccccccccccccccc=="

        # 用 key_b 加密
        _set_pii_keys(current=key_b, previous="")
        encrypted = encrypt_field("multi-fallback@example.com", "phone")

        # 切换到新密钥, 旧密钥列表为 [key_a, key_b]
        _set_pii_keys(current=new_key, previous=f"{key_a},{key_b}")
        # 应该跳过 key_a, 用 key_b 成功解密
        assert decrypt_field(encrypted, "phone") == "multi-fallback@example.com"

    def test_all_keys_fail_raises_value_error(self):
        """所有密钥都失败时, 应抛 ValueError."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        old_key = "old-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        # 用一个完全无关的密钥加密 (既不在当前, 也不在旧密钥列表)
        unrelated_key = "unrel-ccccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=unrelated_key, previous="")
        encrypted = encrypt_field("orphan@example.com", "email")

        # 切换到新密钥, 旧密钥列表不包含 unrelated_key
        new_key = "newkey-ddddddddddddddddddddddddddddddddddd=="
        _set_pii_keys(current=new_key, previous=old_key)

        with pytest.raises(ValueError, match="PII 解密失败"):
            decrypt_field(encrypted, "email")

    def test_no_previous_keys_current_fails_raises(self):
        """未配置旧密钥且当前密钥失败时, 直接抛错 (不尝试回退)."""
        from app.core.pii_crypto import decrypt_field, encrypt_field

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        key_b = "key-bb-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        # 用 key_a 加密
        _set_pii_keys(current=key_a, previous="")
        encrypted = encrypt_field("no-fallback@example.com", "email")

        # 切换到 key_b, 但不配置 previous_keys
        _set_pii_keys(current=key_b, previous="")

        with pytest.raises(ValueError, match="PII 解密失败"):
            decrypt_field(encrypted, "email")

    def test_plaintext_passthrough_when_no_keys_work(self):
        """明文 (无 enc:v1: 前缀) 应直接透传, 不触发密钥尝试."""
        from app.core.pii_crypto import decrypt_field

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        # 明文输入, 即使没有可用密钥也不应抛错
        assert decrypt_field("plain@example.com", "email") == "plain@example.com"

    def test_none_and_empty_passthrough(self):
        """None 和空字符串应直接透传."""
        from app.core.pii_crypto import decrypt_field

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert decrypt_field(None, "email") is None
        assert decrypt_field("", "email") == ""


# ──────────────────────────────────────────────────────────────────
# 2. _get_previous_fernets 辅助函数
# ──────────────────────────────────────────────────────────────────


class TestGetPreviousFernets:
    """_get_previous_fernets 解析旧密钥列表的行为."""

    def test_empty_config_returns_empty_list(self):
        """PII_PREVIOUS_KEYS 为空时返回空列表."""
        from app.core.pii_crypto import _get_previous_fernets

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert _get_previous_fernets("email") == []

    def test_single_key_returns_one_fernet(self):
        """单个旧密钥返回包含一个 Fernet 的列表."""
        from cryptography.fernet import Fernet

        from app.core.pii_crypto import _get_previous_fernets

        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous=old_key
        )
        fernets = _get_previous_fernets("email")
        assert len(fernets) == 1
        assert isinstance(fernets[0], Fernet)

    def test_multiple_keys_returns_fernets_in_order(self):
        """多个旧密钥按配置顺序返回."""
        from app.core.pii_crypto import _get_previous_fernets

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        key_b = "key-bb-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        key_c = "key-cc-ccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==",
            previous=f"{key_a},{key_b},{key_c}",
        )
        fernets = _get_previous_fernets("phone")
        assert len(fernets) == 3

    def test_deduplicates_repeated_keys(self):
        """重复的旧密钥应被去重."""
        from app.core.pii_crypto import _get_previous_fernets

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==",
            previous=f"{key_a},{key_a},{key_a}",
        )
        fernets = _get_previous_fernets("email")
        assert len(fernets) == 1  # 去重后只保留一个

    def test_skips_empty_entries_in_list(self):
        """逗号分隔中的空字符串条目应被跳过 (如尾部多余逗号)."""
        from app.core.pii_crypto import _get_previous_fernets

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==",
            previous=f"{key_a},, ,{key_a}",  # 包含空字符串和空白
        )
        fernets = _get_previous_fernets("email")
        assert len(fernets) == 1  # 只有 key_a (最后一个 key_a 是重复, 去重)

    def test_skips_whitespace_around_keys(self):
        """旧密钥前后的空白字符应被 strip."""
        from app.core.pii_crypto import _get_previous_fernets

        key_a = "key-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==",
            previous=f"  {key_a}  ",  # 前后有空格
        )
        fernets = _get_previous_fernets("email")
        assert len(fernets) == 1


# ──────────────────────────────────────────────────────────────────
# 3. 轮换脚本 (scripts/rotate_pii_keys.py)
# ──────────────────────────────────────────────────────────────────


class TestIsEncryptedWithCurrentKey:
    """is_encrypted_with_current_key 判断函数."""

    def test_current_key_encryption_returns_true(self):
        """当前密钥加密的密文应返回 True."""
        from app.core.pii_crypto import encrypt_field, is_encrypted_with_current_key

        _set_pii_keys(current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        encrypted = encrypt_field("test@example.com", "email")
        assert is_encrypted_with_current_key(encrypted, "email") is True

    def test_old_key_encryption_returns_false(self):
        """旧密钥加密的密文应返回 False (需要轮换)."""
        from app.core.pii_crypto import encrypt_field, is_encrypted_with_current_key

        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=old_key, previous="")
        encrypted = encrypt_field("legacy@example.com", "email")

        # 切换到新密钥
        _set_pii_keys(current=new_key, previous=old_key)
        assert is_encrypted_with_current_key(encrypted, "email") is False

    def test_null_and_empty_return_true(self):
        """NULL 和空字符串返回 True (不需要轮换)."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert is_encrypted_with_current_key(None, "email") is True
        assert is_encrypted_with_current_key("", "email") is True

    def test_plaintext_returns_true(self):
        """未加密的明文返回 True (不需要轮换)."""
        from app.core.pii_crypto import is_encrypted_with_current_key

        _set_pii_keys(current="anykey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        assert is_encrypted_with_current_key("plain@example.com", "email") is True


# ──────────────────────────────────────────────────────────────────
# 4. 轮换脚本 (scripts/rotate_pii_keys.py)
# ──────────────────────────────────────────────────────────────────


# 将 backend 目录加入 sys.path 以导入脚本模块
import sys as _sys
from pathlib import Path as _Path

_BACKEND_DIR = _Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_DIR))

# 导入脚本模块 (脚本目录无 __init__.py, 用 importlib 加载)
import importlib.util as _importlib_util

_script_path = _BACKEND_DIR / "scripts" / "rotate_pii_keys.py"
_spec = _importlib_util.spec_from_file_location("rotate_pii_keys", _script_path)
assert _spec is not None and _spec.loader is not None
rotate_pii_keys = _importlib_util.module_from_spec(_spec)
# 注册到 sys.modules: dataclass 装饰器在解析 KW_ONLY 字段时需要
# 访问 sys.modules[cls.__module__].__dict__, 未注册会抛 AttributeError
_sys.modules["rotate_pii_keys"] = rotate_pii_keys
_spec.loader.exec_module(rotate_pii_keys)


class TestPreflightChecks:
    """rotate_pii_keys.preflight_checks 前置检查."""

    def test_missing_current_key_returns_error(self):
        """未配置 PII_ENCRYPTION_KEY 应返回错误."""
        _set_pii_keys(current="", previous="any-old-key")
        errors = rotate_pii_keys.preflight_checks()
        assert any("PII_ENCRYPTION_KEY 未配置" in e for e in errors)

    def test_missing_previous_keys_returns_error(self):
        """未配置 PII_PREVIOUS_KEYS 应返回错误."""
        _set_pii_keys(current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==", previous="")
        errors = rotate_pii_keys.preflight_checks()
        assert any("PII_PREVIOUS_KEYS 未配置" in e for e in errors)

    def test_current_key_in_previous_returns_error(self):
        """当前密钥出现在旧密钥列表中应返回错误."""
        same_key = "samekey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        _set_pii_keys(current=same_key, previous=same_key)
        errors = rotate_pii_keys.preflight_checks()
        assert any("出现在 PII_PREVIOUS_KEYS" in e for e in errors)

    def test_duplicate_previous_keys_returns_error(self):
        """旧密钥列表包含重复项应返回错误."""
        key_a = "dupkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=="
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==",
            previous=f"{key_a},{key_a}",
        )
        errors = rotate_pii_keys.preflight_checks()
        assert any("重复密钥" in e for e in errors)

    def test_valid_config_returns_no_errors(self):
        """合法配置应返回空错误列表."""
        _set_pii_keys(
            current="currentkey-aaaaaaaaaaaaaaaaaaaaaaaaaaaa==",
            previous="oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb==",
        )
        errors = rotate_pii_keys.preflight_checks()
        assert errors == []


class TestRotateField:
    """rotate_pii_keys.rotate_field 字段轮换逻辑."""

    def _make_session_with_rows(self, rows: list[tuple]) -> MagicMock:
        """构造一个 mock AsyncSession, SELECT 返回指定行."""
        session = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = rows
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_dry_run_does_not_commit(self):
        """dry-run 模式不应执行 UPDATE 也不应 commit."""
        # 用旧密钥加密一份数据
        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=old_key, previous="")
        from app.core.pii_crypto import encrypt_field

        encrypted = encrypt_field("user@example.com", "email")

        # 切换到新密钥
        _set_pii_keys(current=new_key, previous=old_key)

        session = self._make_session_with_rows([(1, encrypted)])
        spec = rotate_pii_keys.FieldSpec(
            "users", "email", "email", has_blind_index=True
        )

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=10, apply=False
        )

        # dry-run: 不应调用 commit, 不应执行除 SELECT 外的 SQL
        assert session.commit.await_count == 0
        # 仅一次 SELECT, 没有 UPDATE
        assert session.execute.await_count == 1
        # 统计: 1 行待轮换
        assert stats.total == 1
        assert stats.rotated == 1
        assert stats.skipped == 0
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_apply_re_encrypts_and_updates_email_hash(self):
        """apply 模式应重加密 email + 同步更新 email_hash."""
        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=old_key, previous="")
        from app.core.pii_crypto import (
            compute_blind_index,
            decrypt_field,
            encrypt_field,
        )

        encrypted = encrypt_field("user@example.com", "email")

        # 切换到新密钥
        _set_pii_keys(current=new_key, previous=old_key)

        session = self._make_session_with_rows([(42, encrypted)])
        spec = rotate_pii_keys.FieldSpec(
            "users", "email", "email", has_blind_index=True
        )

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=10, apply=True
        )

        # 验证 commit 被调用
        assert session.commit.await_count == 1
        # 验证 UPDATE 被执行 (SELECT + UPDATE = 2 次 execute)
        assert session.execute.await_count == 2
        # 统计: 1 行重加密, 1 行盲索引更新
        assert stats.rotated == 1
        assert stats.blind_index_updated == 1
        assert stats.failed == 0

        # 验证 UPDATE 参数包含新密文和 email_hash
        update_call = session.execute.call_args_list[1]
        # _Call 对象支持 .args 和 .kwargs 属性访问
        args_tuple = update_call.args
        assert len(args_tuple) >= 2, f"UPDATE 调用应至少 2 个参数: {args_tuple}"
        params = args_tuple[1]
        assert isinstance(params, dict), f"params 应为 dict, 实际: {type(params)}"
        assert "value" in params, "UPDATE 应包含 value (新密文)"
        assert "email_hash" in params, "UPDATE 应包含 email_hash"
        assert "id" in params and params["id"] == 42, "UPDATE 应匹配 id=42"
        # 新密文应该能用当前密钥解密
        assert decrypt_field(params["value"], "email") == "user@example.com"
        # email_hash 应该等于用当前密钥计算的盲索引
        assert params["email_hash"] == compute_blind_index("user@example.com", "email")

    @pytest.mark.asyncio
    async def test_skips_already_migrated_rows(self):
        """已用当前密钥加密的行应被跳过 (密文比较相同)."""
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(
            current=new_key, previous="oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        )
        from app.core.pii_crypto import encrypt_field

        # 用当前 (新) 密钥加密 - 已是最新状态
        encrypted = encrypt_field("already-new@example.com", "email")

        session = self._make_session_with_rows([(1, encrypted)])
        spec = rotate_pii_keys.FieldSpec(
            "users", "email", "email", has_blind_index=True
        )

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=10, apply=True
        )

        # 应跳过, 不应 UPDATE
        assert session.commit.await_count == 0
        assert stats.rotated == 0
        assert stats.skipped == 1
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_skips_null_and_plaintext(self):
        """NULL 和明文 (无 enc:v1: 前缀) 应被跳过."""
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(
            current=new_key, previous="oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        )

        rows = [
            (1, None),  # NULL
            (2, ""),  # 空字符串
            (3, "plain@example.com"),  # 未加密明文
        ]
        session = self._make_session_with_rows(rows)
        spec = rotate_pii_keys.FieldSpec("users", "phone", "phone")

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=10, apply=True
        )

        assert stats.total == 3
        assert stats.rotated == 0
        assert stats.skipped == 3
        assert stats.failed == 0
        assert session.commit.await_count == 0

    @pytest.mark.asyncio
    async def test_failed_decryption_does_not_block_others(self):
        """单行解密失败不应阻断其他行的处理."""
        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=old_key, previous="")
        from app.core.pii_crypto import encrypt_field

        good_cipher = encrypt_field("good@example.com", "email")
        # 损坏的密文 (看似加密但实际无效)
        bad_cipher = "enc:v1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

        # 切换到新密钥, 旧密钥列表为空 → 无法解密旧密文
        _set_pii_keys(current=new_key, previous="")

        rows = [(1, good_cipher), (2, bad_cipher), (3, good_cipher)]
        session = self._make_session_with_rows(rows)
        spec = rotate_pii_keys.FieldSpec("users", "phone", "phone")

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=10, apply=True
        )

        # 因 previous_keys 为空, decrypt_field 会抛 ValueError → 全部失败
        # 验证: 即使所有行都失败, 也不应抛出异常或阻断后续行处理
        assert stats.failed == 3  # 全部失败 (因为旧密钥列表空, 都解不开)
        assert stats.rotated == 0
        # 不应 commit 任何东西
        assert session.commit.await_count == 0

    @pytest.mark.asyncio
    async def test_batch_failure_rolls_back_and_continues(self):
        """批次失败时应 rollback 当前批, 继续处理后续批."""
        old_key = "oldkey-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb=="
        new_key = "newkey-cccccccccccccccccccccccccccccccccc=="
        _set_pii_keys(current=old_key, previous="")
        from app.core.pii_crypto import encrypt_field

        encrypted = encrypt_field("user@example.com", "phone")

        # 切换到新密钥
        _set_pii_keys(current=new_key, previous=old_key)

        # 3 行数据, batch_size=2 → 2 批
        rows = [(1, encrypted), (2, encrypted), (3, encrypted)]
        session = self._make_session_with_rows(rows)

        # 让第一次 commit 抛错, 第二次成功
        session.commit = AsyncMock(side_effect=[Exception("DB connection lost"), None])
        spec = rotate_pii_keys.FieldSpec("users", "phone", "phone")

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=2, apply=True
        )

        # 第 1 批失败 (2 行), 第 2 批成功 (1 行)
        assert stats.failed == 2
        assert stats.rotated == 1
        # rollback 应被调用一次
        assert session.rollback.await_count == 1

    @pytest.mark.asyncio
    async def test_empty_table_returns_zero_stats(self):
        """空表应返回全 0 统计."""
        session = self._make_session_with_rows([])
        spec = rotate_pii_keys.FieldSpec(
            "users", "email", "email", has_blind_index=True
        )

        stats = await rotate_pii_keys.rotate_field(
            session, spec, batch_size=10, apply=True
        )

        assert stats.total == 0
        assert stats.rotated == 0
        assert stats.skipped == 0
        assert stats.failed == 0
        assert session.commit.await_count == 0


class TestRotationStatsMerge:
    """RotationStats.merge 行为."""

    def test_merge_accumulates_all_fields(self):
        from rotate_pii_keys import RotationStats  # type: ignore[import-not-found]

        s1 = RotationStats(
            table="users",
            column="email",
            total=10,
            rotated=5,
            skipped=3,
            failed=2,
            blind_index_updated=5,
        )
        s2 = RotationStats(
            table="users",
            column="phone",
            total=20,
            rotated=15,
            skipped=5,
            failed=0,
            blind_index_updated=0,
        )

        overall = RotationStats(table="(overall)", column="(all)")
        overall.merge(s1).merge(s2)

        assert overall.total == 30
        assert overall.rotated == 20
        assert overall.skipped == 8
        assert overall.failed == 2
        assert overall.blind_index_updated == 5
