"""Tests for v1.27 PII encryption and GDPR service.

覆盖的安全加固点:
1. pii_crypto: 加密/解密 roundtrip + 字段派生密钥
2. pii_crypto: ENCRYPTED_PREFIX 检测与兼容
3. pii_crypto: mask_pii 脱敏
4. pii_crypto: EncryptedString TypeDecorator
5. gdpr_service: 导出包含所有用户数据
6. gdpr_service: 匿名化需密码验证
7. gdpr_service: 匿名化撤销所有 session
8. gdpr_service: 匿名化保留 OperationLog
9. gdpr API: 端点存在并要求登录
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# 在导入被测模块前确保 PII 密钥存在
os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-1234567890abcdef==")


@pytest.fixture(autouse=True)
def _ensure_pii_key():
    """每个测试前确保 PII 密钥已设置 (覆盖 settings 已被 pydantic 加载的情况)."""
    from app.core import pii_crypto
    from app.core.config import settings

    test_key = "test-pii-key-for-unit-tests-1234567890abcdef=="
    if not settings.pii_encryption_key:
        object.__setattr__(settings, "pii_encryption_key", test_key)
    if not pii_crypto.settings.pii_encryption_key:
        object.__setattr__(pii_crypto.settings, "pii_encryption_key", test_key)
    yield


class TestPIICrypto:
    """PII 字段加密层测试."""

    def test_encrypt_decrypt_roundtrip(self):
        """同一字段的加密解密 roundtrip 应正确."""
        from app.core.pii_crypto import encrypt_field, decrypt_field

        original = "user@example.com"
        encrypted = encrypt_field(original, "email")
        assert encrypted != original
        assert encrypted.startswith("enc:v1:")
        assert decrypt_field(encrypted, "email") == original

    def test_different_fields_have_different_keys(self):
        """不同字段的密文应不同（即使明文相同）."""
        from app.core.pii_crypto import encrypt_field

        email_enc = encrypt_field("samevalue", "email")
        phone_enc = encrypt_field("samevalue", "phone")
        assert email_enc != phone_enc

    def test_empty_value_passthrough(self):
        """空值/None 应直接透传, 不加密."""
        from app.core.pii_crypto import encrypt_field, decrypt_field

        assert encrypt_field("", "email") == ""
        assert encrypt_field(None, "email") is None
        assert decrypt_field("", "email") == ""
        assert decrypt_field(None, "email") is None

    def test_double_encryption_prevented(self):
        """已加密的密文不应被重复加密."""
        from app.core.pii_crypto import encrypt_field, decrypt_field

        original = "test@example.com"
        encrypted = encrypt_field(original, "email")
        re_encrypted = encrypt_field(encrypted, "email")
        assert encrypted == re_encrypted
        assert decrypt_field(re_encrypted, "email") == original

    def test_plaintext_passthrough_on_decrypt(self):
        """未加密的明文在解密时直接返回 (向后兼容)."""
        from app.core.pii_crypto import decrypt_field

        plain = "not-encrypted-yet@example.com"
        assert decrypt_field(plain, "email") == plain

    def test_mask_pii_full(self):
        """完全脱敏."""
        from app.core.pii_crypto import mask_pii

        assert mask_pii("user@example.com") == "*" * 16  # 16 chars total
        assert mask_pii("") == ""
        assert mask_pii(None) == ""

    def test_mask_pii_keep_last(self):
        """保留末尾 N 个字符 (用于显示)."""
        from app.core.pii_crypto import mask_pii

        # 11 chars total, keep_last=4 → 7 stars + "8000" = 11 chars
        assert mask_pii("13800138000", keep_last=4) == "*" * 7 + "8000"
        assert mask_pii("abc", keep_last=4) == "***"  # len <= keep_last

    def test_encrypted_string_type_decorator(self):
        """EncryptedString SQLAlchemy TypeDecorator."""
        from app.core.pii_crypto import EncryptedString

        col = EncryptedString(100, field="email")
        # process_bind_param 应加密
        encrypted = col.process_bind_param("user@test.com", dialect=MagicMock())
        assert encrypted.startswith("enc:v1:")
        # process_result_value 应解密
        plain = col.process_result_value(encrypted, dialect=MagicMock())
        assert plain == "user@test.com"
        # None 应直接透传
        assert col.process_bind_param(None, MagicMock()) is None
        assert col.process_result_value(None, MagicMock()) is None

    def test_ensure_pii_key_in_dev_generates(self):
        """开发环境缺失密钥时, ensure_pii_key 应生成临时密钥."""
        from app.core import pii_crypto

        original = pii_crypto.settings.pii_encryption_key
        pii_crypto.settings.pii_encryption_key = ""
        try:
            # 模拟 development 环境
            with patch.object(pii_crypto.settings, "app_env", "development"):
                pii_crypto.ensure_pii_key()
                assert pii_crypto.settings.pii_encryption_key  # 已生成
        finally:
            pii_crypto.settings.pii_encryption_key = original

    def test_ensure_pii_key_in_prod_raises(self):
        """生产环境缺失密钥时, ensure_pii_key 应抛异常."""
        from app.core import pii_crypto

        original = pii_crypto.settings.pii_encryption_key
        pii_crypto.settings.pii_encryption_key = ""
        try:
            with patch.object(pii_crypto.settings, "app_env", "production"):
                with pytest.raises(RuntimeError, match="PII_ENCRYPTION_KEY"):
                    pii_crypto.ensure_pii_key()
        finally:
            pii_crypto.settings.pii_encryption_key = original


class TestGDPRServiceExport:
    """GDPRService.export_user_data 测试."""

    @pytest.mark.asyncio
    async def test_export_returns_full_structure(self):
        """导出应返回完整数据结构."""
        from app.services.gdpr_service import GDPRService

        # 模拟 DB 会话
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "enc:v1:abc"  # 假装是密文
        mock_user.email = "enc:v1:xyz"
        mock_user.phone = None
        mock_user.role = "user"
        mock_user.status = "active"
        mock_user.created_at = None
        mock_user.last_login_at = None

        mock_db = AsyncMock()
        # 第一次 get(User) → user
        # 之后的 execute() 调用都返回空结果
        mock_db.get.return_value = mock_user

        # 模拟所有 select 查询返回空
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = empty_result

        service = GDPRService(mock_db)
        result = await service.export_user_data(1)

        # 验证关键字段
        assert "export_metadata" in result
        assert "account" in result
        assert "profile" in result
        assert "emergency_contacts" in result
        assert "counselor_bindings" in result
        assert "risk_assessments" in result
        assert "warnings" in result
        assert "crisis_events" in result
        assert "intervention_plans" in result
        assert "intervention_tasks" in result
        assert "operation_logs" in result
        assert "summary" in result
        assert result["export_metadata"]["user_id"] == 1
        assert result["export_metadata"]["gdpr_articles"][0] == "Article 15 (Access)"

    @pytest.mark.asyncio
    async def test_export_raises_for_missing_user(self):
        """不存在的用户应抛 ValueError."""
        from app.services.gdpr_service import GDPRService

        mock_db = AsyncMock()
        mock_db.get.return_value = None

        service = GDPRService(mock_db)
        with pytest.raises(ValueError, match="用户不存在"):
            await service.export_user_data(999)


class TestGDPRServiceAnonymize:
    """GDPRService.anonymize_user 测试."""

    @pytest.mark.asyncio
    async def test_anonymize_requires_password(self):
        """错误的密码应被拒绝."""
        from app.services.gdpr_service import GDPRService

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "user@test.com"
        mock_user.status = "active"
        mock_user.password_hash = "hashed_pwd"

        mock_db = AsyncMock()
        mock_db.get.return_value = mock_user

        with patch("app.services.gdpr_service.verify_password", return_value=False):
            service = GDPRService(mock_db)
            with pytest.raises(ValueError, match="密码错误"):
                await service.anonymize_user(1, password_confirm="wrong")

    @pytest.mark.asyncio
    async def test_anonymize_already_deleted_raises(self):
        """已删除用户重复删除应被拒绝."""
        from app.services.gdpr_service import GDPRService

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.status = "deleted"

        mock_db = AsyncMock()
        mock_db.get.return_value = mock_user

        service = GDPRService(mock_db)
        with pytest.raises(ValueError, match="已被删除"):
            await service.anonymize_user(1, password_confirm="any")

    @pytest.mark.asyncio
    async def test_anonymize_succeeds_with_correct_password(self):
        """正确密码应完成匿名化, 写 OperationLog, 撤销 sessions."""
        from app.services.gdpr_service import GDPRService

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.username = "realuser"
        mock_user.email = "user@test.com"
        mock_user.phone = "13800138000"
        mock_user.password_hash = "hashed_pwd"
        mock_user.status = "active"
        mock_user.avatar_url = None

        mock_db = AsyncMock()
        mock_db.get.return_value = mock_user
        # 所有 execute() 返回空 (无 profile/contacts/bindings/sessions)
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = empty_result

        with patch("app.services.gdpr_service.verify_password", return_value=True):
            service = GDPRService(mock_db)
            result = await service.anonymize_user(42, password_confirm="correct")

        # 验证用户被匿名化
        assert mock_user.status == "deleted"
        assert mock_user.username.startswith("anon_")
        assert "@deleted.local" in mock_user.email
        assert mock_user.phone is None

        # 验证 OperationLog 被创建
        mock_db.add.assert_called_once()
        added = mock_db.add.call_args[0][0]
        assert added.action_type == "gdpr.account.deleted"
        assert added.operator_id == 42
        assert added.target_id == 42

        # 验证 commit
        mock_db.commit.assert_called_once()

        # 验证返回结果
        assert result["user_id"] == 42
        assert result["contacts_anonymized"] == 0
        assert result["sessions_revoked"] == 0
        assert "original_email_masked" in result


class TestGDPRAPIEndpoints:
    """GDPR API 端点测试 (路由存在性 + 鉴权)."""

    def test_export_endpoint_requires_auth(self):
        """未登录访问 /user/gdpr/export 应返回 401."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.gdpr import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/user/gdpr/export")
        assert resp.status_code in (401, 403)

    def test_delete_endpoint_requires_auth(self):
        """未登录访问 /user/gdpr/delete 应返回 401."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.gdpr import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/user/gdpr/delete", json={"password": "x", "confirm": True})
        assert resp.status_code in (401, 403)

    def test_delete_endpoint_requires_confirm(self):
        """未传 confirm=true 应返回 400."""
        from fastapi import FastAPI, Depends
        from fastapi.testclient import TestClient
        from app.api.v1.gdpr import router
        from app.core.deps import get_current_user
        from app.models.user import User

        # 绕过认证
        async def fake_user():
            return User(id=1, role="user")

        app = FastAPI()
        app.dependency_overrides[get_current_user] = fake_user
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/user/gdpr/delete", json={"password": "x", "confirm": False})
        assert resp.status_code == 400
        assert "确认" in resp.json()["detail"]
