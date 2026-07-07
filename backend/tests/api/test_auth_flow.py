from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.user import User


@pytest.fixture
def clean_db(db_session):
    return db_session


class TestRegister:
    def test_register_success(self, client: TestClient, clean_db):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "id" in body["data"]

    def test_register_duplicate_username(self, client: TestClient, clean_db):
        payload = {
            "username": "dup_user",
            "email": "dup1@test.com",
            "password": "StrongPass123",
            "role": "user",
        }
        client.post("/api/v1/auth/register", json=payload)
        payload["email"] = "dup2@test.com"
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400

    def test_register_short_password(self, client: TestClient, clean_db):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "shortpw",
                "email": "short@test.com",
                "password": "abc",
                "role": "user",
            },
        )
        assert resp.status_code == 422


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_rejects_disabled_user(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "disabled_user",
                "email": "disabled@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )

        user = (
            await clean_db.execute(select(User).where(User.username == "disabled_user"))
        ).scalar_one()
        # P1-D-8: 使用约束允许的合法值 'inactive' (auth_service 通过 status != 'active' 判断禁用)
        user.status = "inactive"
        await clean_db.commit()

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "disabled_user", "password": "StrongPass123"},
        )
        assert resp.status_code == 401

    def test_login_success(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "logintest",
                "email": "login@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "logintest", "password": "StrongPass123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "access_token" in body["data"]
        # H-API-12: refresh_token 不再在响应体返回，通过 httpOnly Cookie 设置
        assert client.cookies.get("refresh_token") is not None

    def test_login_wrong_password(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "wrongpw",
                "email": "wrong@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "wrongpw", "password": "WrongPass999"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient, clean_db):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "Whatever123"},
        )
        assert resp.status_code == 401


class TestRequestReset:
    def test_request_reset_accepts_json_email(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "reset_user",
                "email": "reset@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        resp = client.post(
            "/api/v1/auth/request-reset", json={"email": "reset@test.com"}
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_request_reset_rejects_invalid_email(self, client: TestClient, clean_db):
        resp = client.post("/api/v1/auth/request-reset", json={"email": "not-an-email"})
        assert resp.status_code == 422


class TestTokenRefresh:
    def test_refresh_rotates_token(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "rotator",
                "email": "rotator@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        client.post(
            "/api/v1/auth/login",
            json={"username": "rotator", "password": "StrongPass123"},
        )
        # H-API-12: refresh_token 通过 httpOnly Cookie 返回，不在响应体
        refresh_token = client.cookies.get("refresh_token")

        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["refresh_token"] != refresh_token

    def test_refresh_replay_old_token_rejected(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "replay",
                "email": "replay@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        client.post(
            "/api/v1/auth/login",
            json={"username": "replay", "password": "StrongPass123"},
        )
        # H-API-12: refresh_token 通过 httpOnly Cookie 返回
        refresh_token = client.cookies.get("refresh_token")

        first = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert second.status_code == 401

    def test_refresh_success(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "refresher",
                "email": "refresh@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        client.post(
            "/api/v1/auth/login",
            json={"username": "refresher", "password": "StrongPass123"},
        )
        # H-API-12: refresh_token 通过 httpOnly Cookie 返回
        refresh_token = client.cookies.get("refresh_token")

        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "access_token" in body["data"]

    def test_refresh_with_invalid_token(self, client: TestClient, clean_db):
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        # Pydantic validates min_length=32 first, so 422 is expected for short token
        assert resp.status_code in (401, 422)

    def test_refresh_with_access_token_instead(self, client: TestClient, clean_db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "wrongtype",
                "email": "wrongtype@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "wrongtype", "password": "StrongPass123"},
        )
        access_token = login_resp.json()["data"]["access_token"]

        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert resp.status_code == 401


class TestRegisterEdgeCases:
    def test_register_username_boundary_3_chars(self, client: TestClient, clean_db):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "abc",
                "email": "abc@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "id" in body["data"]

    def test_register_username_boundary_50_chars(self, client: TestClient, clean_db):
        username_50 = "a" * 50
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": username_50,
                "email": "fifty@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "id" in body["data"]

    def test_register_username_too_short_rejected(self, client: TestClient, clean_db):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "ab",
                "email": "short2@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        assert resp.status_code == 422

    def test_register_username_too_long_rejected(self, client: TestClient, clean_db):
        username_51 = "a" * 51
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": username_51,
                "email": "long51@test.com",
                "password": "StrongPass123",
                "role": "user",
            },
        )
        assert resp.status_code == 422


class TestLoginRateLimit:
    def test_login_rate_limit_after_5_attempts(self, client: TestClient, clean_db):
        from app.core.rate_limit import limiter

        original_enabled = limiter.enabled
        limiter.enabled = True
        try:
            for i in range(5):
                resp = client.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "nonexistent_user_ratelimit",
                        "password": "WrongPass123",
                    },
                )
                assert resp.status_code == 401

            resp = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "nonexistent_user_ratelimit",
                    "password": "WrongPass123",
                },
            )
            assert resp.status_code == 429
        finally:
            limiter.enabled = original_enabled


class TestTokenExpiration:
    def test_expired_access_token_rejected(self, client: TestClient, clean_db):
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.core.config import settings
        from app.core.deps import get_current_user
        from app.main import app

        expired_token = jwt.encode(
            {
                "sub": "1",
                "type": "access",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
                "jti": "expired-jti-001",
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        app.dependency_overrides.pop(get_current_user, None)
        try:
            resp = client.get(
                "/api/v1/user/warnings",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            assert resp.status_code == 401
        finally:

            async def _override_get_current_user():
                from app.models.user import User

                return User(
                    id=1,
                    username="user_tester",
                    email="user@test.com",
                    role="user",
                    status="active",
                    password_hash="x",
                )

            app.dependency_overrides[get_current_user] = _override_get_current_user
