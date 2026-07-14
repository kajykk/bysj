"""PERF-P2-002 专项测试: RiskAssessment is_latest 标志位.

验证 is_latest 字段存在、创建时正确维护、查询时正确使用,
消除 list_my_users 中的 GROUP BY + max(created_at) 子查询.
"""

from __future__ import annotations

import ast
import importlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.models.risk import RiskAssessment

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_APP_DIR = _BACKEND_DIR / "app"


# ─────────────────────────── 模型结构测试 ───────────────────────────


class TestModelStructure:
    """验证 RiskAssessment 模型包含 is_latest 字段和索引."""

    def test_model_has_is_latest_column(self):
        """模型定义包含 is_latest Boolean 字段."""
        assert hasattr(RiskAssessment, "is_latest"), (
            "RiskAssessment 必须有 is_latest 字段 (PERF-P2-002)"
        )

    def test_is_latest_has_default_false(self):
        """is_latest 默认值为 False."""
        col = RiskAssessment.__table__.c.is_latest
        assert col.default is not None or col.server_default is not None, (
            "is_latest 必须有默认值"
        )
        # server_default="0" 或 default=False
        if col.server_default is not None:
            server_default_text = str(col.server_default.arg)
            assert "0" in server_default_text, (
                f"is_latest server_default 应为 0 (False), 实际: {server_default_text}"
            )

    def test_model_has_composite_index(self):
        """模型定义包含 (user_id, is_latest) 复合索引."""
        index_names = [idx.name for idx in RiskAssessment.__table__.indexes]
        assert "ix_risk_assessments_user_is_latest" in index_names, (
            "必须有 ix_risk_assessments_user_is_latest 复合索引"
        )

    def test_is_latest_is_boolean_type(self):
        """is_latest 字段类型为 Boolean."""
        from sqlalchemy import Boolean

        col = RiskAssessment.__table__.c.is_latest
        assert isinstance(col.type, Boolean), (
            f"is_latest 类型应为 Boolean, 实际: {type(col.type)}"
        )


# ─────────────────────────── 迁移文件测试 ───────────────────────────


class TestMigrationFile:
    """验证 alembic 迁移文件结构."""

    def test_migration_file_exists(self):
        """迁移文件存在."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        assert migration_file.exists(), f"迁移文件不存在: {migration_file}"

    def test_migration_revision_and_down_revision(self):
        """迁移文件有正确的 revision 和 down_revision."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        content = migration_file.read_text(encoding="utf-8")
        assert 'revision: str = "j1f6a7b8c9d0"' in content
        assert 'down_revision: Union[str, None] = "i0e5f6a7b8c9"' in content

    def test_migration_has_upgrade_with_add_column(self):
        """迁移 upgrade() 包含 add_column 操作."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        content = migration_file.read_text(encoding="utf-8")
        assert "add_column" in content
        assert "is_latest" in content
        assert "risk_assessments" in content

    def test_migration_has_backfill_update(self):
        """迁移包含回填 UPDATE 语句 (标记最新风险评估)."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        content = migration_file.read_text(encoding="utf-8")
        assert "UPDATE risk_assessments" in content or "update" in content.lower()
        assert "is_latest = 1" in content or "is_latest" in content

    def test_migration_creates_index(self):
        """迁移创建 ix_risk_assessments_user_is_latest 索引."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        content = migration_file.read_text(encoding="utf-8")
        assert "create_index" in content
        assert "ix_risk_assessments_user_is_latest" in content

    def test_migration_has_downgrade(self):
        """迁移有 downgrade() 删除列和索引."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        content = migration_file.read_text(encoding="utf-8")
        assert "def downgrade" in content
        assert "drop_index" in content
        assert "drop_column" in content

    def test_migration_has_perf_p2_002_comment(self):
        """迁移文件包含 PERF-P2-002 注释."""
        migration_file = (
            _BACKEND_DIR
            / "alembic"
            / "versions"
            / "j1f6a7b8c9d0_add_risk_assessment_is_latest.py"
        )
        content = migration_file.read_text(encoding="utf-8")
        assert "PERF-P2-002" in content


# ─────────────────────────── 源码静态扫描测试 ───────────────────────────


