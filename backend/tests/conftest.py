from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

# Fix Windows DLL issues with sklearn/pandas/numpy
# Must be set BEFORE importing any scientific computing libraries
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import pytest
import pytest_asyncio
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# pytest-asyncio 配置
pytestmark = pytest.mark.asyncio(loop_scope="function")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
# P1-SEC-001 修复：为测试环境提供 PII 加密密钥（仅用于单元测试，非生产密钥）
os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-only-not-for-production"
)
# H-Core-7 修复：seed.py 在模块导入时读取 E2E_*_PASSWORD，必须在 app 导入前设置
os.environ.setdefault("E2E_ADMIN_PASSWORD", "TestAdminPwd-2024-Secure!")
os.environ.setdefault("E2E_COUNSELOR_PASSWORD", "TestCounselorPwd-2024-Secure!")
os.environ.setdefault("E2E_USER_PASSWORD", "TestUserPwd-2024-Secure!")

# CI 环境 DATABASE_URL 可能指向 PostgreSQL, 但测试引擎默认用 SQLite (TEST_DATABASE_URL 未设置).
# 覆盖 DATABASE_URL 确保 settings.database_url 与测试引擎一致, 避免 _is_sqlite 误判
# (monitoring.py 的 to_char vs strftime 选择) 和模块级 engine 事件循环不匹配.
if not os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_app.db"

from starlette.requests import Request as StarletteRequest

from app.core.database import get_db
from app.core.deps import get_current_user, oauth2_scheme
from app.core.security import get_password_hash
from app.main import app
from app.models import Base
from app.models.admin import EducationContent, ModelFeedback
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
    TaskExecution,
)
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User, UserCounselorBinding

Request = StarletteRequest

# v1.39 R3 RISK-4: autouse mock ObservabilityExporter, 避免 60s 调度干扰测试时长
from unittest.mock import AsyncMock
from unittest.mock import MagicMock as _MagicMock


@pytest.fixture(autouse=True)
def mock_observability_exporter(monkeypatch):
    """v1.39: 自动 mock ObservabilityExporter.start/stop, 避免真实 60s 调度."""
    mock_exporter = _MagicMock()
    mock_exporter.start = AsyncMock()
    mock_exporter.stop = AsyncMock()
    monkeypatch.setattr(
        "app.services.observability_exporter.ObservabilityExporter",
        lambda: mock_exporter,
    )
    return mock_exporter


@pytest.fixture(autouse=True)
def _allow_app_logger_propagate_for_caplog():
    """测试基础设施修复: 让 app logger 临时传播到 root, 使 pytest caplog 可捕获.

    背景: logging_config.py 中 ``app`` logger 配置 ``propagate=False`` 以避免
    root logger 重复打印. 但 pytest 的 ``caplog`` fixture 默认只在 root logger
    上挂载 LogCaptureHandler, 故当 configure_logging() 已被某次 TestClient
    启动调用后, app.* 模块的日志不再进入 caplog, 导致依赖 caplog 断言的测试
    在合并运行时集体失败 (单文件运行时 configure_logging 未触发, 仍走默认 propagate=True).

    本 fixture 在测试期间临时将 propagate 改为 True, 测试结束后恢复原值,
    不影响生产环境日志配置.
    """
    import logging

    app_logger = logging.getLogger("app")
    original_propagate = app_logger.propagate
    app_logger.propagate = True
    try:
        yield
    finally:
        app_logger.propagate = original_propagate


@pytest.fixture(autouse=True)
def _reset_global_executors():
    """每个测试前重置全局线程池/资源，防止前一个 TestClient lifespan shutdown 关闭的资源影响后续测试.

    背景: TestClient 关闭时触发 lifespan shutdown, 调用 ``shutdown_pdf_executor()``
    关闭 ``risk_service._pdf_executor`` 全局线程池. 后续不使用 ``client`` fixture
    的测试 (如直接调用 ``RiskService.export_risk()``) 会因 executor 已关闭而抛
    ``RuntimeError: cannot schedule new futures after shutdown``.
    """
    from concurrent.futures import ThreadPoolExecutor

    try:
        import app.services.risk_service as _rs

        if _rs._pdf_executor._shutdown:
            _rs._pdf_executor = ThreadPoolExecutor(
                max_workers=4, thread_name_prefix="pdf_gen"
            )
    except Exception:
        pass
    # 重置全局 event_bus, 防止跨测试 event loop 的 handler/queue 泄漏
    try:
        from app.core.event_bus import event_bus

        event_bus.reset()
    except Exception:
        pass
    yield


import os as _os
SQLALCHEMY_DATABASE_URL = _os.environ.get(
    "TEST_DATABASE_URL", "sqlite+aiosqlite:///./test_app.db"
)
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, future=True)
SessionFactory = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)
TestingSessionLocal = SessionFactory

