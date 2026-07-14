"""STAB-P2-006 专项测试: 金丝雀扩展按路由前缀分流.

验证 CanaryRecord.route_prefix 字段 + CanaryManager.get_active_canary/decide_version/start_canary 支持 route_prefix:
- route_prefix=None: 全局金丝雀 (覆盖所有路由, 向后兼容)
- route_prefix="/api/v1/reports": 特定路由金丝雀 (仅覆盖该路由前缀)
- get_active_canary: 特定路由优先匹配, 回退到全局
- start_canary: 同一 route_prefix 仅允许一个活跃金丝雀
- Schema + API: route_prefix 字段传递
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.models.monitoring import CanaryRecord, CanaryStatus
from app.schemas.canary import CanaryCreateRequest, CanaryDeploymentResponse, CanaryListItem
from app.services.canary_manager import CanaryManager


class TestModelStructure:
    """CanaryRecord 模型结构测试."""

    def test_route_prefix_field_exists(self) -> None:
        """CanaryRecord 有 route_prefix 字段."""
        assert hasattr(CanaryRecord, "route_prefix")

    def test_route_prefix_nullable(self) -> None:
        """route_prefix 字段 nullable=True (NULL=覆盖所有路由)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(CanaryRecord)
        col = mapper.columns.get("route_prefix")
        assert col is not None
        assert col.nullable is True

    def test_route_prefix_type_string(self) -> None:
        """route_prefix 字段类型为 String(100)."""
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import String

        mapper = sa_inspect(CanaryRecord)
        col = mapper.columns.get("route_prefix")
        assert col is not None
        assert isinstance(col.type, String)
        assert col.type.length == 100

    def test_route_prefix_has_stab_p2_006_comment(self) -> None:
        """route_prefix 字段 comment 标注 STAB-P2-006."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(CanaryRecord)
        col = mapper.columns.get("route_prefix")
        assert col is not None
        assert col.comment is not None
        assert "STAB-P2-006" in col.comment


class TestMigrationFile:
    """Migration 文件测试."""

    def test_migration_file_exists(self) -> None:
        """migration 文件存在."""
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "k2a7b8c9d0e1_add_canary_route_prefix.py",
        )
        assert os.path.exists(path)

    def test_migration_revision_id(self) -> None:
        """migration revision ID 正确."""
        import importlib.util
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "k2a7b8c9d0e1_add_canary_route_prefix.py",
        )
        spec = importlib.util.spec_from_file_location("migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "k2a7b8c9d0e1"
        assert module.down_revision == "j1f6a7b8c9d0"

    def test_migration_adds_route_prefix_column(self) -> None:
        """migration upgrade 添加 route_prefix 列."""
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "k2a7b8c9d0e1_add_canary_route_prefix.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "add_column" in content
        assert "route_prefix" in content
        assert "STAB-P2-006" in content

    def test_migration_creates_index(self) -> None:
        """migration 创建复合索引 (status, route_prefix)."""
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "k2a7b8c9d0e1_add_canary_route_prefix.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "create_index" in content
        assert "ix_canary_records_status_route_prefix" in content

    def test_migration_downgrade(self) -> None:
        """migration downgrade 正确回滚."""
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "k2a7b8c9d0e1_add_canary_route_prefix.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "def downgrade" in content
        assert "drop_index" in content
        assert "drop_column" in content


class TestSchemaStructure:
    """Schema 结构测试."""

    def test_create_request_has_route_prefix(self) -> None:
        """CanaryCreateRequest 有 route_prefix 字段."""
        assert "route_prefix" in CanaryCreateRequest.model_fields

    def test_create_request_route_prefix_default_none(self) -> None:
        """CanaryCreateRequest.route_prefix 默认 None."""
        field = CanaryCreateRequest.model_fields["route_prefix"]
        assert field.default is None

    def test_create_request_route_prefix_max_length(self) -> None:
        """CanaryCreateRequest.route_prefix max_length=100."""
        # 验证 max_length 通过尝试创建超长值
        with pytest.raises(Exception):
            CanaryCreateRequest(
                version="test",
                route_prefix="x" * 101,
            )

    def test_deployment_response_has_route_prefix(self) -> None:
        """CanaryDeploymentResponse 有 route_prefix 字段."""
        assert "route_prefix" in CanaryDeploymentResponse.model_fields

    def test_list_item_has_route_prefix(self) -> None:
        """CanaryListItem 有 route_prefix 字段."""
        assert "route_prefix" in CanaryListItem.model_fields


class TestCanaryManagerSourceStructure:
    """CanaryManager 源码结构测试."""

    def test_get_active_canary_has_route_prefix_param(self) -> None:
        """get_active_canary 有 route_prefix 参数."""
        sig = inspect.signature(CanaryManager.get_active_canary)
        assert "route_prefix" in sig.parameters
        param = sig.parameters["route_prefix"]
        assert param.default is None

    def test_decide_version_has_route_prefix_param(self) -> None:
        """decide_version 有 route_prefix 参数."""
        sig = inspect.signature(CanaryManager.decide_version)
        assert "route_prefix" in sig.parameters
        param = sig.parameters["route_prefix"]
        assert param.default is None

    def test_start_canary_has_route_prefix_param(self) -> None:
        """start_canary 有 route_prefix 参数."""
        sig = inspect.signature(CanaryManager.start_canary)
        assert "route_prefix" in sig.parameters
        param = sig.parameters["route_prefix"]
        assert param.default is None

    def test_get_active_canary_route_prefix_filter_logic(self) -> None:
        """get_active_canary 包含 route_prefix 过滤逻辑."""
        source = inspect.getsource(CanaryManager.get_active_canary)
        assert "route_prefix" in source
        assert "is_(None)" in source
        assert "STAB-P2-006" in source

    def test_start_canary_route_prefix_conflict_check(self) -> None:
        """start_canary 检查同一 route_prefix 冲突."""
        source = inspect.getsource(CanaryManager.start_canary)
        assert "route_prefix" in source
        assert "already running" in source.lower() or "已运行" in source


@pytest.mark.asyncio
class TestGetActiveCanaryRoutePrefix:
    """get_active_canary route_prefix 过滤测试."""

    async def test_global_canary_no_route_prefix(self, db_session) -> None:
        """route_prefix=None: 仅匹配 route_prefix IS NULL 的全局金丝雀."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        global_canary = CanaryRecord(
            version="v1.0-global",
            traffic_percent=10,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix=None,
        )
        route_canary = CanaryRecord(
            version="v1.0-reports",
            traffic_percent=20,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix="/api/v1/reports",
        )
        db_session.add_all([global_canary, route_canary])
        await db_session.flush()

        manager = CanaryManager()
        result = await manager.get_active_canary(db_session, route_prefix=None)
        assert result is not None
        assert result.version == "v1.0-global"
        assert result.route_prefix is None

    async def test_route_specific_canary_preferred(self, db_session) -> None:
        """route_prefix='/api/v1/reports': 优先匹配特定路由金丝雀."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        global_canary = CanaryRecord(
            version="v1.0-global",
            traffic_percent=10,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix=None,
        )
        route_canary = CanaryRecord(
            version="v1.0-reports",
            traffic_percent=20,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix="/api/v1/reports",
        )
        db_session.add_all([global_canary, route_canary])
        await db_session.flush()

        manager = CanaryManager()
        result = await manager.get_active_canary(
            db_session, route_prefix="/api/v1/reports"
        )
        assert result is not None
        assert result.version == "v1.0-reports"
        assert result.route_prefix == "/api/v1/reports"

    async def test_fallback_to_global_when_no_route_specific(self, db_session) -> None:
        """无特定路由金丝雀时, 回退到全局金丝雀."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        global_canary = CanaryRecord(
            version="v1.0-global",
            traffic_percent=10,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix=None,
        )
        db_session.add(global_canary)
        await db_session.flush()

        manager = CanaryManager()
        # 查询 /api/v1/reports, 但只有全局金丝雀 → 回退
        result = await manager.get_active_canary(
            db_session, route_prefix="/api/v1/reports"
        )
        assert result is not None
        assert result.version == "v1.0-global"
        assert result.route_prefix is None

    async def test_no_canary_returns_none(self, db_session) -> None:
        """无活跃金丝雀时返回 None."""
        manager = CanaryManager()
        result = await manager.get_active_canary(db_session, route_prefix=None)
        assert result is None

    async def test_different_route_prefix_not_matched(self, db_session) -> None:
        """不同 route_prefix 的金丝雀不匹配, 但回退到全局."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        reports_canary = CanaryRecord(
            version="v1.0-reports",
            traffic_percent=20,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix="/api/v1/reports",
        )
        db_session.add(reports_canary)
        await db_session.flush()

        manager = CanaryManager()
        # 查询 /api/v1/counselor, 只有 /api/v1/reports 金丝雀 → 无精确匹配, 无全局 → None
        result = await manager.get_active_canary(
            db_session, route_prefix="/api/v1/counselor"
        )
        assert result is None

    async def test_non_running_canary_not_matched(self, db_session) -> None:
        """非 RUNNING 状态的金丝雀不匹配."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        completed_canary = CanaryRecord(
            version="v1.0-old",
            traffic_percent=100,
            status=CanaryStatus.COMPLETED,
            started_at=now,
            route_prefix=None,
        )
        db_session.add(completed_canary)
        await db_session.flush()

        manager = CanaryManager()
        result = await manager.get_active_canary(db_session, route_prefix=None)
        assert result is None


