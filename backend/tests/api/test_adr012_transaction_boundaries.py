"""ADR-012 (R-D) 契约测试: 事务边界统一.

覆盖:
1. 静态护栏: silences.py 变更端点 ≤1 commit（防回归多提交点）
2. 静态护栏(仓库级): API 与业务 Service 层无任何单路径多 commit
3. 运行时: update/enable 端点提交失败 → 业务变更与审计日志均不落库（无部分提交）
"""

from __future__ import annotations

import ast
import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AlertSilence, OperationLog

_SILENCES_PATH = pathlib.Path("app/api/v1/silences.py")


class TestCommitPointDiscipline:
    """静态护栏: 单端点 ≤1 commit."""

    def test_silences_file_commit_count_bounded(self) -> None:
        """ADR-012 规则 3: silences.py 全文件 commit 数 ≤ 变更端点数 (4)."""
        src = _SILENCES_PATH.read_text(encoding="utf-8")
        commits = re.findall(r"await db\.commit\(\)", src)
        # 4 个变更端点: create / update / enable / delete
        assert len(commits) <= 4, f"发现 {len(commits)} 个 commit 点 (规则: ≤4)"

    def test_no_commit_inside_read_only_endpoints(self) -> None:
        """ADR-012 规则 1: 列表/只读端点不得出现 commit."""
        src = _SILENCES_PATH.read_text(encoding="utf-8")
        for name in ("async def list_silences", "async def list_active_silences"):
            idx = src.index(name)
            tail = src[idx:]
            next_def = re.search(r"\n(@router\.|async def )", tail)
            block = tail[: next_def.start()] if next_def else tail
            assert "await db.commit()" not in block, f"{name} 不应包含 commit"


# 允许作为 commit 之间"分支隔离点"的控制流节点：两条 commit 分属互斥分支时可共存
_BRANCH_NODES = (ast.If, ast.Try, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Match)


def _commit_positions(body_nodes) -> list[str]:
    """返回函数体中按执行顺序的 (commit 位置) 标记列表.

    用 AST 遍历给每个 commit 标注其最近包围的分支节点 id；相邻 commit 若包裹
    节点不同则视为互斥分支（Allowed），相同则视为同一路径连续 commit（违规）。
    """
    marks: list[tuple[str, object]] = []

    def walk(node, branch_id) -> None:
        if isinstance(node, _BRANCH_NODES):
            branch_id = id(node)
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "commit"
        ):
            marks.append((f"b{id(node)}", branch_id))
            return
        for child in ast.iter_child_nodes(node):
            walk(child, branch_id)

    walk(body_nodes, None)
    return marks


class TestRepoWideNoSequentialCommits:
    """仓库级静态护栏: 任何 async 函数同一执行路径最多 1 个 commit.

    相邻两个 commit 若分属不同包围分支节点（if/else、try/except 互斥、
    match case 等），视为互斥分支允许共存；否则为同一路径连续 commit（违规）。
    """

    _TARGETS = ["app/api/v1", "app/services"]

    def test_no_same_path_sequential_commits(self) -> None:
        violations = []
        for base in self._TARGETS:
            for py in sorted(pathlib.Path(base).rglob("*.py")):
                try:
                    tree = ast.parse(py.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for node in ast.walk(tree):
                    if not (isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))):
                        continue
                    marks = _commit_positions(node)
                    # 连续两个 commit 共享同一 branch_id → 同路径连续 commit
                    for i in range(len(marks) - 1):
                        if marks[i][0] != marks[i + 1][0] and marks[i][1] == marks[i + 1][1]:
                            violations.append(
                                f"{py.as_posix()}:{node.lineno} {node.name} "
                                f"({marks[i][0]}@b{marks[i][1]} vs {marks[i+1][0]}@b{marks[i+1][1]})"
                            )
                            break
        assert not violations, "发现同一执行路径内连续 commit 的违规:\n" + "\n".join(violations)


def _patch_request_commit_to_fail(monkeypatch) -> None:
    """劫持请求内 session 的 commit 使其失败.

    测试夹具将 session.commit 替换为 session.flush（实例属性遮蔽类方法），
    且每次请求新建 session，类级 patch commit 无效。通过 patch AsyncSession.flush
    实现：_make_test_session 中 `session.commit = session.flush` 捕获的是
    AsyncSession.flush 的绑定方法，patch flush 后任何 flush/commit 均抛异常。
    """
    async def _always_fail_flush(self, *args, **kwargs):
        raise RuntimeError("simulated commit/flush failure")

    monkeypatch.setattr(AsyncSession, "flush", _always_fail_flush)