CURRENT_USER = {"id": 1, "role": "user", "tenant_id": 1}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="session", autouse=True)
def setup_schema() -> None:
    async def _setup() -> None:
        async with engine.begin() as conn:
            # checkfirst=True: 避免因残留 test_app.db 中表不存在导致 DROP TABLE 报错
            # (场景: 之前运行的 test_app.db 文件残留但 schema 不完整)
            await conn.run_sync(Base.metadata.drop_all, checkfirst=True)
            await conn.run_sync(Base.metadata.create_all)

    run(_setup())


@pytest_asyncio.fixture
def db_connection() -> AsyncConnection:
    async def _connect() -> AsyncConnection:
        conn = await engine.connect()
        await conn.begin()
        return conn

    conn = run(_connect())
    try:
        yield conn
    finally:

        async def _close() -> None:
            await conn.rollback()
            await conn.close()

        run(_close())


@pytest_asyncio.fixture
def db_session(db_connection: AsyncConnection) -> AsyncSession:
    """每个测试独立的数据库 session.

    将 session.commit 替换为 session.flush, 使 SQL 发送到数据库但不提交外层事务.
    外层事务在 db_connection teardown 时 rollback, 确保数据不跨测试泄漏.
    """
    session = SessionFactory(bind=db_connection)
    # Monkey-patch: commit -> flush, 防止提交外层事务
    session.commit = session.flush  # type: ignore[method-assign]

    # 清理可能被 AsyncSessionLocal 直接提交到 SQLite 文件的残留数据
    # (SQLite 延迟事务在首次读取时才获取快照, 无法隔离其他连接的已提交数据)
    # 清理所有 seed 相关表 (FK 反序), 防止多测试共享同一事务时 UNIQUE 冲突.
    from sqlalchemy import text

    async def _cleanup():
        # FK 反序: 先清依赖表, 再清 users
        for tbl in [
            "operation_logs",
            "alert_silences",
            "refresh_token_sessions",
            "client_group_members",
            "client_groups",
            "user_counselor_bindings",
            "intervention_tasks",
            "intervention_plans",
            "intervention_templates",
            "user_data_records",
            "risk_assessments",
            "crisis_events",
            "warnings",
            "users",
        ]:
            try:
                await session.execute(text(f"DELETE FROM {tbl}"))
            except Exception:
                # 表可能不存在 (SQLite schema 差异), 忽略
                pass

    run(_cleanup())
    # flush 让 DELETE 对同一 connection 的其他 session (get_db override) 可见
    run(session.flush())

    try:
        yield session
    finally:
        run(session.close())


@pytest_asyncio.fixture(autouse=True)
def override_db_dependency(db_connection: AsyncConnection, monkeypatch):
    def _make_test_session():
        """创建绑定到测试连接且 commit->flush 的 session."""
        session = SessionFactory(bind=db_connection)
        session.commit = session.flush  # type: ignore[method-assign]
        return session

    async def _override_get_db():
        session = _make_test_session()
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Override AsyncSessionLocal for code that bypasses get_db (e.g., WebSocket endpoint)
    from app.core import database as _db_module
    from app.core import ws as _ws_module

    monkeypatch.setattr(_db_module, "AsyncSessionLocal", _make_test_session)
    monkeypatch.setattr(_ws_module, "AsyncSessionLocal", _make_test_session)

    CURRENT_USER["id"] = 1
    CURRENT_USER["role"] = "user"
    CURRENT_USER["tenant_id"] = 1

    from app.core.rate_limit import limiter

    _original_enabled = getattr(limiter, "_enabled", True)
    limiter.enabled = False
    yield
    limiter.enabled = _original_enabled
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
def override_user_dependency():
    async def _override_get_current_user(
        request: Request,
        token=Depends(oauth2_scheme),
        db=Depends(get_db),
    ) -> User:
        role = CURRENT_USER["role"]
        user_id = CURRENT_USER["id"]
        tenant_id = CURRENT_USER.get("tenant_id", 1)
        return User(
            id=user_id,
            username=f"{role}_tester",
            email=f"{role}@test.com",
            role=role,
            status="active",
            password_hash="x",
            tenant_id=tenant_id,
        )

    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-scoped TestClient.

    背景: 早期为 function-scope, 每个测试创建新 TestClient 触发 lifespan startup
    (加载 ML 模型). 2118+ 测试导致:
    1. Windows 页面文件耗尽 (WinError 1455, torch DLL 加载失败)
    2. model_engine 不支持重复 preload → 第二次 lifespan startup 挂起

    改为 session-scope: lifespan startup 只执行一次, ML 模型只加载一次.
    每测试的数据库隔离由 ``override_db_dependency`` (function-scope autouse)
    通过 ``app.dependency_overrides[get_db]`` 实现, 不依赖 client 重建.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture
