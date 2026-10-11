"""P0-FIX-2026-10-11: 密码重置令牌必须**一次性核销**，不可重放。

背景（来自 2026-10-11 全量源码审查）：

``auth_service.reset_password`` 修复前只校验签名与 ``exp``，令牌在有效期内
（``password_reset_token_expire_minutes``，默认 30 分钟）可**无限次**使用。
后果不是「多改一次密码」而是账号接管：

* 攻击者截获一封重置邮件（邮箱历史记录、日志/代理里的明文 URL、被盗的
  收件箱）后，可在受害者已改密之后**再次**用它把密码改回攻击者已知值；
* 受害者改密成功后令牌仍在有效期内，任何拿到链接的人都能登入。

修复：复用 ``app.core.token_blocklist``（jti 级撤销），
与 ``logout`` / ``change_password`` 同一套基础设施，不引入新表新依赖。

本文件覆盖三类性质：
1. 正常路径：首次重置成功，令牌被写入 blocklist；
2. 重放：同一令牌第二次使用必须被拒，且**不会**再次改动密码；
3. 失败关闭：撤销状态查不到（Redis 不可用）时拒绝重置，而不是放行。
"""

from __future__ import annotations

import pytest

from app.core.cache import CacheUnavailableError
from app.schemas.auth import ResetPasswordRequest
from app.services.auth_service import AuthService

SEED_EMAIL = "seed@test.com"


def _token(user_id: int, email: str = SEED_EMAIL) -> str:
    from app.core.security import create_password_reset_token

    return create_password_reset_token({"sub": str(user_id), "email": email})


def _payload(token: str, password: str = "newpass123", email: str = SEED_EMAIL):
    return ResetPasswordRequest(
        reset_token=token, new_password=password, email=email
    )


@pytest.fixture
def service(db_session):
    return AuthService(db_session)


async def _password_matches(db_session, user_id: int, plain: str) -> bool:
    from sqlalchemy import select

    from app.core.security import verify_password
    from app.models.user import User

    user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    return verify_password(plain, user.password_hash)


class TestResetTokenIsOneTime:
    async def test_first_use_succeeds_and_marks_token_consumed(
        self, service, db_session, seeded_user_id, in_memory_token_blocklist
    ):
        from app.core.security import decode_token

        token = _token(seeded_user_id)
        jti = decode_token(token)["jti"]
        assert jti not in in_memory_token_blocklist

        await service.reset_password(_payload(token, "brandnewpass1"))

        assert await _password_matches(db_session, seeded_user_id, "brandnewpass1")
        assert jti in in_memory_token_blocklist, (
            "重置成功后未核销令牌 —— 同一链接仍可被重放"
        )

    async def test_replaying_same_token_is_rejected(
        self, service, db_session, seeded_user_id, in_memory_token_blocklist
    ):
        """核心断言：第二次使用必须抛错，且密码**不再**被改动。"""
        token = _token(seeded_user_id)

        await service.reset_password(_payload(token, "firstpassword1"))
        assert await _password_matches(db_session, seeded_user_id, "firstpassword1")

        # 攻击者拿着同一条链接重放，试图改回自己知道的密码
        with pytest.raises(ValueError, match="已被使用"):
            await service.reset_password(_payload(token, "attackerpassword1"))

        assert await _password_matches(
            db_session, seeded_user_id, "firstpassword1"
        ), "重置令牌被重放后密码仍被改动 —— 账号接管链路成立"

    async def test_distinct_tokens_remain_independent(
        self, service, db_session, seeded_user_id, in_memory_token_blocklist
    ):
        """核销只针对单个 jti，不应误伤同一用户另一次申请的令牌。"""
        t1 = _token(seeded_user_id)
        t2 = _token(seeded_user_id)

        await service.reset_password(_payload(t1, "passwordnumber1"))
        await service.reset_password(_payload(t2, "passwordnumber2"))

        assert await _password_matches(db_session, seeded_user_id, "passwordnumber2")

    async def test_token_without_jti_is_rejected(
        self, service, seeded_user_id, in_memory_token_blocklist
    ):
        """缺 jti 的令牌无法核销 —— 必须拒绝而不是跳过校验。"""
        import jwt

        from app.core.security import _get_signing_key
        from app.core.config import settings

        forged = jwt.encode(
            {
                "sub": str(seeded_user_id),
                "email": SEED_EMAIL,
                "type": "password_reset",
                "exp": 9999999999,
                # 故意不带 jti
            },
            _get_signing_key(),
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(ValueError, match="缺少必要信息"):
            await service.reset_password(_payload(forged))


class TestResetTokenFailClosed:
    """撤销状态查不到时必须拒绝，不能静默降级为「令牌可重放」。"""

    async def test_cache_unavailable_denies_reset(
        self, service, db_session, seeded_user_id, monkeypatch
    ):
        from app.core import token_blocklist as tb

        async def _boom(jti: str) -> bool:
            raise CacheUnavailableError("redis down")

        monkeypatch.setattr(tb, "is_token_revoked", _boom)

        with pytest.raises(ValueError, match="重置服务暂时不可用"):
            await service.reset_password(_payload(_token(seeded_user_id)))

        # 密码未被改动
        assert not await _password_matches(db_session, seeded_user_id, "newpass123")


class TestResetTokenRevokesRefreshSessions:
    """既有行为不得回退：重置后仍需撤销全部 refresh token。"""

    async def test_refresh_sessions_revoked_after_reset(
        self, service, db_session, seeded_user_id, in_memory_token_blocklist
    ):
        from datetime import datetime, timezone, timedelta

        from app.models.auth import RefreshTokenSession

        session_row = RefreshTokenSession(
            jti="rt-1",
            user_id=seeded_user_id,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
            revoked_at=None,
        )
        db_session.add(session_row)
        await db_session.flush()

        await service.reset_password(_payload(_token(seeded_user_id)))

        await db_session.refresh(session_row)
        assert session_row.revoked_at is not None, "重置密码后旧 refresh token 未撤销"