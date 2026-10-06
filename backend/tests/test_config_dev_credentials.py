"""AUDIT-2026-10-06 (P1-3): 开发用默认凭据的回落必须是白名单制.

背景：原判定写作 `app_env == "production"` 取反，于是 staging / uat /
"prod" / "Production "（带空格）等一切非严格 production 的**对外部署**
都会静默启用硬编码凭据（metrics 令牌 / AlertManager webhook 密钥）——
任何知道公开常量的人都能拉全量指标或注入伪造告警。

修复：`Settings.dev_credentials_allowed` 改为白名单判定，非白名单环境
一律 fail-closed。本文件锁定该语义，防止改回宽松判定。
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.mark.parametrize("env", ["development", "dev", "local", "test", "testing", "pytest"])
def test_dev_like_envs_allow_fallback(env: str) -> None:
    """本地开发/测试环境允许回落开发用默认值（否则本地与 CI 无法开箱运行）。"""
    assert Settings(app_env=env).dev_credentials_allowed is True


@pytest.mark.parametrize(
    "env",
    [
        "prod",  # 常见简写（原判定下会误判为非 production）
        "staging",  # 预发：最容易被原判定放过
        "uat",
        "preprod",
    ],
)
def test_non_dev_envs_are_fail_closed(env: str) -> None:
    """非白名单环境一律 fail-closed —— 这正是原实现的漏洞所在。"""
    assert Settings(app_env=env).dev_credentials_allowed is False


@pytest.mark.parametrize(
    "env",
    [
        "production",
        "Production",  # 大小写差异
        " production ",  # 首尾空白
    ],
)
def test_production_never_allows_fallback(env: str) -> None:
    """production 一律不回落（含大小写/空白变体）。

    用 ``model_construct`` 绕开 model_validator：真实构造 production 时会因
    「生产 + sqlite」等启动校验直接抛 ValueError（那是另一条防线的职责），
    而本用例只验证「白名单判定」这一纯逻辑。
    """
    assert Settings.model_construct(app_env=env).dev_credentials_allowed is False