class TestNoPartialCommit:
    """运行时: 提交失败 → 业务变更与审计日志均不落库（无部分提交）.

    验证通过 db_connection 原始连接读库（绕过 session identity map 与 autoflush），
    确保读到的是数据库真实状态而非内存对象。
    """

    @pytest.fixture
    def seed_active(self, db_session: AsyncSession) -> int:
        from tests.conftest import run

        async def _seed() -> int:
            silence = AlertSilence(
                name="adr-original",
                matcher={"alertname": "HighCpu"},
                starts_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                ends_at=datetime.now(timezone.utc) + timedelta(hours=2),
                created_by=3,
                is_active=True,
                comment="seed",
            )
            db_session.add(silence)
            await db_session.commit()
            await db_session.refresh(silence)
            return silence.id

        return run(_seed())

    @pytest.fixture
    def seed_inactive(self, db_session: AsyncSession) -> int:
        from tests.conftest import run

        async def _seed() -> int:
            silence = AlertSilence(
                name="adr-inactive",
                matcher={"alertname": "HighCpu"},
                starts_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                ends_at=datetime.now(timezone.utc) + timedelta(hours=2),
                created_by=3,
                is_active=False,
                comment="seed",
            )
            db_session.add(silence)
            await db_session.commit()
            await db_session.refresh(silence)
            return silence.id

        return run(_seed())

    @staticmethod
    def _db_name(db_connection, silence_id: int) -> str:
        """通过原始连接读库（不经 session identity map / autoflush）."""
        from tests.conftest import run

        async def _read() -> str:
            result = await db_connection.execute(
                select(AlertSilence.name).where(AlertSilence.id == silence_id)
            )
            return result.scalar_one()

        return run(_read())

    @staticmethod
    def _db_is_active(db_connection, silence_id: int) -> bool:
        from tests.conftest import run

        async def _read() -> bool:
            result = await db_connection.execute(
                select(AlertSilence.is_active).where(
                    AlertSilence.id == silence_id
                )
            )
            return bool(result.scalar_one())

        return run(_read())

    @staticmethod
    def _db_audit_count(db_connection, action_type: str, target_id: int) -> int:
        from tests.conftest import run

        async def _count() -> int:
            result = await db_connection.execute(
                select(func.count()).where(
                    OperationLog.action_type == action_type,
                    OperationLog.target_id == target_id,
                )
            )
            return result.scalar_one()

        return run(_count())

    def test_update_commit_failure_no_partial_commit(
        self,
        client: TestClient,
        as_role,
        db_connection,
        monkeypatch,
        seed_active: int,
    ) -> None:
        """PUT 编辑: 提交失败 → name 不变更 + 无 update_silence 审计日志."""
        as_role("admin", 3)
        _patch_request_commit_to_fail(monkeypatch)
        now = datetime.now(timezone.utc)

        # TestClient raise_server_exceptions=True: 未处理异常以异常形式浮出（等价 500 信号）
        with pytest.raises(Exception) as excinfo:
            client.put(
                f"/api/v1/alerts/silences/{seed_active}",
                json={
                    "name": "adr-renamed",
                    "matcher": {"alertname": "HighCpu"},
                    "starts_at": (now - timedelta(minutes=5)).isoformat(),
                    "ends_at": (now + timedelta(hours=2)).isoformat(),
                    "comment": "rename attempt",
                },
            )
        assert "simulated commit/flush failure" in str(excinfo.value)

        assert self._db_name(db_connection, seed_active) == "adr-original"
        assert self._db_audit_count(db_connection, "update_silence", seed_active) == 0

    def test_enable_commit_failure_no_partial_commit(
        self,
        client: TestClient,
        as_role,
        db_connection,
        monkeypatch,
        seed_inactive: int,
    ) -> None:
        """enable: 提交失败 → is_active 保持 False + 无 enable_silence 审计日志."""
        as_role("admin", 3)
        _patch_request_commit_to_fail(monkeypatch)

        with pytest.raises(Exception) as excinfo:
            client.post(f"/api/v1/alerts/silences/{seed_inactive}/enable")
        assert "simulated commit/flush failure" in str(excinfo.value)

        assert self._db_is_active(db_connection, seed_inactive) is False
        assert self._db_audit_count(db_connection, "enable_silence", seed_inactive) == 0