@pytest.mark.asyncio
class TestStartCanaryRoutePrefix:
    """start_canary route_prefix 测试."""

    async def test_start_global_canary(self, db_session) -> None:
        """启动全局金丝雀 (route_prefix=None)."""
        manager = CanaryManager()
        canary = await manager.start_canary(
            db_session=db_session,
            version="v1.0",
            traffic_percent=10,
            route_prefix=None,
        )
        assert canary.version == "v1.0"
        assert canary.route_prefix is None
        assert canary.status == CanaryStatus.RUNNING

    async def test_start_route_specific_canary(self, db_session) -> None:
        """启动特定路由金丝雀 (route_prefix='/api/v1/reports')."""
        manager = CanaryManager()
        canary = await manager.start_canary(
            db_session=db_session,
            version="v1.0-reports",
            traffic_percent=20,
            route_prefix="/api/v1/reports",
        )
        assert canary.version == "v1.0-reports"
        assert canary.route_prefix == "/api/v1/reports"

    async def test_start_global_conflict_with_global(self, db_session) -> None:
        """全局金丝雀冲突: 已有全局金丝雀时, 再启动全局金丝雀报错."""
        manager = CanaryManager()
        await manager.start_canary(
            db_session=db_session,
            version="v1.0",
            traffic_percent=10,
            route_prefix=None,
        )

        with pytest.raises(ValueError, match="already running"):
            await manager.start_canary(
                db_session=db_session,
                version="v2.0",
                traffic_percent=20,
                route_prefix=None,
            )

    async def test_start_route_specific_conflict_same_route(self, db_session) -> None:
        """同路由金丝雀冲突: 同 route_prefix 仅允许一个活跃金丝雀."""
        manager = CanaryManager()
        await manager.start_canary(
            db_session=db_session,
            version="v1.0-reports",
            traffic_percent=10,
            route_prefix="/api/v1/reports",
        )

        with pytest.raises(ValueError, match="already running"):
            await manager.start_canary(
                db_session=db_session,
                version="v2.0-reports",
                traffic_percent=20,
                route_prefix="/api/v1/reports",
            )

    async def test_start_different_route_no_conflict(self, db_session) -> None:
        """不同路由金丝雀不冲突: 可同时启动不同 route_prefix 的金丝雀."""
        manager = CanaryManager()
        canary1 = await manager.start_canary(
            db_session=db_session,
            version="v1.0-reports",
            traffic_percent=10,
            route_prefix="/api/v1/reports",
        )
        canary2 = await manager.start_canary(
            db_session=db_session,
            version="v1.0-counselor",
            traffic_percent=20,
            route_prefix="/api/v1/counselor",
        )
        assert canary1.route_prefix == "/api/v1/reports"
        assert canary2.route_prefix == "/api/v1/counselor"

    async def test_start_global_and_route_specific_no_conflict(self, db_session) -> None:
        """全局 + 特定路由不冲突: 可同时启动全局金丝雀和特定路由金丝雀."""
        manager = CanaryManager()
        global_canary = await manager.start_canary(
            db_session=db_session,
            version="v1.0-global",
            traffic_percent=10,
            route_prefix=None,
        )
        route_canary = await manager.start_canary(
            db_session=db_session,
            version="v1.0-reports",
            traffic_percent=20,
            route_prefix="/api/v1/reports",
        )
        assert global_canary.route_prefix is None
        assert route_canary.route_prefix == "/api/v1/reports"


