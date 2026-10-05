"""闸门: workflow 的 CI 占位密钥必须满足 config.py 的生产环境强度校验。

背景 (2026-10-05 实测): `v1.39-alerting-e2e` 因 env里的占位
JWT_SECRET_KEY 只有 26 字符, 低于 config.py `_MIN_JWT_SECRET_LENGTH`(32),
在 Settings() 处抛 ValidationError -> alembic_migrate 退出 1 ->
Start stack 步骤红灯, 且失败日志未抓该容器日志, 根因不可见。

这是同类问题的**第二次复发** (上一次 dd775d6: 缺 PII_ENCRYPTION_KEY)。
两类根因同构 —— workflow 里手写的占位值与 Settings 校验规则各自独立演进。
本测试直接复用真实校验函数, 不复制规则, 避免"测试与实现漂移"。

跑法(backend 目录下):
    .venv/Scripts/python.exe -m pytest tests/test_ci_secret_placeholders.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import (
    _INSECURE_KEYS,
    _MIN_JWT_SECRET_LENGTH,
    _validate_jwt_secret_strength,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# 只审计 CI 占位密钥, 不含 JWT_ALGORITHM 等非密钥字段
SECRET_VAR_RE = re.compile(
    r"^\s*(JWT_SECRET_KEY|PASSWORD_RESET_BASE_URL|ALERTMANAGER_WEBHOOK_SECRET"
    r"|METRICS_ACCESS_TOKEN|GRAFANA_SA_TOKEN)\s*:\s*(.+?)\s*$"
)


def _collect_workflow_secrets() -> list[tuple[str, str, str]]:
    """返回 [(文件名, 变量名, 字面值)]，跳过 ${VAR:-} 这类 shell 插值。"""
    found: list[tuple[str, str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = SECRET_VAR_RE.match(line)
            if not m:
                continue
            name, raw = m.group(1), m.group(2)
            if "${" in raw:  # 交给 compose 插值, 不在 workflow 里给字面值
                continue
            found.append((path.name, name, raw.strip().strip("'\"")))
    return found


class TestCIPlaceholderSecretStrength:
    """CI 占位密钥必须能通过生产模式的强度校验。"""

    def test_workflows_declare_at_least_one_placeholder_secret(self):
        """防呆: 若将来正则与实际格式脱节, 本测试必须显式失败而非静默通过 0 条。"""
        secrets = _collect_workflow_secrets()
        assert secrets, (
            "未从 .github/workflows/*.yml 采集到任何占位密钥 —— "
            "SECRET_VAR_RE 可能已与 workflow 实际格式脱节, 闸门失效"
        )

    def test_jwt_secret_placeholder_passes_production_strength_check(self):
        """核心闸门: 复用真实校验函数, 不复述规则。

        旧代码 (ci-jwt-secret-for-e2e-only, 26 字符) 在此抛 ValueError。
        """
        jwt_entries = [
            (fname, value)
            for fname, name, value in _collect_workflow_secrets()
            if name == "JWT_SECRET_KEY"
        ]
        if not jwt_entries:
            pytest.skip("workflow 中当前无 JWT_SECRET_KEY 字面值")

        for fname, value in jwt_entries:
            assert value not in _INSECURE_KEYS, (
                f"{fname}: JWT_SECRET_KEY 命中弱值黑名单: {value!r}"
            )
            assert len(value) >= _MIN_JWT_SECRET_LENGTH, (
                f"{fname}: JWT_SECRET_KEY 仅 {len(value)} 字符, "
                f"低于生产模式下限 {_MIN_JWT_SECRET_LENGTH} —— "
                f"会导致 alembic_migrate 在 Settings() 处退出 1"
            )
            # 不捕获异常: 真实校验通过才算过
            _validate_jwt_secret_strength(value)


class TestAlertingWorkflowJWTKey:
    """针对本次根因的定点回归锁。"""

    WORKFLOW = WORKFLOWS / "v1.39-alerting-e2e.yml"

    def test_workflow_exists(self):
        assert self.WORKFLOW.exists(), f"缺失 {self.WORKFLOW}"

    def test_known_bad_placeholder_is_gone(self):
        """旧占位值若再出现, 说明有人 revert 了修复或改了配置同步机制。

        只扫env 定义区的实际取值, 不扫注释 —— 本文件的说明性注释里
        也会提到旧值, 全文匹配会把自己判成失败。
        """
        bad = "ci-jwt-secret-for-e2e" + "-for-e2e-only"  # 拆写避免注释自命中
        for line in self.WORKFLOW.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert bad not in stripped, (
                "弱密钥占位值回归 —— 它必然触发 config.py 的生产强度校验失败"
            )

    def test_current_placeholder_is_strong_enough(self):
        m = re.search(
            r"^\s*JWT_SECRET_KEY\s*:\s*(.+?)\s*$",
            self.WORKFLOW.read_text(encoding="utf-8", errors="replace"),
            re.M,
        )
        assert m, "v1.39-alerting-e2e.yml 中未找到 JWT_SECRET_KEY 定义"
        value = m.group(1).strip().strip("'\"")
        assert len(value) >= _MIN_JWT_SECRET_LENGTH, (
            f"当前占位值 {len(value)} 字符 < {_MIN_JWT_SECRET_LENGTH}"
        )
        _validate_jwt_secret_strength(value)


class TestFailureArtifactsCaptureMigrateLogs:
    """取证完整性: 失败时必须抓到唯一报错方 alembic_migrate 的日志。

    本次根因之所以要靠本地复现才定位, 直接原因就是失败日志只抓 backend/grafana,
    漏掉了 alembic_migrate, artifact 仅 254 字节(≈空)。
    """

    WORKFLOW = WORKFLOWS / "v1.39-alerting-e2e.yml"

    def _content(self) -> str:
        return self.WORKFLOW.read_text(encoding="utf-8", errors="replace")

    def test_artifact_includes_migrate_log(self):
        assert "alembic-migrate.log" in self._content(), (
            "artifact 未包含 alembic_migrate 日志 —— 唯一报错方再次不可见"
        )

    def test_missing_files_is_error_not_ignored(self):
        """文件缺失必须让artifact 步骤显式失败, 不得静默忽略。

        只检查 upload 步骤块内的设置行 —— 说明性注释里会讨论被禁掉的写法,
        全文匹配会把自己判成失败。
        """
        text = self.WORKFLOW.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # 定位 upload-artifact 步骤, 只在其块内判定
        start = next(
            (i for i, l in enumerate(lines) if "upload-artifact" in l),
            None,
        )
        assert start is not None, "未找到 upload-artifact 步骤"
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].strip().startswith("- name:"):
                end = i
                break
        block = "\n".join(lines[start:end])

        ignore_marker = "if-no-files-found:" + "ignore"
        assert ignore_marker not in block, (
            "if-no-files-found 不得为 ignore —— 空日志正是根因不可见的直接原因"
        )
        assert "if-no-files-found:" in block and "error" in block, (
            "upload-artifact 步骤必须显式声明 if-no-files-found: error"
        )