def as_role():
    def _set(role: str, user_id: int = 1, tenant_id: int = 1) -> None:
        CURRENT_USER["role"] = role
        CURRENT_USER["id"] = user_id
        CURRENT_USER["tenant_id"] = tenant_id

    return _set


@pytest_asyncio.fixture
def seeded_user_id(db_session: AsyncSession) -> int:
    async def _seed() -> int:
        # 幂等: 同一事务内多测试共享, 避免重复插入 UNIQUE 冲突
        from sqlalchemy import select

        existing = (
            await db_session.execute(select(User).where(User.id == 1))
        ).scalar_one_or_none()
        if existing is not None:
            return 1

        # 使用正确的密码哈希，使登录测试可用
        test_password_hash = get_password_hash("testpass123")
        # P1-E 修复：User 模型新增 email_hash（nullable=False），需在 fixture 中提供
        from app.core.pii_crypto import compute_blind_index

        db_session.add_all(
            [
                User(
                    id=1,
                    username="seed_user",
                    email="seed@test.com",
                    email_hash=compute_blind_index("seed@test.com", "email"),
                    password_hash=test_password_hash,
                    role="user",
                    status="active",
                ),
                User(
                    id=2,
                    username="counselor",
                    email="c@test.com",
                    email_hash=compute_blind_index("c@test.com", "email"),
                    password_hash=test_password_hash,
                    role="counselor",
                    status="active",
                ),
                User(
                    id=3,
                    username="admin",
                    email="a@test.com",
                    email_hash=compute_blind_index("a@test.com", "email"),
                    password_hash=test_password_hash,
                    role="admin",
                    status="active",
                ),
            ]
        )
        await db_session.commit()
        return 1

    return run(_seed())


@pytest.fixture
def user_token() -> str:
    return "test-token"


@pytest.fixture
def auth_headers(user_token: str) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture
def seed_risk_and_content(db_session: AsyncSession, seeded_user_id: int) -> None:
    async def _seed() -> None:
        db_session.add(
            RiskAssessment(
                user_id=seeded_user_id,
                risk_score=78,
                risk_level=3,
                structured_score=78,
                models_used=["mock"],
                risk_factors=[{"feature": "stress_level", "importance": 0.8}],
                assessment_type="structured",
            )
        )
        db_session.add_all(
            [
                EducationContent(
                    title="情绪调节训练",
                    content_type="article",
                    category="emotion",
                    content="x",
                    summary="s",
                    status="active",
                ),
                EducationContent(
                    title="睡眠恢复指导",
                    content_type="audio",
                    category="stress",
                    content="x",
                    summary="s",
                    status="active",
                ),
            ]
        )
        await db_session.commit()

    run(_seed())


@pytest_asyncio.fixture
def seed_intervention_for_user(db_session: AsyncSession, seeded_user_id: int) -> int:
    async def _seed() -> int:
        plan = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="测试计划",
            risk_level=3,
            status="active",
            start_date=date.today(),
            end_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()
        task = InterventionTask(
            plan_id=plan.id,
            task_name="呼吸训练",
            task_type="meditation",
            description="desc",
            schedule="daily",
            duration_minutes=10,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=seeded_user_id,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        await db_session.commit()
        return task.id

    return run(_seed())


@pytest_asyncio.fixture
def seed_counselor_data(db_session: AsyncSession, seeded_user_id: int) -> None:
    async def _seed() -> None:
        db_session.add(
            UserCounselorBinding(
                user_id=1, counselor_id=2, bind_code="B001", status="active"
            )
        )
        db_session.add(
            RiskAssessment(
                user_id=1,
                risk_score=66,
                risk_level=3,
                structured_score=66,
                models_used=["m"],
                risk_factors=[],
                assessment_type="structured",
            )
        )
        await db_session.flush()
        db_session.add(
            WarningNotification(
                user_id=1,
                counselor_id=2,
                current_level=3,
                previous_level=2,
                trigger_reason="risk up",
            )
        )
        await db_session.commit()

    run(_seed())


@pytest_asyncio.fixture
def seed_admin_data(db_session: AsyncSession, seeded_user_id: int) -> None:
    async def _seed() -> None:
        db_session.add(
            InterventionTemplate(
                template_name="模板A",
                applicable_levels=[2, 3],
                task_list=[{"task_name": "a", "task_type": "meditation"}],
                estimated_weeks=4,
                status="active",
            )
        )
        db_session.add(
            ModelFeedback(
                counselor_id=2, user_id=1, assessment_id=None, agreed=True, reason="ok"
            )
        )
        await db_session.commit()

    run(_seed())
