"""STAB-P2-008: 数据库迁移向后兼容性测试.

测试范围:
1. Alembic 配置文件存在性 (alembic.ini / env.py / versions/)
2. 迁移文件结构完整性 (upgrade/downgrade 函数, revision/down_revision 字段)
3. 迁移链完整性 (无悬挂 down_revision, 无重复 revision, 链路可达)
4. CI workflow 配置 (migration-tests.yml 引用脚本)
5. 端到端 alembic upgrade/downgrade 循环 (子进程调用)
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
ALEMBIC_DIR = BACKEND_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"
ENV_PY = ALEMBIC_DIR / "env.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "migration-tests.yml"
COMPAT_SCRIPT = REPO_ROOT / "scripts" / "test_migration_compat.py"


class TestAlembicConfig:
    """Alembic 配置文件存在性测试."""

    def test_alembic_ini_exists(self):
        """alembic.ini 配置文件存在."""
        assert ALEMBIC_INI.exists(), f"alembic.ini not found at {ALEMBIC_INI}"

    def test_alembic_dir_exists(self):
        """alembic/ 目录存在."""
        assert ALEMBIC_DIR.exists(), f"alembic dir not found at {ALEMBIC_DIR}"
        assert ALEMBIC_DIR.is_dir()

    def test_env_py_exists(self):
        """alembic/env.py 存在."""
        assert ENV_PY.exists(), f"env.py not found at {ENV_PY}"

    def test_versions_dir_exists(self):
        """alembic/versions/ 目录存在."""
        assert VERSIONS_DIR.exists(), f"versions dir not found at {VERSIONS_DIR}"
        assert VERSIONS_DIR.is_dir()

    def test_alembic_ini_script_location_configured(self):
        """alembic.ini 配置 script_location = alembic."""
        content = ALEMBIC_INI.read_text(encoding="utf-8")
        assert "script_location" in content
        assert "alembic" in content


class TestMigrationFiles:
    """迁移文件结构完整性测试."""

    @classmethod
    def _get_migration_files(cls) -> list[Path]:
        """获取所有迁移文件 (.py)."""
        return sorted(VERSIONS_DIR.glob("*.py"))

    def test_at_least_one_migration(self):
        """至少 1 个迁移文件."""
        files = self._get_migration_files()
        assert len(files) >= 1, "no migration files found in versions/"

    def test_all_migrations_have_upgrade_function(self):
        """所有迁移文件有 upgrade() 函数."""
        for migration_file in self._get_migration_files():
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            function_names = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
            assert "upgrade" in function_names, (
                f"{migration_file.name} missing upgrade() function"
            )

    def test_all_migrations_have_downgrade_function(self):
        """所有迁移文件有 downgrade() 函数."""
        for migration_file in self._get_migration_files():
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            function_names = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
            assert "downgrade" in function_names, (
                f"{migration_file.name} missing downgrade() function"
            )

    def test_all_migrations_have_revision_id(self):
        """所有迁移文件有 revision 字符串字段."""
        for migration_file in self._get_migration_files():
            content = migration_file.read_text(encoding="utf-8")
            # 模块级赋值: revision: str = "xxx"
            assert "revision" in content, (
                f"{migration_file.name} missing revision field"
            )

    def test_all_migrations_have_down_revision(self):
        """所有迁移文件有 down_revision 字段."""
        for migration_file in self._get_migration_files():
            content = migration_file.read_text(encoding="utf-8")
            assert "down_revision" in content, (
                f"{migration_file.name} missing down_revision field"
            )

    def test_no_only_pass_in_non_initial_upgrade(self):
        """非初始迁移的 upgrade() 不能仅是 pass (必须有实际操作)."""
        files = self._get_migration_files()
        for migration_file in files:
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef)
                    and node.name == "upgrade"
                ):
                    # 检查函数体是否只有 pass 或 docstring + pass
                    body = node.body
                    # 过滤 docstring
                    real_body = [
                        n
                        for n in body
                        if not (
                            isinstance(n, ast.Expr)
                            and isinstance(n.value, ast.Constant)
                            and isinstance(n.value.value, str)
                        )
                    ]
                    if len(real_body) == 1 and isinstance(real_body[0], ast.Pass):
                        # pass-only upgrade, 检查是否为初始迁移或 merge 迁移
                        # 初始迁移 down_revision = None
                        # merge 迁移 down_revision = tuple
                        is_initial = "down_revision: Union[str, None] = None" in content
                        is_merge = "down_revision: Union[str, None] = (" in content
                        assert is_initial or is_merge, (
                            f"{migration_file.name} has pass-only upgrade() "
                            "but is neither initial nor merge migration"
                        )

    def test_no_only_pass_in_non_initial_downgrade(self):
        """非初始迁移的 downgrade() 不能仅是 pass."""
        files = self._get_migration_files()
        for migration_file in files:
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef)
                    and node.name == "downgrade"
                ):
                    body = node.body
                    real_body = [
                        n
                        for n in body
                        if not (
                            isinstance(n, ast.Expr)
                            and isinstance(n.value, ast.Constant)
                            and isinstance(n.value.value, str)
                        )
                    ]
                    if len(real_body) == 1 and isinstance(real_body[0], ast.Pass):
                        is_initial = "down_revision: Union[str, None] = None" in content
                        is_merge = "down_revision: Union[str, None] = (" in content
                        assert is_initial or is_merge, (
                            f"{migration_file.name} has pass-only downgrade() "
                            "but is neither initial nor merge migration"
                        )


class TestMigrationChain:
    """迁移链完整性测试."""

    @classmethod
    def _parse_revisions(cls) -> dict[str, set[str]]:
        """解析所有迁移文件的 revision / down_revision.

        Returns:
            {revision_id: set(down_revision_ids)} 字典.
            down_revision 为 None 时, set 为空.
            down_revision 为 tuple (merge) 时, set 含多个元素.
        """
        revisions: dict[str, set[str]] = {}
        for migration_file in sorted(VERSIONS_DIR.glob("*.py")):
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            rev_id = None
            down_rev = None
            for node in ast.walk(tree):
                # 处理 Assign (revision = "xxx") 和 AnnAssign (down_revision: Union[str, None] = None)
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "revision":
                                rev_id = _extract_str_literal(node.value)
                            elif target.id == "down_revision":
                                down_rev = node.value
                elif isinstance(node, ast.AnnAssign):
                    target = node.target
                    if isinstance(target, ast.Name):
                        if target.id == "revision":
                            rev_id = _extract_str_literal(node.value)
                        elif target.id == "down_revision":
                            down_rev = node.value
            if rev_id is None:
                continue
            if down_rev is None:
                revisions[rev_id] = set()
            elif isinstance(down_rev, ast.Constant):
                if down_rev.value is None:
                    revisions[rev_id] = set()
                else:
                    revisions[rev_id] = {str(down_rev.value)}
            elif isinstance(down_rev, ast.Tuple):
                deps = set()
                for elt in down_rev.elts:
                    if isinstance(elt, ast.Constant):
                        deps.add(str(elt.value))
                revisions[rev_id] = deps
        return revisions

    def test_initial_migration_has_null_down_revision(self):
        """至少 1 个初始迁移 (down_revision = None)."""
        revisions = self._parse_revisions()
        initial_count = sum(1 for deps in revisions.values() if not deps)
        assert initial_count >= 1, "no initial migration (down_revision=None) found"

    def test_no_dangling_down_revision(self):
        """所有 down_revision 指向存在的 revision (无悬挂引用)."""
        revisions = self._parse_revisions()
        all_revisions = set(revisions.keys())
        for rev_id, deps in revisions.items():
            for dep in deps:
                assert dep in all_revisions, (
                    f"migration {rev_id} references non-existent "
                    f"down_revision {dep}"
                )

    def test_no_duplicate_revision_ids(self):
        """revision id 唯一 (无重复)."""
        revisions = self._parse_revisions()
        # dict key 本身就唯一, 这里验证文件数 == revision 数
        files = list(VERSIONS_DIR.glob("*.py"))
        # 跳过 __init__.py (如果存在)
        files = [f for f in files if f.name != "__init__.py"]
        # 每个 .py 应该对应一个 revision (解析成功)
        # 允许某些文件解析失败 (如 __init__.py), 但不应有重复 revision
        # 这里检查: dict 中无重复 key (Python dict 保证)
        # 额外检查: 同一 revision id 不应出现在 2 个文件中
        rev_count: dict[str, int] = {}
        for migration_file in files:
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "revision"
                        ):
                            rev_id = _extract_str_literal(node.value)
                            if rev_id:
                                rev_count[rev_id] = rev_count.get(rev_id, 0) + 1
        duplicates = {k: v for k, v in rev_count.items() if v > 1}
        assert not duplicates, f"duplicate revision ids: {duplicates}"

    def test_chain_reachable_from_base_to_head(self):
        """从 base (initial) 到 head 的链路完整可达 (BFS)."""
        revisions = self._parse_revisions()
        # 找出所有初始迁移 (无 down_revision)
        initials = [rev for rev, deps in revisions.items() if not deps]
        # BFS: 从初始迁移出发, 沿 down_revision 反向 (即谁依赖我) 到达所有迁移
        # 构建 reverse graph: down_rev -> [rev_ids that depend on it]
        reverse: dict[str, list[str]] = {}
        for rev_id, deps in revisions.items():
            for dep in deps:
                reverse.setdefault(dep, []).append(rev_id)

        # BFS 从 initials 出发
        visited: set[str] = set()
        queue = list(initials)
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for child in reverse.get(current, []):
                if child not in visited:
                    queue.append(child)

        # 验证所有迁移都可达
        unreachable = set(revisions.keys()) - visited
        assert not unreachable, (
            f"migrations unreachable from initial: {unreachable}"
        )


class TestMigrationCompatScript:
    """迁移兼容性测试脚本 (scripts/test_migration_compat.py) 测试."""

    def test_script_exists(self):
        """scripts/test_migration_compat.py 文件存在."""
        assert COMPAT_SCRIPT.exists(), f"script not found at {COMPAT_SCRIPT}"

    def test_script_has_stab_p2_008_annotation(self):
        """脚本中有 STAB-P2-008 注释."""
        content = COMPAT_SCRIPT.read_text(encoding="utf-8")
        assert "STAB-P2-008" in content

    def test_script_runs_alembic_upgrade(self):
        """脚本调用 alembic upgrade head."""
        content = COMPAT_SCRIPT.read_text(encoding="utf-8")
        assert '"upgrade"' in content and '"head"' in content

    def test_script_runs_alembic_downgrade_base(self):
        """脚本调用 alembic downgrade base."""
        content = COMPAT_SCRIPT.read_text(encoding="utf-8")
        assert '"downgrade"' in content and '"base"' in content

    def test_script_runs_alembic_downgrade_one_step(self):
        """脚本调用 alembic downgrade -1 (单步回滚)."""
        content = COMPAT_SCRIPT.read_text(encoding="utf-8")
        assert '"-1"' in content

    def test_script_cleans_up_temp_db(self):
        """脚本运行后清理临时 DB 文件."""
        content = COMPAT_SCRIPT.read_text(encoding="utf-8")
        assert "os.unlink" in content or "cleanup" in content.lower()

    def test_script_has_main_function(self):
        """脚本有 main() 函数 + __main__ 入口."""
        content = COMPAT_SCRIPT.read_text(encoding="utf-8")
        assert "def main()" in content
        assert '__name__ == "__main__"' in content


class TestCIWorkflow:
    """CI workflow 配置测试."""

    def test_workflow_exists(self):
        """migration-tests.yml workflow 文件存在."""
        assert CI_WORKFLOW.exists(), f"workflow not found at {CI_WORKFLOW}"

    def test_workflow_has_stab_p2_008_annotation(self):
        """workflow 中有 STAB-P2-008 注释."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "STAB-P2-008" in content

    def test_workflow_triggers_on_pr(self):
        """workflow 在 PR 时触发."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "pull_request" in content

    def test_workflow_triggers_on_push_to_main(self):
        """workflow 在 push 到 main 分支时触发."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "push:" in content
        assert "main" in content

    def test_workflow_runs_compat_script(self):
        """workflow 调用 scripts/test_migration_compat.py."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "scripts/test_migration_compat.py" in content

    def test_workflow_runs_pytest(self):
        """workflow 调用 pytest 跑结构测试."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "pytest" in content
        assert "test_stab_p2_008_migration_compat" in content

    def test_workflow_uses_python_3_12(self):
        """workflow 使用 Python 3.12."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "3.12" in content

    def test_workflow_paths_filter_includes_alembic(self):
        """workflow path filter 包含 alembic 目录 (迁移变更时触发)."""
        content = CI_WORKFLOW.read_text(encoding="utf-8")
        assert "backend/alembic" in content


class TestEndToEndMigrationCompat:
    """端到端 alembic upgrade/downgrade 循环测试.

    通过子进程调用 alembic 命令, 验证迁移可逆性.

    策略:
    - **PostgreSQL 环境 (CI)**: 跑完整 upgrade head → downgrade base → upgrade head.
    - **SQLite 环境 (本地)**: 只跑前 2 个迁移 (eab25055097a + 5f2c9d3a1b7e),
      因为第 3 个迁移 b1a7c0d9f4e8 使用 ``op.create_check_constraint`` 而 SQLite
      不支持 ALTER TABLE ADD CONSTRAINT (需 batch mode, 改动生产代码风险大).
      SQLite 环境的完整端到端测试由 CI workflow 在 PostgreSQL 上执行
      (``scripts/test_migration_compat.py``).
    """

    # SQLite 可执行的最后一个迁移 (第 2 个, 不依赖 ALTER CONSTRAINT)
    SQLITE_COMPATIBLE_REVISION = "5f2c9d3a1b7e"

    @pytest.fixture
    def temp_db_url(self, tmp_path):
        """创建临时 DB URL.

        PostgreSQL 环境 (DATABASE_URL=postgresql://...) 使用临时 PG 数据库.
        SQLite 环境使用临时文件 DB.
        """
        env_db_url = os.environ.get("DATABASE_URL", "")
        if "postgresql" in env_db_url:
            # PostgreSQL: 使用独立的临时 DB 名 (避免与 testdb 冲突)
            # 解析原 URL 替换 database 名
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(env_db_url)
            db_name = f"migration_compat_{os.getpid()}"
            new_path = f"/{db_name}"
            pg_url = urlunparse(parsed._replace(path=new_path))
            # 创建临时 DB
            import psycopg2  # type: ignore[import-not-found]

            admin_url = env_db_url.rsplit("/", 1)[0] + "/postgres"
            admin = psycopg2.connect(admin_url, autocommit=True)
            try:
                with admin.cursor() as cur:
                    cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                    cur.execute(f'CREATE DATABASE "{db_name}"')
            finally:
                admin.close()
            yield pg_url, None
            # 清理: 删除临时 DB
            admin = psycopg2.connect(admin_url, autocommit=True)
            try:
                with admin.cursor() as cur:
                    cur.execute(
                        f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'
                    )
            finally:
                admin.close()
        else:
            # SQLite: 使用临时文件
            db_file = tmp_path / "migration_compat.db"
            yield f"sqlite:///{db_file}", db_file

    @pytest.fixture
    def is_postgres_env(self) -> bool:
        """检测当前是否为 PostgreSQL 环境."""
        return "postgresql" in os.environ.get("DATABASE_URL", "")

    def _run_alembic(
        self, *args: str, db_url: str
    ) -> subprocess.CompletedProcess[str]:
        """运行 alembic 命令."""
        env = os.environ.copy()
        env["DATABASE_URL"] = db_url
        cmd = [sys.executable, "-m", "alembic", *args]
        return subprocess.run(
            cmd,
            cwd=str(BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_alembic_command_available(self):
        """alembic 命令可用."""
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "--help"],
            cwd=str(BACKEND_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"alembic not available: {result.stderr}"
        )

    def test_upgrade_head_succeeds(self, temp_db_url, is_postgres_env):
        """alembic upgrade head 能从空 DB 升级到最新版本.

        PostgreSQL: 跑完整 upgrade head.
        SQLite: 只跑到第 2 个迁移 (SQLite 不支持 ALTER CONSTRAINT).
        """
        db_url, _ = temp_db_url
        target = "head" if is_postgres_env else self.SQLITE_COMPATIBLE_REVISION
        result = self._run_alembic("upgrade", target, db_url=db_url)
        assert result.returncode == 0, (
            f"alembic upgrade {target} failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_downgrade_base_succeeds(self, temp_db_url, is_postgres_env):
        """alembic downgrade base 能完整回滚到初始状态."""
        db_url, _ = temp_db_url
        target = "head" if is_postgres_env else self.SQLITE_COMPATIBLE_REVISION
        # 先升级到 target
        up_result = self._run_alembic("upgrade", target, db_url=db_url)
        assert up_result.returncode == 0, (
            f"setup upgrade failed: {up_result.stderr}"
        )
        # 回滚到 base
        down_result = self._run_alembic("downgrade", "base", db_url=db_url)
        assert down_result.returncode == 0, (
            f"alembic downgrade base failed:\n"
            f"stdout: {down_result.stdout}\nstderr: {down_result.stderr}"
        )

    def test_upgrade_downgrade_upgrade_cycle(self, temp_db_url, is_postgres_env):
        """upgrade → downgrade → upgrade 循环成功 (验证 downgrade 干净)."""
        db_url, _ = temp_db_url
        target = "head" if is_postgres_env else self.SQLITE_COMPATIBLE_REVISION

        # Step 1: upgrade target
        result1 = self._run_alembic("upgrade", target, db_url=db_url)
        assert result1.returncode == 0, (
            f"step 1 upgrade failed: {result1.stderr}"
        )

        # Step 2: downgrade base
        result2 = self._run_alembic("downgrade", "base", db_url=db_url)
        assert result2.returncode == 0, (
            f"step 2 downgrade failed: {result2.stderr}"
        )

        # Step 3: re-upgrade target (验证 downgrade 干净)
        result3 = self._run_alembic("upgrade", target, db_url=db_url)
        assert result3.returncode == 0, (
            f"step 3 re-upgrade failed (downgrade not clean):\n"
            f"stdout: {result3.stdout}\nstderr: {result3.stderr}"
        )

    def test_downgrade_one_step_succeeds(self, temp_db_url, is_postgres_env):
        """alembic downgrade -1 单步回滚最新迁移成功."""
        db_url, _ = temp_db_url
        target = "head" if is_postgres_env else self.SQLITE_COMPATIBLE_REVISION
        # 先升级到 target
        up_result = self._run_alembic("upgrade", target, db_url=db_url)
        assert up_result.returncode == 0
        # 单步回滚
        down_result = self._run_alembic("downgrade", "-1", db_url=db_url)
        assert down_result.returncode == 0, (
            f"alembic downgrade -1 failed:\n"
            f"stdout: {down_result.stdout}\nstderr: {down_result.stderr}"
        )

    def test_alembic_current_returns_version(self, temp_db_url, is_postgres_env):
        """alembic current 返回当前版本 (升级后应非空)."""
        db_url, _ = temp_db_url
        target = "head" if is_postgres_env else self.SQLITE_COMPATIBLE_REVISION
        # 升级到 target
        up_result = self._run_alembic("upgrade", target, db_url=db_url)
        assert up_result.returncode == 0
        # 查询当前版本
        cur_result = self._run_alembic("current", db_url=db_url)
        assert cur_result.returncode == 0
        # 输出应包含 revision id (12 位十六进制) 或 head 标记
        assert len(cur_result.stdout.strip()) > 0 or "head" in cur_result.stdout

    def test_sqlite_constraint_limitation_documented(self, is_postgres_env):
        """SQLite 不支持 ALTER CONSTRAINT, 此限制应在测试中显式记录.

        本测试验证: 我们已经识别 SQLite 的限制 (b1a7c0d9f4e8 迁移使用
        op.create_check_constraint), 并通过 SQLITE_COMPATIBLE_REVISION 截断
        SQLite 测试范围. 完整端到端测试由 CI 在 PostgreSQL 上执行.
        """
        # 验证截断 revision 是第 2 个迁移 (不是 head)
        if not is_postgres_env:
            assert self.SQLITE_COMPATIBLE_REVISION != "head"
            # 验证 SQLITE_COMPATIBLE_REVISION 确实存在
            revisions = TestMigrationChain._parse_revisions()
            assert self.SQLITE_COMPATIBLE_REVISION in revisions, (
                f"SQLITE_COMPATIBLE_REVISION {self.SQLITE_COMPATIBLE_REVISION} "
                "not found in migration chain"
            )


def _extract_str_literal(node: ast.AST) -> str | None:
    """从 AST 节点提取字符串字面量.

    Args:
        node: AST 节点 (期望是 ast.Constant 或 ast.Str).

    Returns:
        字符串值. 若节点不是字符串字面量, 返回 None.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Python 3.7 兼容 (ast.Str 已在 3.8 弃用)
    if hasattr(ast, "Str") and isinstance(node, ast.Str):  # type: ignore[attr-defined]
        return node.s  # type: ignore[attr-defined]
    return None