class TestSourceCodeUsesIsLatest:
    """验证生产代码使用 is_latest 标志替代 GROUP BY 子查询."""

    def test_counselor_service_uses_is_latest_in_list_my_users(self):
        """counselor_service_user.py list_my_users 使用 is_latest.

        MAINT-P2-001: list_my_users 已随 UserMixin 拆分到 counselor_service_user.py。
        """
        content = (_APP_DIR / "services" / "counselor_service_user.py").read_text(
            encoding="utf-8"
        )
        assert "is_latest" in content, "counselor_service_user.py 必须引用 is_latest"

    def test_counselor_service_no_func_max_in_list_my_users(self):
        """counselor_service_user.py 不再使用 func.max(RiskAssessment.created_at).

        MAINT-P2-001: list_my_users 已随 UserMixin 拆分到 counselor_service_user.py。
        """
        content = (_APP_DIR / "services" / "counselor_service_user.py").read_text(
            encoding="utf-8"
        )
        # 不应存在 func.max(RiskAssessment.created_at) 模式
        assert "func.max(RiskAssessment.created_at)" not in content, (
            "counselor_service_user.py 不应再使用 func.max(RiskAssessment.created_at) 子查询"
        )

    def test_risk_service_sets_is_latest_on_create(self):
        """risk_service_assessment.py 创建 RiskAssessment 时设置 is_latest=True.

        MAINT-P2-001: assess_structured 已随 AssessmentMixin 拆分到
        risk_service_assessment.py。
        """
        content = (
            _APP_DIR / "services" / "risk_service_assessment.py"
        ).read_text(encoding="utf-8")
        assert "is_latest=True" in content, (
            "risk_service_assessment.py 创建 RiskAssessment 时必须设置 is_latest=True"
        )
        assert "is_latest" in content

    def test_risk_service_clears_old_is_latest(self):
        """risk_service_assessment.py 清除旧 is_latest 标志.

        MAINT-P2-001: assess_structured 已随 AssessmentMixin 拆分到
        risk_service_assessment.py。
        """
        content = (
            _APP_DIR / "services" / "risk_service_assessment.py"
        ).read_text(encoding="utf-8")
        assert "is_latest=False" in content, (
            "risk_service_assessment.py 必须清除旧 is_latest 标志"
        )

    def test_user_data_service_sets_is_latest(self):
        """user_data_service.py 创建 RiskAssessment 时维护 is_latest."""
        content = (_APP_DIR / "services" / "user_data_service.py").read_text(
            encoding="utf-8"
        )
        assert "is_latest=True" in content
        assert "is_latest=False" in content

    def test_common_sets_is_latest(self):
        """_common.py 创建 RiskAssessment 时维护 is_latest."""
        content = (
            _APP_DIR / "api" / "v1" / "model_predict" / "_common.py"
        ).read_text(encoding="utf-8")
        assert "is_latest=True" in content
        assert "is_latest=False" in content

    def test_seed_sets_is_latest(self):
        """seed.py 创建 RiskAssessment 时设置 is_latest=True."""
        content = (_APP_DIR / "core" / "seed.py").read_text(encoding="utf-8")
        assert "is_latest=True" in content

    def test_scheduler_uses_is_latest(self):
        """scheduler.py 使用 is_latest 替代 ORDER BY."""
        content = (_APP_DIR / "tasks" / "scheduler.py").read_text(encoding="utf-8")
        assert "is_latest" in content

    def test_content_service_uses_is_latest(self):
        """content_service.py 使用 is_latest 替代 ORDER BY."""
        content = (_APP_DIR / "services" / "content_service.py").read_text(
            encoding="utf-8"
        )
        assert "is_latest" in content

    def test_counselor_service_get_user_detail_uses_is_latest(self):
        """counselor_service_user.py get_user_detail 使用 is_latest.

        MAINT-P2-001: get_user_detail 已随 UserMixin 拆分到 counselor_service_user.py。
        """
        content = (_APP_DIR / "services" / "counselor_service_user.py").read_text(
            encoding="utf-8"
        )
        # 找到 get_user_detail 方法
        assert "def get_user_detail" in content
        # 在 get_user_detail 方法中应该使用 is_latest
        get_detail_start = content.index("def get_user_detail")
        # 查找下一个 def 或文件结尾
        next_def = content.find("\n    async def ", get_detail_start + 1)
        if next_def == -1:
            next_def = len(content)
        method_content = content[get_detail_start:next_def]
        assert "is_latest" in method_content, (
            "get_user_detail 方法必须使用 is_latest 标志"
        )


