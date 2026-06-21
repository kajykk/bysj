from __future__ import annotations

import pytest
from app.core.security import create_access_token


def test_login_refresh_and_logout_flow(client, seeded_user_id: int) -> None:
    register_resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": "p0_user",
            "email": "p0_user@test.com",
            "password": "StrongPass123",
            "role": "user",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "p0_user", "password": "StrongPass123"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()["data"]
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()["data"]
    assert refresh_data["access_token"]
    assert refresh_data["refresh_token"]

    from app.core.deps import get_current_user
    from app.main import app
    from app.models.user import User

    registered_user_id = register_data.get("user", {}).get("id") or login_data.get("user", {}).get("id")

    async def _override_for_logout():
        return User(
            id=registered_user_id,
            username="p0_user",
            email="p0_user@test.com",
            role="user",
            status="active",
            password_hash="x",
        )

    app.dependency_overrides[get_current_user] = _override_for_logout
    try:
        logout_resp = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == 200
        logout_data = logout_resp.json()["data"]
        assert logout_data["revoked_count"] >= 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_profile_update_and_change_password(client, seeded_user_id: int) -> None:
    access_token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
    headers = {"Authorization": f"Bearer {access_token}"}

    profile_resp = client.put(
        "/api/v1/auth/profile",
        json={"nickname": "新昵称", "email": "new_email@test.com"},
        headers=headers,
    )
    assert profile_resp.status_code == 200
    profile_data = profile_resp.json()["data"]
    assert profile_data["nickname"] == "新昵称"
    assert profile_data["email"] == "new_email@test.com"

    change_resp = client.put(
        "/api/v1/auth/change-password",
        json={"old_password": "wrong-old", "new_password": "NewStrongPass123"},
        headers=headers,
    )
    assert change_resp.status_code == 400
    body = change_resp.json()
    detail = (
        body.get("detail")
        or body.get("error", {}).get("message")
        or body.get("error", {}).get("details")
        or ""
    )
    assert "当前密码错误" in str(detail)
