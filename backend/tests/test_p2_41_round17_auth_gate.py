"""ROUND_17 T2：止血开关覆盖度自检闸门。

目标：把「哪些鉴权入口做了租户封禁校验」从口头清单变成**结构性不变式**。

判据（全部 AST，不查字符串）：
1. **发现**：扫描 ``backend/app`` 全部模块，找出所有直接调用
   ``decode_token`` / ``create_access_token`` / ``create_refresh_token`` /
   ``create_password_reset_token`` 的函数 —— 这些函数要么在发放凭证，要么在
   兑换凭证，都是鉴权入口。
2. **登记**：发现集必须与 ``REGISTRY`` 的键**完全相等**。新增一个入口
   （例如再写一个 refresh 变体）而不登记 ⇒ 本文件红，强制回答
   "这个入口要不要封禁"。
3. **校验**：``enforced`` 条目必须在自己函数体内调用 ``is_tenant_suspended``，
   且调用行号必须早于任何凭证签发/密码写入。
4. **豁免必须有理由**：``exempt`` 条目必须写明原因，且不得出现封禁调用
   （避免"登记成豁免、实际偷偷校验"的口径漂移）。

变异见证：
- 移除任一 enforced 条目的 ``is_tenant_suspended`` 调用 ⇒
  ``test_enforced_entries_have_ban_check`` 红；
- 新增一个未登记的 token 操作函数 ⇒
  ``test_every_token_operation_function_is_registered`` 红。

行为侧另配两条用例（reset 流程两道门），见文件下半部分。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_ROOT = REPO / "backend" / "app"

TOKEN_OPS = {
    "decode_token",
    "create_access_token",
    "create_refresh_token",
    "create_password_reset_token",
}
ISSUANCE_OPS = {
    "create_access_token",
    "create_refresh_token",
    "create_password_reset_token",
}
BAN_CHECK = "is_tenant_suspended"


@dataclass(frozen=True)
class Entry:
    bucket: Literal["enforced", "exempt"]
    kind: str
    reason: str = ""


# 入口清单（新增 token 操作函数必须在此登记，否则本闸门红）
REGISTRY: dict[tuple[str, str], Entry] = {
    # ── 强制校验 ───────────────────────────────────────────────────
    ("app/core/deps.py", "get_current_user"): Entry(
        "enforced", "http_dependency", "所有已认证 HTTP 请求的唯一用户解析入口"
    ),
    ("app/core/ws.py", "websocket_endpoint"): Entry(
        "enforced", "ws_handshake", "WebSocket 长连接握手"
    ),
    ("app/services/auth_service.py", "AuthService.login"): Entry(
        "enforced", "session_issue", "签发 access/refresh"
    ),
    ("app/services/auth_service.py", "AuthService.refresh"): Entry(
        "enforced", "session_renew", "refresh 换发新会话"
    ),
    ("app/services/auth_service.py", "AuthService.request_password_reset"): Entry(
        "enforced", "credential_recovery_issue", "签发密码重置令牌（邮件）"
    ),
    ("app/services/auth_service.py", "AuthService.reset_password"): Entry(
        "enforced", "credential_reset", "兑换重置令牌并改密"
    ),
    # ── 显式豁免（必须写理由）─────────────────────────────────────
    ("app/core/deps.py", "_role_for_request"): Entry(
        "exempt",
        "role_helper",
        "只在 get_current_user 成功后由 _check_role_and_tenant 调用，"
        "仅提取角色声明，不单独放行请求",
    ),
    ("app/services/auth_service.py", "AuthService.logout"): Entry(
        "exempt",
        "session_revoke",
        "只撤销会话；封禁期间仍应允许用户主动退出，拒绝 logout 会把用户困在已登录态",
    ),
}

# 豁免但不在 token 操作发现集里的入口（人工登记，防"新增登录类入口不触发发现"）
MANUAL_ONLY_EXEMPT = {
    ("app/core/deps.py", "_resolve_current_user"): "委托 get_current_user（或测试覆盖）",
    ("app/api/v1/uploads.py", "_optional_resolve_user"): "委托 get_current_user",
    ("app/core/deps.py", "require_sa_or_admin"): "Grafana 平台 SA 凭据或委托 get_current_user",
    ("app/services/auth_service.py", "AuthService.change_password"): (
        "路由挂 Depends(get_current_user)，封禁已在 HTTP 入口拒绝"
    ),
}


def _iter_functions(body: list[ast.stmt], prefix: str = ""):
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield prefix + node.name, node
        elif isinstance(node, ast.ClassDef):
            yield from _iter_functions(node.body, prefix + node.name + ".")


def _own_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, int]]:
    """函数自身语句里的调用（不进入嵌套函数/类，避免把内层 helper 记到外层）。"""
    out: list[tuple[str, int]] = []
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            continue
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name:
                out.append((name, node.lineno))
        stack.extend(ast.iter_child_nodes(node))
    return out


def _password_write_lines(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "password_hash":
                    lines.append(node.lineno)
    return lines


def _ordering_problem(
    label: str, fn: ast.FunctionDef | ast.AsyncFunctionDef
) -> str | None:
    """封禁校验必须早于凭证签发/密码写入；返回问题描述或 None。"""
    calls = _own_calls(fn)
    ban_lines = [line for name, line in calls if name == BAN_CHECK]
    issuance_lines = [line for name, line in calls if name in ISSUANCE_OPS]
    issuance_lines += _password_write_lines(fn)
    if not issuance_lines:
        return None
    if not ban_lines:
        return f"{label} 缺少 {BAN_CHECK} 调用"
    if min(ban_lines) > min(issuance_lines):
        return (
            f"{label} 的封禁校验在第 {min(ban_lines)} 行，"
            f"晚于签发/改密第 {min(issuance_lines)} 行"
        )
    return None


def _discover() -> dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef]:
    found: dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO / "backend").as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for qualname, fn in _iter_functions(tree.body):
            ops = {name for name, _ in _own_calls(fn)} & TOKEN_OPS
            if ops:
                found[(rel, qualname)] = fn
    return found


class TestAuthEntryCoverage:
    def test_every_token_operation_function_is_registered(self):
        discovered = set(_discover())
        registered = set(REGISTRY)

        unregistered = sorted(discovered - registered)
        stale = sorted(registered - discovered)

        assert not unregistered, (
            "发现未登记的鉴权入口（新增入口必须显式登记并回答'要不要封禁'）：\n"
            + "\n".join(f"  {rel}::{name}" for rel, name in unregistered)
        )
        assert not stale, (
            "REGISTRY 里的入口在代码中已不存在（改名/删除后必须同步清单）：\n"
            + "\n".join(f"  {rel}::{name}" for rel, name in stale)
        )

    def test_enforced_entries_have_ban_check(self):
        discovered = _discover()
        problems: list[str] = []

        for key, entry in REGISTRY.items():
            if entry.bucket != "enforced":
                continue
            fn = discovered.get(key)
            if fn is None:
                problems.append(f"{key[0]}::{key[1]} 未找到函数")
                continue

            calls = _own_calls(fn)
            ban_lines = [line for name, line in calls if name == BAN_CHECK]
            if not ban_lines:
                problems.append(
                    f"{key[0]}::{key[1]}（{entry.kind}）缺少 {BAN_CHECK} 调用"
                )
                continue

            # 校验必须在凭证签发/密码写入之前发生（"先核验，再兑现"）
            problem = _ordering_problem(f"{key[0]}::{key[1]}", fn)
            if problem:
                problems.append(problem)

        assert not problems, "enforced 入口校验缺失或次序错误：\n" + "\n".join(
            f"  {p}" for p in problems
        )

    def test_exempt_entries_are_explicit_and_unchecked(self):
        discovered = _discover()
        problems: list[str] = []

        for key, entry in REGISTRY.items():
            if entry.bucket != "exempt":
                continue
            if not entry.reason.strip():
                problems.append(f"{key[0]}::{key[1]} 豁免未写理由")
            fn = discovered.get(key)
            if fn is None:
                continue
            ban_calls = [n for n, _ in _own_calls(fn) if n == BAN_CHECK]
            if ban_calls:
                problems.append(
                    f"{key[0]}::{key[1]} 登记为 exempt 却出现 {BAN_CHECK} 调用，"
                    "口径漂移（要么改登记，要么删调用）"
                )

        assert not problems, "豁免口径不自洽：\n" + "\n".join(f"  {p}" for p in problems)

    def test_manual_exempt_entries_have_reason_and_exist(self):
        all_code = {
            (path.relative_to(REPO / "backend").as_posix(), qualname)
            for path in sorted(APP_ROOT.rglob("*.py"))
            if "__pycache__" not in path.parts
            for qualname, _ in _iter_functions(
                ast.parse(path.read_text(encoding="utf-8-sig")).body
            )
        }
        for key, reason in MANUAL_ONLY_EXEMPT.items():
            assert reason.strip(), f"{key} 未写豁免理由"
            assert key in all_code, f"人工登记的豁免入口不存在：{key}"


class TestGateSelfProof:
    """闸门自证：次序判据不能是恒真/恒假的空断言。

    生产代码当前都是"先校验、后签发"，只跑真实入口无法区分
    ``min(ban) > min(issuance)`` 这条判据是否真的在工作，故用合成样本两头夹。
    """

    def test_ordering_arm_accepts_check_before_issuance(self):
        src = '''
async def correct(order):
    if await is_tenant_suspended(db, 1):
        raise ValueError("suspended")
    return create_access_token({})
'''
        _, fn = next(iter(_iter_functions(ast.parse(src).body)))
        assert _ordering_problem("probe", fn) is None

    def test_ordering_arm_flags_check_after_issuance(self):
        src = '''
async def wrong(order):
    token = create_access_token({})
    if await is_tenant_suspended(db, 1):
        raise ValueError("suspended")
    return token
'''
        _, fn = next(iter(_iter_functions(ast.parse(src).body)))
        assert _ordering_problem("probe", fn) is not None


# ── 行为侧：reset 流程两道门 ────────────────────────────────────────


@pytest.fixture
async def suspended_tenant_user(db_session, monkeypatch):
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash
    from app.models.tenant import Tenant
    from app.models.user import User

    tenant_id, user_id = 987_670, 987_670
    email = "r17-reset@test.com"
    db_session.add(
        Tenant(id=tenant_id, name="R17 reset", code="r17-reset", status="suspended")
    )
    user = User(
        id=user_id,
        username="r17_reset",
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash=get_password_hash("OldPass123!"),
        role="user",
        status="active",
        tenant_id=tenant_id,
    )
    db_session.add(user)
    await db_session.commit()
    return db_session, user, email


async def test_request_password_reset_suppressed_for_suspended_tenant(
    suspended_tenant_user, monkeypatch
):
    from app.services.auth_service import AuthService

    db, user, email = suspended_tenant_user
    service = AuthService(db)
    sent: list[str] = []

    async def _record(email_arg: str, token: str) -> None:
        sent.append(email_arg)

    monkeypatch.setattr(service.email_service, "send_password_reset_email", _record)

    await service.request_password_reset(email)

    assert sent == [], "暂停租户仍收到重置邮件 —— 找回入口未受封禁约束"


async def test_reset_password_rejected_for_suspended_tenant(
    suspended_tenant_user, monkeypatch
):
    from app.core.security import create_password_reset_token
    from app.schemas.auth import ResetPasswordRequest
    from app.services.auth_service import AuthService

    db, user, email = suspended_tenant_user
    old_hash = user.password_hash

    # Redis 不可用：blocklist 与本缺陷无关，替换为"未撤销/核销成功"
    import app.core.token_blocklist as blocklist

    async def _not_revoked(jti: str) -> bool:
        return False

    async def _revoke_ok(jti: str, ttl: int) -> bool:
        return True

    monkeypatch.setattr(blocklist, "is_token_revoked", _not_revoked)
    monkeypatch.setattr(blocklist, "revoke_token", _revoke_ok)

    token = create_password_reset_token({"sub": str(user.id), "email": email})
    payload = ResetPasswordRequest(
        email=email, new_password="NewPass123!", reset_token=token
    )

    with pytest.raises(ValueError) as excinfo:
        await AuthService(db).reset_password(payload)

    assert "租户已暂停" in str(excinfo.value)
    assert user.password_hash == old_hash, "暂停租户的密码被重置令牌改掉了"