# ─────────────────────────── 数据库集成测试 ───────────────────────────


@pytest.mark.asyncio
class TestIsLatestMaintenance:
    """验证 is_latest 标志在数据库操作中的正确维护."""

    @staticmethod
    def _make_user(suffix: str) -> "User":
        """创建带必填字段的测试用户."""
        from app.core.pii_crypto import compute_blind_index
        from app.models.user import User

        email = f"test_{suffix}@test.com"
        return User(
            username=f"test_{suffix}",
            email=email,
            email_hash=compute_blind_index(email, "email"),
            password_hash="hash",
            role="user",
            status="active",
        )

    async def test_new_assessment_has_is_latest_true(self, db_session):
        """新创建的 RiskAssessment 有 is_latest=True."""
        # 直接创建 RiskAssessment (模拟应用层行为)
        user = self._make_user("is_latest_user")
        db_session.add(user)
        await db_session.flush()

        risk = RiskAssessment(
            user_id=user.id,
            risk_score=50.0,
            risk_level=3,
            is_latest=True,
        )
        db_session.add(risk)
        await db_session.flush()

        # 验证 is_latest=True
        assert risk.is_latest is True

    async def test_only_one_is_latest_per_user(self, db_session):
        """每个用户只有一条 is_latest=True 的风险评估."""
        user = self._make_user("multi_risk")
        db_session.add(user)
        await db_session.flush()

        # 创建 3 条风险评估, 模拟应用层行为: 新建时清除旧的 is_latest
        for i in range(3):
            # 清除旧 is_latest
            from sqlalchemy import update

            await db_session.execute(
                update(RiskAssessment)
                .where(
                    RiskAssessment.user_id == user.id,
                    RiskAssessment.is_latest.is_(True),
                )
                .values(is_latest=False)
            )
            risk = RiskAssessment(
                user_id=user.id,
                risk_score=float(50 + i * 10),
                risk_level=3 + i,
                is_latest=True,
            )
            db_session.add(risk)
            await db_session.flush()

        # 查询该用户所有风险评估
        stmt = select(RiskAssessment).where(RiskAssessment.user_id == user.id)
        risks = (await db_session.execute(stmt)).scalars().all()
        assert len(risks) == 3

        # 验证只有一条 is_latest=True
        latest_count = sum(1 for r in risks if r.is_latest)
        assert latest_count == 1, f"应有 1 条 is_latest=True, 实际 {latest_count} 条"

        # 验证 is_latest=True 的是最后创建的 (risk_score=70)
        latest = next(r for r in risks if r.is_latest)
        assert latest.risk_score == 70.0

    async def test_query_latest_risk_by_is_latest(self, db_session):
        """通过 WHERE is_latest=True 查询最新风险评估."""
        from sqlalchemy import update

        user = self._make_user("query_latest")
        db_session.add(user)
        await db_session.flush()

        # 创建 2 条风险评估
        risk1 = RiskAssessment(
            user_id=user.id, risk_score=30.0, risk_level=2, is_latest=True
        )
        db_session.add(risk1)
        await db_session.flush()

        # 更新 risk1 的 is_latest 为 False, 创建 risk2
        await db_session.execute(
            update(RiskAssessment)
            .where(
                RiskAssessment.user_id == user.id,
                RiskAssessment.is_latest.is_(True),
            )
            .values(is_latest=False)
        )
        risk2 = RiskAssessment(
            user_id=user.id, risk_score=80.0, risk_level=5, is_latest=True
        )
        db_session.add(risk2)
        await db_session.flush()

        # 使用 is_latest 查询
        stmt = (
            select(RiskAssessment)
            .where(
                RiskAssessment.user_id == user.id,
                RiskAssessment.is_latest.is_(True),
            )
            .limit(1)
        )
        latest = (await db_session.execute(stmt)).scalar_one_or_none()

        assert latest is not None
        assert latest.risk_score == 80.0
        assert latest.id == risk2.id
