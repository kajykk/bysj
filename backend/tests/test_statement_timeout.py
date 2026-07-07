"""STAB-P0-002 测试：数据库查询语句级超时 (statement_timeout)

验证要点：
1. PostgreSQL 模式下 ``connect_args.server_settings.statement_timeout`` 被正确设置
2. SQLite 模式下不设置 ``connect_args`` (SQLite 不支持 statement_timeout)
3. ``db_statement_timeout > 0`` 时启用, 值为秒 * 1000 毫秒
4. ``db_statement_timeout = 0`` 时禁用 (不设置 connect_args)
5. 不同 timeout 值能正确转换为毫秒字符串
6. ``_build_engine_kwargs`` 抽取函数的幂等性
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.database import _build_engine_kwargs


@dataclass
class FakeSettings:
    """模拟 Settings 对象, 仅暴露 _build_engine_kwargs 依赖的字段.

    使用 dataclass 而非 SimpleNamespace 以保证类型提示和默认值清晰.
    """

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_statement_timeout: int = 10


class TestBuildEngineKwargsSqlite:
    """SQLite 模式: 不应设置 connect_args (不支持 statement_timeout)."""

    def test_sqlite_has_no_connect_args(self):
        """SQLite 模式下 kwargs 中不应包含 connect_args."""
        kwargs = _build_engine_kwargs(is_sqlite=True, settings_obj=FakeSettings())
        assert "connect_args" not in kwargs

    def test_sqlite_has_no_pool_args(self):
        """SQLite 模式下 kwargs 不应包含连接池参数 (SQLite 使用默认)."""
        kwargs = _build_engine_kwargs(is_sqlite=True, settings_obj=FakeSettings())
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs
        assert "pool_timeout" not in kwargs
        assert "pool_recycle" not in kwargs

    def test_sqlite_keeps_base_args(self):
        """SQLite 模式下应保留 echo/future/pool_pre_ping 基础参数."""
        kwargs = _build_engine_kwargs(is_sqlite=True, settings_obj=FakeSettings())
        assert kwargs["echo"] is False
        assert kwargs["future"] is True
        assert kwargs["pool_pre_ping"] is True

    def test_sqlite_ignores_statement_timeout_value(self):
        """SQLite 模式下即使 db_statement_timeout > 0 也不应设置 connect_args."""
        settings_obj = FakeSettings(db_statement_timeout=30)
        kwargs = _build_engine_kwargs(is_sqlite=True, settings_obj=settings_obj)
        assert "connect_args" not in kwargs


class TestBuildEngineKwargsPostgres:
    """PostgreSQL 模式: 应正确设置 statement_timeout."""

    def test_postgres_default_timeout_10s(self):
        """默认 db_statement_timeout=10 应转换为 10000 毫秒字符串."""
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=FakeSettings())
        assert "connect_args" in kwargs
        server_settings = kwargs["connect_args"]["server_settings"]
        assert server_settings["statement_timeout"] == "10000"

    def test_postgres_custom_timeout_30s(self):
        """db_statement_timeout=30 应转换为 30000 毫秒字符串."""
        settings_obj = FakeSettings(db_statement_timeout=30)
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        server_settings = kwargs["connect_args"]["server_settings"]
        assert server_settings["statement_timeout"] == "30000"

    def test_postgres_timeout_value_is_string(self):
        """statement_timeout 值应为字符串类型 (asyncpg server_settings 要求)."""
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=FakeSettings())
        timeout_value = kwargs["connect_args"]["server_settings"]["statement_timeout"]
        assert isinstance(timeout_value, str)

    def test_postgres_timeout_5s(self):
        """db_statement_timeout=5 应转换为 5000 毫秒."""
        settings_obj = FakeSettings(db_statement_timeout=5)
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "5000"

    def test_postgres_timeout_60s(self):
        """db_statement_timeout=60 应转换为 60000 毫秒."""
        settings_obj = FakeSettings(db_statement_timeout=60)
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "60000"

    def test_postgres_disabled_when_timeout_zero(self):
        """db_statement_timeout=0 应禁用 (不设置 connect_args)."""
        settings_obj = FakeSettings(db_statement_timeout=0)
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        assert "connect_args" not in kwargs

    def test_postgres_has_pool_args(self):
        """PostgreSQL 模式应设置连接池参数."""
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=FakeSettings())
        assert kwargs["pool_size"] == 20
        assert kwargs["max_overflow"] == 10
        assert kwargs["pool_timeout"] == 30
        assert kwargs["pool_recycle"] == 1800

    def test_postgres_custom_pool_args(self):
        """PostgreSQL 模式应从 settings 读取连接池参数."""
        settings_obj = FakeSettings(
            db_pool_size=50,
            db_max_overflow=20,
            db_pool_timeout=60,
            db_pool_recycle=3600,
        )
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        assert kwargs["pool_size"] == 50
        assert kwargs["max_overflow"] == 20
        assert kwargs["pool_timeout"] == 60
        assert kwargs["pool_recycle"] == 3600

    def test_postgres_keeps_base_args(self):
        """PostgreSQL 模式应保留 echo/future/pool_pre_ping 基础参数."""
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=FakeSettings())
        assert kwargs["echo"] is False
        assert kwargs["future"] is True
        assert kwargs["pool_pre_ping"] is True

    def test_postgres_connect_args_structure(self):
        """connect_args 应为 dict, 包含 server_settings 键."""
        kwargs = _build_engine_kwargs(is_sqlite=False, settings_obj=FakeSettings())
        connect_args = kwargs["connect_args"]
        assert isinstance(connect_args, dict)
        assert "server_settings" in connect_args
        assert isinstance(connect_args["server_settings"], dict)


class TestBuildEngineKwargsIdempotent:
    """验证 _build_engine_kwargs 多次调用结果一致 (无副作用)."""

    def test_multiple_calls_same_result(self):
        """相同输入应产生相同输出 (函数应为纯函数)."""
        settings_obj = FakeSettings(db_statement_timeout=15)
        kwargs1 = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        kwargs2 = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        assert kwargs1 == kwargs2

    def test_does_not_mutate_settings(self):
        """函数不应修改传入的 settings 对象."""
        settings_obj = FakeSettings(db_statement_timeout=10)
        _ = _build_engine_kwargs(is_sqlite=False, settings_obj=settings_obj)
        assert settings_obj.db_statement_timeout == 10
        assert settings_obj.db_pool_size == 20


class TestEngineKwargsIntegration:
    """验证 database.py 模块级 engine_kwargs 与 _build_engine_kwargs 一致."""

    def test_module_engine_kwargs_matches_helper(self):
        """模块级 engine_kwargs 应等于 _build_engine_kwargs(settings) 的返回值."""
        from app.core.config import settings
        from app.core.database import _build_engine_kwargs, _is_sqlite, engine_kwargs

        expected = _build_engine_kwargs(_is_sqlite, settings)
        assert engine_kwargs == expected

    def test_module_engine_kwargs_is_dict(self):
        """模块级 engine_kwargs 应为 dict 类型."""
        from app.core.database import engine_kwargs

        assert isinstance(engine_kwargs, dict)

    def test_module_engine_kwargs_has_pool_pre_ping(self):
        """模块级 engine_kwargs 应始终包含 pool_pre_ping=True (防陈旧连接)."""
        from app.core.database import engine_kwargs

        assert engine_kwargs.get("pool_pre_ping") is True


class TestStatementTimeoutDefaultConfig:
    """验证 config.py 默认配置符合 STAB-P0-002 设计意图."""

    def test_default_statement_timeout_is_10s(self):
        """config.py 中 db_statement_timeout 默认值应为 10 秒."""
        from app.core.config import settings

        assert settings.db_statement_timeout == 10

    def test_default_statement_timeout_positive(self):
        """默认 db_statement_timeout 应 > 0 (启用)."""
        from app.core.config import settings

        assert settings.db_statement_timeout > 0
