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
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine

# pytest-asyncio 配置
pytestmark = pytest.mark.asyncio(loop_scope="function")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
# P1-SEC-001 修复：为测试环境提供 PII 加密密钥（仅用于单元测试，非生产密钥）
os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-only-not-for-production")

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import get_password_hash
from app.main import app
from app.models import Base
from app.models.admin import EducationContent, ModelFeedback
from app.models.intervention import InterventionPlan, InterventionTask, InterventionTemplate, TaskExecution
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User, UserCounselorBinding
from starlette.requests import Request as StarletteRequest
Request = StarletteRequest

# v1.39 R3 RISK-4: autouse mock ObservabilityExporter, 避免 60s 调度干扰测试时长
from unittest.mock import AsyncMock, MagicMock as _MagicMock


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

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test_app.db"
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, future=True)
SessionFactory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
TestingSessionLocal = SessionFactory

CURRENT_USER = {"id": 1, "role": "user"}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="session", autouse=True)
def setup_schema() -> None:
    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
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
    session = SessionFactory(bind=db_connection)
    try:
        yield session
    finally:
        run(session.close())


@pytest_asyncio.fixture(autouse=True)
def override_db_dependency(db_connection: AsyncConnection):
    async def _override_get_db():
        session = SessionFactory(bind=db_connection)
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_db] = _override_get_db
    CURRENT_USER["id"] = 1
    CURRENT_USER["role"] = "user"

    from app.core.rate_limit import limiter
    _original_enabled = getattr(limiter, "_enabled", True)
    limiter.enabled = False
    yield
    limiter.enabled = _original_enabled
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
def override_user_dependency():
    async def _override_get_current_user() -> User:
        role = CURRENT_USER["role"]
        user_id = CURRENT_USER["id"]
        return User(
            id=user_id,
            username=f"{role}_tester",
            email=f"{role}@test.com",
            role=role,
            status="active",
            password_hash="x",
        )

    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def as_role():
    def _set(role: str, user_id: int = 1) -> None:
        CURRENT_USER["role"] = role
        CURRENT_USER["id"] = user_id

    return _set


@pytest_asyncio.fixture
def seeded_user_id(db_session: AsyncSession) -> int:
    async def _seed() -> int:
        # 使用正确的密码哈希，使登录测试可用
        test_password_hash = get_password_hash("testpass123")
        # P1-E 修复：User 模型新增 email_hash（nullable=False），需在 fixture 中提供
        from app.core.pii_crypto import compute_blind_index
        db_session.add_all(
            [
                User(id=1, username="seed_user", email="seed@test.com", email_hash=compute_blind_index("seed@test.com", "email"), password_hash=test_password_hash, role="user", status="active"),
                User(id=2, username="counselor", email="c@test.com", email_hash=compute_blind_index("c@test.com", "email"), password_hash=test_password_hash, role="counselor", status="active"),
                User(id=3, username="admin", email="a@test.com", email_hash=compute_blind_index("a@test.com", "email"), password_hash=test_password_hash, role="admin", status="active"),
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
                EducationContent(title="情绪调节训练", content_type="article", category="emotion", content="x", summary="s", status="active"),
                EducationContent(title="睡眠恢复指导", content_type="audio", category="stress", content="x", summary="s", status="active"),
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
        db_session.add(TaskExecution(task_id=task.id, user_id=seeded_user_id, scheduled_date=date.today(), status="pending"))
        await db_session.commit()
        return task.id

    return run(_seed())


@pytest_asyncio.fixture
def seed_counselor_data(db_session: AsyncSession, seeded_user_id: int) -> None:
    async def _seed() -> None:
        db_session.add(UserCounselorBinding(user_id=1, counselor_id=2, bind_code="B001", status="active"))
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
        db_session.add(WarningNotification(user_id=1, counselor_id=2, current_level=3, previous_level=2, trigger_reason="risk up"))
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
        db_session.add(ModelFeedback(counselor_id=2, user_id=1, assessment_id=None, agreed=True, reason="ok"))
        await db_session.commit()

    run(_seed())