@pytest.mark.asyncio
class TestDecideVersionRoutePrefix:
    """decide_version route_prefix 测试."""

    async def test_decide_version_global_canary(self, db_session) -> None:
        """decide_version 不传 route_prefix: 匹配全局金丝雀."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        global_canary = CanaryRecord(
            version="v1.0-canary",
            traffic_percent=50,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix=None,
        )
        db_session.add(global_canary)
        await db_session.flush()

        manager = CanaryManager()
        # user_id=1 的 hash 应在 0-99 之间, 50% 概率匹配
        # 使用 traffic_percent=100 确保匹配
        global_canary.traffic_percent = 100
        await db_session.flush()

        decision = await manager.decide_version(
            db_session, user_id=1, stable_version="v1.0", route_prefix=None
        )
        assert decision.use_canary is True
        assert decision.canary_version == "v1.0-canary"

    async def test_decide_version_route_specific_preferred(self, db_session) -> None:
        """decide_version 传 route_prefix: 优先匹配特定路由金丝雀."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        global_canary = CanaryRecord(
            version="v1.0-global",
            traffic_percent=100,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix=None,
        )
        route_canary = CanaryRecord(
            version="v1.0-reports",
            traffic_percent=100,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix="/api/v1/reports",
        )
        db_session.add_all([global_canary, route_canary])
        await db_session.flush()

        manager = CanaryManager()
        decision = await manager.decide_version(
            db_session,
            user_id=1,
            stable_version="v1.0",
            route_prefix="/api/v1/reports",
        )
        assert decision.use_canary is True
        assert decision.canary_version == "v1.0-reports"

    async def test_decide_version_fallback_to_global(self, db_session) -> None:
        """decide_version 传 route_prefix 但无特定路由: 回退到全局."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        global_canary = CanaryRecord(
            version="v1.0-global",
            traffic_percent=100,
            status=CanaryStatus.RUNNING,
            started_at=now,
            route_prefix=None,
        )
        db_session.add(global_canary)
        await db_session.flush()

        manager = CanaryManager()
        decision = await manager.decide_version(
            db_session,
            user_id=1,
            stable_version="v1.0",
            route_prefix="/api/v1/counselor",  # 无特定路由金丝雀
        )
        assert decision.use_canary is True
        assert decision.canary_version == "v1.0-global"

    async def test_decide_version_no_active_canary(self, db_session) -> None:
        """无活跃金丝雀时: use_canary=False."""
        manager = CanaryManager()
        decision = await manager.decide_version(
            db_session, user_id=1, stable_version="v1.0", route_prefix=None
        )
        assert decision.use_canary is False
        assert decision.reason == "no_active_canary"


class TestApiSourceStructure:
    """API 源码结构测试."""

    def test_create_canary_passes_route_prefix(self) -> None:
        """create_canary 端点传递 route_prefix."""
        from app.api.v1 import canary as canary_api

        source = inspect.getsource(canary_api)
        # 查找 create_canary 函数
        func_start = source.find("async def create_canary")
        assert func_start != -1
        func_source = source[func_start : func_start + 1000]
        assert "route_prefix" in func_source
        assert "payload.route_prefix" in func_source

    def test_list_canaries_includes_route_prefix(self) -> None:
        """list_canaries 端点返回 route_prefix."""
        from app.api.v1 import canary as canary_api

        source = inspect.getsource(canary_api)
        # 查找 list_canaries 函数
        func_start = source.find("async def list_canaries")
        assert func_start != -1
        func_source = source[func_start : func_start + 2000]
        assert "route_prefix" in func_source

    def test_deployment_response_includes_route_prefix(self) -> None:
        """create_canary 的 CanaryDeploymentResponse 包含 route_prefix."""
        from app.api.v1 import canary as canary_api

        source = inspect.getsource(canary_api)
        func_start = source.find("async def create_canary")
        assert func_start != -1
        func_source = source[func_start : func_start + 1500]
        assert "route_prefix=canary.route_prefix" in func_source
