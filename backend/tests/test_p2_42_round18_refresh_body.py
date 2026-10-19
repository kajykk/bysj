"""ROUND_18 · T1（审查报告 M1）：``/auth/refresh`` 响应体不得回传 refresh_token。

缺陷原文（`outputs/CODE_REVIEW_2026-10-20.md` §2.1 M1）：端点 ``return ok(tokens)``，
而 login 已按 H-API-12 只回 access_token。refresh_token 在 Cookie 里是 httpOnly，
同一个响应 JSON 里又给了明文 —— 任何 XSS 只需
``fetch('/api/v1/auth/refresh',{credentials:'include'})`` 就能拿到长效令牌并外带。

判据两条，一条行为、一条契约：
1. 真实走 register → login → refresh，**响应体的键集合**必须恰为
   ``{access_token, token_type}``（结构断言：不多不少，不靠"某字段不在 JSON 文本里"）；
2. OpenAPI 里 ``TokenResponse`` 不再声明该字段 —— 防止有人把字段加回模型，
   让 FastAPI 以 ``null`` 的形式把键名重新暴露出去。

反向对照：同一条用例里断言 Cookie 仍然轮换（``Set-Cookie`` 路径未被削弱），
证明剥离 body 没有连带把换发功能改坏。
"""

from __future__ import annotations


def _register_and_login(client, username: str) -> str | None:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "StrongPass123",
            "role": "user",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "StrongPass123"},
    )
    assert resp.status_code == 200
    return client.cookies.get("refresh_token")


def test_refresh_response_exposes_only_access_token(client, db_session):
    original = _register_and_login(client, "r18_refresh_body")
    assert original

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": original})

    assert resp.status_code == 200
    data = resp.json()["data"]
    # 键集合完全相等：多一个 refresh_token 就是回退到 M1 的缺陷形态
    assert set(data) == {"access_token", "token_type"}
    assert data["access_token"]

    # 反向对照：换发仍然发生（Cookie 被轮换成新值）
    rotated = client.cookies.get("refresh_token")
    assert rotated and rotated != original


def test_refresh_response_schema_does_not_declare_refresh_token():
    """契约层闸门：模型里不得再出现该字段。

    行为断言只能证明"当前实现不回传"；若有人把字段加回 ``TokenResponse``，
    FastAPI 会补一个 ``"refresh_token": null``，键名重新进入响应体与前端类型定义。
    """
    from app.main import app

    schema = app.openapi()
    op = schema["paths"]["/api/v1/auth/refresh"]["post"]
    ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    wrapper_name = ref.rsplit("/", 1)[-1]
    assert wrapper_name == "ApiResponse_TokenResponse_"

    inner_ref = schema["components"]["schemas"][wrapper_name]["properties"]["data"]
    branches = inner_ref.get("anyOf", [inner_ref])
    names = [b.get("$ref", "").rsplit("/", 1)[-1] for b in branches]
    assert "TokenResponse" in names
    props = schema["components"]["schemas"]["TokenResponse"]["properties"]
    assert "access_token" in props
    assert "refresh_token" not in props
