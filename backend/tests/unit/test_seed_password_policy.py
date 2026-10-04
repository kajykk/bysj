"""AUDIT-2026-10-01 (P1-32): 生产环境种子口令强度策略的回归测试。

背景：``app/core/seed.py`` 的注释声称
「L-17 修复：原默认密码偏弱（E2E@User123 仅 11 位），加强为至少 18 位且包含大小写/数字/特殊字符」，
但实现里 ``_validate_seed_passwords_for_production()`` 只校验了「非空」（``if not val``）——
也就是说这条安全控制当时并不存在，生产环境用 ``E2E_ADMIN_PASSWORD=abc`` 也能建账号。

本测试把该策略钉住，防止再次出现「注释声称有、代码里没有」的漂移。
"""

from __future__ import annotations

import pytest

from app.core import seed as seed_module
from app.core.config import settings

#: 满足全部要求的强口令：22 位、含大小写/数字/特殊字符
_STRONG = "Xk7#mQ2vLp9ZtR4nWb6Yd1"

#: 仓库与文档中公开出现过的示例口令（等同已泄漏）
_PUBLIC_EXAMPLES = ("E2E@Admin123", "E2E@Counselor123", "E2E@User123")


@pytest.fixture
def set_passwords(monkeypatch):
    """替换 seed 模块级的三个口令变量。"""

    def _set(admin: str | None, counselor: str | None, user: str | None) -> None:
        monkeypatch.setattr(seed_module, "_E2E_ADMIN_PASSWORD", admin, raising=False)
        monkeypatch.setattr(seed_module, "_E2E_COUNSELOR_PASSWORD", counselor, raising=False)
        monkeypatch.setattr(seed_module, "_E2E_USER_PASSWORD", user, raising=False)

    return _set


@pytest.fixture
def set_app_env(monkeypatch):
    """切换 app_env（校验函数内部读的是 settings 单例）。"""

    def _set(value: str) -> None:
        monkeypatch.setattr(settings, "app_env", value, raising=False)

    return _set


def _validate() -> None:
    seed_module._validate_seed_passwords_for_production()


# ── 生产环境：必须拒绝 ──────────────────────────────────────────────


@pytest.mark.parametrize("example", _PUBLIC_EXAMPLES)
def test_production_rejects_publicly_known_example_passwords(set_passwords, set_app_env, example):
    """公开示例口令即便「够长」也必须被拒绝（它们等同于已泄漏）。"""
    set_app_env("production")
    set_passwords(example + "-padding", example + "-padding", example + "-padding")
    with pytest.raises(RuntimeError, match="公开示例口令"):
        _validate()


def test_production_rejects_exact_example_values(set_passwords, set_app_env):
    set_app_env("production")
    set_passwords("E2E@Admin123", "E2E@Counselor123", "E2E@User123")
    with pytest.raises(RuntimeError):
        _validate()


@pytest.mark.parametrize("weak", ["abc", "short", "E2E@Admin12345678"])  # 后者含公开示例前缀
def test_production_rejects_too_short_password(set_passwords, set_app_env, weak):
    set_app_env("production")
    set_passwords(weak, weak, weak)
    with pytest.raises(RuntimeError):
        _validate()


def test_production_rejects_single_character_class(set_passwords, set_app_env):
    """24 位但只有一类字符（全小写）→ 熵不足，必须拒绝。"""
    set_app_env("production")
    set_passwords("a" * 24, "a" * 24, "a" * 24)
    with pytest.raises(RuntimeError, match="熵不足"):
        _validate()


def test_production_accepts_strong_passwords(set_passwords, set_app_env):
    set_app_env("production")
    set_passwords(_STRONG, _STRONG, _STRONG)
    _validate()  # 不应抛异常


def test_production_missing_passwords_still_raises(set_passwords, set_app_env):
    """保持 H-Core-7 的原有语义：缺失时必须报错。"""
    set_app_env("production")
    set_passwords(None, None, None)
    with pytest.raises(RuntimeError, match="缺失"):
        _validate()


# ── 非生产环境：不得因为强度而拦（否则会打断本地开发与 CI）──────────


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_production_does_not_enforce_strength(set_passwords, set_app_env, env):
    """dev/test 下示例口令/弱口令应放行——CI 的 E2E 以 APP_ENV=test 运行。"""
    set_app_env(env)
    set_passwords("E2E@Admin123", "E2E@Counselor123", "E2E@User123")
    _validate()

    set_passwords("abc", "abc", "abc")
    _validate()


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_production_missing_passwords_still_raises(set_passwords, set_app_env, env):
    set_app_env(env)
    set_passwords(None, None, None)
    with pytest.raises(RuntimeError, match="缺失"):
        _validate()
