"""P1-15（F-03）整改闸门：9 个统计卡改后端 SQL 层聚合端点。

判据设计（对齐「先实测再写断言」纪律，防恒绿）：

1. **反截断（核心）**：每种实体种「60 条特征记录（旧，created_at 更早）+
   N 条普通记录（新）」，使特征记录全部落在列表第一页窗口**之外**（列表按
   created_at desc）。此时旧前端口径（分子取窗口内记录、分母取服务端 total）
   必然算错，而聚合端点必须给出全量真值。测试先断言「窗口内确实没有特征
   记录」证明截断场景真实存在，再断言聚合值正确 —— 不是镜像复制前端算法，
   而是钉住「数据条件 + 全量真值」两端。

2. **窗口大小取各列表端点的法定最大 page_size**：本仓 7 个列表端点
   ``le=100``、2 个告警端点 ``le=200``（M-API-3 统一上限）。
   ⚠️ 实测发现（本测试附证）：旧前端对 7 个端点发的是 ``page_size=200``，
   服务端直接 **422**，被卡片空 catch 吞掉 → 这些统计卡**恒显示全 0**，
   比审查报告描述的「分子截断」更严重（只有 alerts/silences 两端真会截断）。

3. **口径一致**：小数据集下聚合值与字面期望值一致（含边界：score 分档
   阈值上下沿、无任务计划记 0、system 角色日志只进 total 不进角色桶）。
4. **权限 / 租户**：错误角色 403；危机事件统计按租户隔离（租户 B 的事件
   不得计入租户 A 的统计）。
5. **路由顺序**：/counselor/users/stats 不得被 /users/{user_id} 吞掉
   （被吞则 FastAPI 把 "stats" 当 int 解析 → 422，本测试即红）。

回退对照：把任一服务层 stats 方法改回「拉全量行在 Python 里 filter」或
把路由删掉，对应测试必须红。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii_crypto import compute_blind_index
from app.models.admin import AlertSilence, OperationLog
from app.models.assessment import (
    PhysiologicalRecord,
    StructuredAssessment,
    TextEntry,
)
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    TaskExecution,
)
from app.models.risk import RiskAssessment, WarningNotification
from app.models.review import CrisisEvent
from app.models.tenant import Tenant
from app.models.user import User, UserCounselorBinding
from tests.conftest import run

# 窗口外（旧）特征记录的时间基准：早于窗口内（新）普通记录
_OLD = datetime(2026, 1, 1, 8, 0, 0)
_NEW = datetime(2026, 10, 1, 8, 0, 0)

# 特征记录数（全部落在窗口外）
_FEATURE = 60
# 普通记录数 = 各端点的法定最大 page_size（7 个端点 le=100，2 个告警端点 le=200）
_WINDOW_100 = 100
_WINDOW_200 = 200

_user_seq = 0


def _make_user(db_session: AsyncSession, **kwargs) -> User:
    """造一个带 email_hash 的用户（users.email_hash 非空且唯一）。"""
    global _user_seq
    _user_seq += 1
    email = f"p1r6_{_user_seq}@test.com"
    return User(
        username=kwargs.pop("username", f"p1r6_{_user_seq}"),
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash="x",
        **kwargs,
    )


def _seed_tenant2_user(db_session: AsyncSession) -> int:
    """幂等种一个租户 2 的用户（危机事件租户隔离用）。"""

    async def _seed() -> int:
        tenant = (
            await db_session.execute(select(Tenant).where(Tenant.id == 2))
        ).scalar_one_or_none()
        if tenant is None:
            db_session.add(
                Tenant(id=2, name="租户二", code="tenant_2_gate", status="active")
            )
            await db_session.flush()
        existing = (
            await db_session.execute(
                select(User).where(User.username == "tenant2_gate_user")
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id
        user = _make_user(
            db_session,
            username="tenant2_gate_user",
            role="user",
            status="active",
            tenant_id=2,
        )
        db_session.add(user)
        await db_session.flush()
        return user.id

    return run(_seed())


# ---------------------------------------------------------------------------
# 1. 用户预警统计：窗口 100，60 条高危全在窗口外
# ---------------------------------------------------------------------------


def _seed_user_warnings(db_session: AsyncSession, user_id: int) -> None:
    async def _seed() -> None:
        rows: list[WarningNotification] = []
        # 60 条高危（旧，窗口外）：15 已处理、25 未读
        for i in range(_FEATURE):
            rows.append(
                WarningNotification(
                    user_id=user_id,
                    current_level=3,
                    previous_level=2,
                    trigger_reason=f"old-high-{i}",
                    is_read=(i >= 25),
                    is_handled=(i < 15),
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        # 100 条低危（新，窗口内）：40 已处理、50 未读
        for i in range(_WINDOW_100):
            rows.append(
                WarningNotification(
                    user_id=user_id,
                    current_level=1,
                    previous_level=1,
                    trigger_reason=f"new-low-{i}",
                    is_read=(i >= 50),
                    is_handled=(i < 40),
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        db_session.add_all(rows)
        await db_session.flush()

    run(_seed())


def test_user_warning_stats_not_truncated_beyond_window(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    _seed_user_warnings(db_session, user_id=seeded_user_id)

    # 先证明截断场景真实存在：窗口（法定最大 page_size=100）内没有任何高危记录
    first_page = client.get(
        "/api/v1/user/warnings?page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 160
    assert len(first_page["items"]) == _WINDOW_100
    assert all(item["risk_level"] != "high" for item in first_page["items"])

    body = client.get("/api/v1/user/warnings/stats").json()["data"]
    # 聚合端点必须是全量真值；且响应是聚合体而非列表
    assert "items" not in body
    assert body["total"] == 160
    assert body["high_risk"] == 60
    assert body["medium_risk"] == 0
    assert body["low_risk"] == 100
    assert body["handled"] == 55
    assert body["unread"] == 75


def test_user_warning_stats_small_dataset_matches_list_semantics(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    async def _seed() -> None:
        db_session.add_all(
            [
                WarningNotification(
                    user_id=seeded_user_id,
                    current_level=3,
                    trigger_reason="a",
                    is_read=False,
                    is_handled=False,
                ),
                WarningNotification(
                    user_id=seeded_user_id,
                    current_level=2,
                    trigger_reason="b",
                    is_read=True,
                    is_handled=True,
                ),
                # current_level=0/4 不计入三档（与前端 normalize 口径一致）
                WarningNotification(
                    user_id=seeded_user_id,
                    current_level=0,
                    trigger_reason="c",
                    is_read=False,
                    is_handled=False,
                ),
                WarningNotification(
                    user_id=seeded_user_id,
                    current_level=4,
                    trigger_reason="d",
                    is_read=True,
                    is_handled=True,
                ),
            ]
        )
        await db_session.flush()

    run(_seed())

    body = client.get("/api/v1/user/warnings/stats").json()["data"]
    assert body == {
        "total": 4,
        "high_risk": 1,
        "medium_risk": 1,
        "low_risk": 0,
        "handled": 2,
        "unread": 2,
    }


def test_user_warning_stats_rejects_counselor_role(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("counselor", 2)
    res = client.get("/api/v1/user/warnings/stats")
    assert res.status_code == 403


def test_old_frontend_approach_page_size_200_is_rejected(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    """旧前端口径的服务端实证：7 个列表端点 page_size 上限 100，发 200 即 422。

    这解释了为什么这些统计卡「恒显示全 0」——422 被卡片空 catch 吞掉。
    钉住此行为，防止有人把统计卡改回 page_size=200 拉列表的老路。
    """
    _seed_user_warnings(db_session, user_id=seeded_user_id)
    res = client.get("/api/v1/user/warnings?page=1&page_size=200")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 2. 用户评估历史统计：窗口 100，60 条高分全在窗口外
# ---------------------------------------------------------------------------


def _seed_user_assessments(db_session: AsyncSession, user_id: int) -> None:
    async def _seed() -> None:
        rows: list[StructuredAssessment] = []
        # 60 条高分（旧，窗口外）：score 70 → high 档
        for i in range(_FEATURE):
            rows.append(
                StructuredAssessment(
                    user_id=user_id,
                    assessment_type="phq9",
                    score=70.0,
                    severity="high",
                    data_payload={},
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        # 100 条低分（新，窗口内）：score 10 → 低于 mild(22)，不进任何档
        for i in range(_WINDOW_100):
            rows.append(
                StructuredAssessment(
                    user_id=user_id,
                    assessment_type="phq9",
                    score=10.0,
                    severity="mild",
                    data_payload={},
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        db_session.add_all(rows)
        # 另种 3 条 text + 2 条 physiological（不计入风险分档）
        for i in range(3):
            db_session.add(
                TextEntry(
                    user_id=user_id,
                    entry_type="diary",
                    content=f"text-{i}",
                    created_at=_NEW + timedelta(minutes=100 + i),
                )
            )
        for i in range(2):
            db_session.add(
                PhysiologicalRecord(
                    user_id=user_id,
                    source="manual",
                    sleep_hours=7.0,
                    recorded_at=_NEW + timedelta(minutes=200 + i),
                )
            )
        await db_session.flush()

    run(_seed())


def test_user_assessment_history_stats_not_truncated_beyond_window(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    _seed_user_assessments(db_session, user_id=seeded_user_id)

    # 窗口内（第一页 100 条结构化）全是 10 分低分记录
    first_page = client.get(
        "/api/v1/user/data/history?type=structured&page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 160
    assert len(first_page["items"]) == _WINDOW_100
    assert all(item["data"]["score"] == 10.0 for item in first_page["items"])

    body = client.get("/api/v1/user/data/history/stats").json()["data"]
    assert "items" not in body
    assert body["total"] == 165
    assert body["structured"] == 160
    assert body["text"] == 3
    assert body["physiological"] == 2
    # 60 条 70 分记录全在窗口外，聚合端点必须计数
    assert body["high_risk"] == 60
    assert body["medium_risk"] == 0
    assert body["low_risk"] == 0


def test_user_assessment_history_stats_buckets_match_thresholds(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    async def _seed() -> None:
        # 分档阈值与前端 summarizeAssessmentHistory 一致：
        # high [62,∞) / medium [42,62) / low [22,42) / 其余不进档
        scores = [62.0, 61.999, 42.0, 41.999, 22.0, 21.999]
        db_session.add_all(
            [
                StructuredAssessment(
                    user_id=seeded_user_id,
                    assessment_type="phq9",
                    score=score,
                    data_payload={},
                )
                for score in scores
            ]
        )
        await db_session.flush()

    run(_seed())

    body = client.get("/api/v1/user/data/history/stats").json()["data"]
    assert body["structured"] == 6
    assert body["high_risk"] == 1  # 62.0
    assert body["medium_risk"] == 2  # 61.999 + 42.0
    assert body["low_risk"] == 2  # 41.999 + 22.0
    assert body["total"] == 6  # 21.999 不进任何档但计 total


# ---------------------------------------------------------------------------
# 3. 用户干预统计：状态计数 + 完成率均值（含无任务计划记 0）
# ---------------------------------------------------------------------------


def _seed_intervention(db_session: AsyncSession, user_id: int) -> None:
    async def _seed() -> None:
        plans: list[InterventionPlan] = []
        # 60 条已完成计划（旧，窗口外）+ 100 条活跃计划（新，窗口内）
        for i in range(_FEATURE):
            plans.append(
                InterventionPlan(
                    user_id=user_id,
                    plan_name=f"old-plan-{i}",
                    risk_level=2,
                    status="completed",
                    start_date=date(2026, 1, 1),
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        for i in range(_WINDOW_100):
            plans.append(
                InterventionPlan(
                    user_id=user_id,
                    plan_name=f"new-plan-{i}",
                    risk_level=2,
                    status="active",
                    start_date=date(2026, 10, 1),
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        db_session.add_all(plans)
        await db_session.flush()

    run(_seed())


def test_intervention_stats_not_truncated_beyond_window(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    _seed_intervention(db_session, user_id=seeded_user_id)

    first_page = client.get(
        "/api/v1/user/intervention/history?page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 160
    assert len(first_page["items"]) == _WINDOW_100
    assert all(item["status"] == "active" for item in first_page["items"])

    body = client.get("/api/v1/user/intervention/stats").json()["data"]
    assert "items" not in body
    assert body["active"] == 100
    assert body["completed"] == 60
    assert body["cancelled"] == 0


def test_intervention_stats_avg_completion_includes_zero_task_plans(
    client: TestClient, db_session: AsyncSession, seeded_user_id: int
) -> None:
    async def _seed() -> None:
        # 计划 A：2 任务全部完成 → 100；计划 B：2 任务完成 1 → 50；
        # 计划 C：无任务 → 0（get_history 的 total_tasks_in_plan==0 分支）。
        # 均值 = (100 + 50 + 0) / 3 = 50
        plan_a = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="A",
            risk_level=1,
            status="active",
            start_date=date(2026, 5, 1),
        )
        plan_b = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="B",
            risk_level=1,
            status="active",
            start_date=date(2026, 5, 1),
        )
        plan_c = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="C",
            risk_level=1,
            status="active",
            start_date=date(2026, 5, 1),
        )
        db_session.add_all([plan_a, plan_b, plan_c])
        await db_session.flush()
        for plan in (plan_a, plan_b):
            for n in range(2):
                db_session.add(
                    InterventionTask(
                        plan_id=plan.id,
                        task_name=f"task-{plan.plan_name}-{n}",
                        task_type="exercise",
                    )
                )
        await db_session.flush()
        tasks = (
            (
                await db_session.execute(
                    select(InterventionTask).where(
                        InterventionTask.plan_id.in_([plan_a.id, plan_b.id])
                    )
                )
            )
            .scalars()
            .all()
        )
        for idx, task in enumerate(tasks):
            # A 的 2 个任务全完成；B 的 2 个任务完成 1 个
            completed = task.plan_id == plan_a.id or idx % 2 == 0
            db_session.add(
                TaskExecution(
                    task_id=task.id,
                    user_id=seeded_user_id,
                    scheduled_date=date(2026, 5, 2),
                    status="completed" if completed else "pending",
                )
            )
        await db_session.flush()

    run(_seed())

    body = client.get("/api/v1/user/intervention/stats").json()["data"]
    assert body["active"] == 3
    assert body["avg_completion"] == 50


# ---------------------------------------------------------------------------
# 4. 咨询师预警统计：按 counselor_id 隔离 + 反截断
# ---------------------------------------------------------------------------


def _seed_counselor_warnings(db_session: AsyncSession) -> None:
    async def _seed() -> None:
        rows: list[WarningNotification] = []
        # 咨询师 2 的 60 条未处理高危（旧，窗口外）
        for i in range(_FEATURE):
            rows.append(
                WarningNotification(
                    user_id=1,
                    counselor_id=2,
                    current_level=3,
                    trigger_reason=f"old-{i}",
                    is_handled=False,
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        # 咨询师 2 的 100 条已处理（新，窗口内）
        for i in range(_WINDOW_100):
            rows.append(
                WarningNotification(
                    user_id=1,
                    counselor_id=2,
                    current_level=1,
                    trigger_reason=f"new-{i}",
                    is_handled=True,
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        # 咨询师 3 的 10 条（必须被 counselor_id 隔离排除；时间最新，
        # 若统计漏了 counselor_id 过滤会第一个污染窗口断言）
        for i in range(10):
            rows.append(
                WarningNotification(
                    user_id=1,
                    counselor_id=3,
                    current_level=3,
                    trigger_reason=f"other-counselor-{i}",
                    is_handled=False,
                    created_at=_NEW + timedelta(minutes=500 + i),
                )
            )
        db_session.add_all(rows)
        await db_session.flush()

    run(_seed())


def test_counselor_warning_stats_scoped_and_not_truncated(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("counselor", 2)
    _seed_counselor_warnings(db_session)

    first_page = client.get(
        "/api/v1/counselor/warnings?page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 160
    assert all(item["status"] != "pending" for item in first_page["items"])

    body = client.get("/api/v1/counselor/warnings/stats").json()["data"]
    assert body == {
        "total": 160,
        "unhandled": 60,
        "handled": 100,
        "high_risk": 60,
        "medium_risk": 0,
        "low_risk": 100,
    }


def test_counselor_warning_stats_rejects_user_role(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/counselor/warnings/stats")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 5. 咨询师用户分布统计：路由顺序 + 反截断 + 无评估落 none 档
# ---------------------------------------------------------------------------


def _seed_counselor_users(db_session: AsyncSession) -> None:
    async def _seed() -> None:
        # 60 个高危用户（旧绑定）+ 100 个无评估用户（新绑定），全部绑定到咨询师 2
        for i in range(_FEATURE):
            user = _make_user(
                db_session,
                username=f"cu_old_{i}",
                role="user",
                status="active",
                tenant_id=1,
            )
            db_session.add(user)
            await db_session.flush()
            db_session.add(
                UserCounselorBinding(
                    counselor_id=2,
                    user_id=user.id,
                    bind_code=f"BCO{i:04d}",
                    status="active",
                )
            )
            db_session.add(
                RiskAssessment(
                    user_id=user.id, risk_score=80.0, risk_level=3, is_latest=True
                )
            )
        for i in range(_WINDOW_100):
            user = _make_user(
                db_session,
                username=f"cu_new_{i}",
                role="user",
                status="active",
                tenant_id=1,
            )
            db_session.add(user)
            await db_session.flush()
            db_session.add(
                UserCounselorBinding(
                    counselor_id=2,
                    user_id=user.id,
                    bind_code=f"BCN{i:04d}",
                    status="active",
                )
            )
        await db_session.flush()

    run(_seed())


def test_counselor_user_stats_not_shadowed_by_dynamic_route(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    """路由顺序闸门：/users/stats 不得被 /users/{user_id} 吞掉（被吞 → 422）。"""
    as_role("counselor", 2)
    res = client.get("/api/v1/counselor/users/stats")
    assert res.status_code == 200
    assert "items" not in res.json()["data"]


def test_counselor_user_stats_distribution_not_truncated(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("counselor", 2)
    _seed_counselor_users(db_session)

    # list_my_users 按 User.id desc，窗口内（新绑定）全部是无评估用户
    first_page = client.get(
        "/api/v1/counselor/users?page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 160
    assert all(item["latest_risk_level"] is None for item in first_page["items"])

    body = client.get("/api/v1/counselor/users/stats").json()["data"]
    assert body["total"] == 160
    assert body["high"] == 60
    assert body["none"] == 100  # 100 个无评估新用户
    assert body["low"] == 0
    assert body["medium"] == 0
    assert body["critical"] == 0


def test_counselor_user_stats_small_dataset_buckets(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("counselor", 2)

    async def _seed() -> None:
        levels = [0, 1, 2, 3, 4]
        for idx, level in enumerate(levels):
            user = _make_user(
                db_session,
                username=f"cu_small_{idx}",
                role="user",
                status="active",
                tenant_id=1,
            )
            db_session.add(user)
            await db_session.flush()
            db_session.add(
                UserCounselorBinding(
                    counselor_id=2,
                    user_id=user.id,
                    bind_code=f"BCS{idx:04d}",
                    status="active",
                )
            )
            db_session.add(
                RiskAssessment(
                    user_id=user.id,
                    risk_score=float(level * 20),
                    risk_level=level,
                    is_latest=True,
                )
            )
        await db_session.flush()

    run(_seed())

    body = client.get("/api/v1/counselor/users/stats").json()["data"]
    assert body == {
        "total": 5,
        "none": 1,
        "low": 1,
        "medium": 1,
        "high": 1,
        "critical": 1,
    }


# ---------------------------------------------------------------------------
# 6. 危机事件统计：租户隔离 + 反截断
# ---------------------------------------------------------------------------


def _seed_crisis_events(db_session: AsyncSession, tenant1_user_id: int, tenant2_user_id: int) -> None:
    async def _seed() -> None:
        rows: list[CrisisEvent] = []
        # 租户 1：60 条 escalated（旧，窗口外）+ 100 条 detected（新，窗口内）
        for i in range(_FEATURE):
            rows.append(
                CrisisEvent(
                    user_id=tenant1_user_id,
                    trigger_source="text",
                    crisis_keywords="[]",
                    status="escalated",
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        for i in range(_WINDOW_100):
            rows.append(
                CrisisEvent(
                    user_id=tenant1_user_id,
                    trigger_source="text",
                    crisis_keywords="[]",
                    status="detected",
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        # 租户 2：30 条 resolved（必须被租户隔离排除）
        for i in range(30):
            rows.append(
                CrisisEvent(
                    user_id=tenant2_user_id,
                    trigger_source="text",
                    crisis_keywords="[]",
                    status="resolved",
                    created_at=_NEW + timedelta(minutes=900 + i),
                )
            )
        db_session.add_all(rows)
        await db_session.flush()

    run(_seed())


def test_crisis_event_stats_tenant_isolated_and_not_truncated(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("admin", 3, tenant_id=1)
    # 危机事件无 tenant_id 列，列表与统计都经 JOIN User.tenant_id 推导租户；
    # seed 用户 1/2/3 的 tenant_id 均为 NULL，会被租户 1 的过滤条件排除，
    # 故必须显式造 tenant_id=1 / tenant_id=2 的用户再种事件。
    tenant2_user_id = _seed_tenant2_user(db_session)
    tenant1_user_id = _make_user(
        db_session,
        username="crisis_tenant1_gate_user",
        role="user",
        status="active",
        tenant_id=1,
    )

    async def _add_tenant1_user() -> int:
        db_session.add(tenant1_user_id)
        await db_session.flush()
        return tenant1_user_id.id

    tenant1_user_id = run(_add_tenant1_user())
    _seed_crisis_events(db_session, tenant1_user_id, tenant2_user_id)

    first_page = client.get(
        "/api/v1/reviews/crisis-events?page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 160
    assert all(item["status"] == "detected" for item in first_page["items"])

    body = client.get("/api/v1/reviews/crisis-events/stats").json()["data"]
    assert "items" not in body
    # 只统计租户 1 的 160 条；租户 2 的 30 条 resolved 不得计入
    assert body["total"] == 160
    assert body["escalated"] == 60
    assert body["detected"] == 100
    assert body["reviewed"] == 0
    assert body["resolved"] == 0


def test_crisis_event_stats_rejects_user_role(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/reviews/crisis-events/stats")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 7. 告警历史统计：severity JSON 匹配 + 反截断（该端点 page_size 上限 200）
# ---------------------------------------------------------------------------


def _alert_log(severity: str, action_type: str, created_at: datetime) -> OperationLog:
    return OperationLog(
        operator_id=None,
        operator_role="system",
        action_type=action_type,
        target_type="alert",
        target_id=None,
        detail=f'{{"rule": "r", "severity": "{severity}", "message": "m"}}',
        created_at=created_at,
    )


def _seed_alert_history(db_session: AsyncSession) -> None:
    async def _seed() -> None:
        rows: list[OperationLog] = []
        # 60 条 P0 firing（旧，窗口外）
        for i in range(_FEATURE):
            rows.append(
                _alert_log("P0", "alert_fired", _OLD + timedelta(minutes=i))
            )
        # 200 条 P1 resolved（新，窗口内）
        for i in range(_WINDOW_200):
            rows.append(
                _alert_log("P1", "alert_resolved", _NEW + timedelta(minutes=i))
            )
        db_session.add_all(rows)
        await db_session.flush()

    run(_seed())


def test_alert_history_stats_severity_and_status_not_truncated(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("admin", 3)
    _seed_alert_history(db_session)

    first_page = client.get(
        "/api/v1/alerts/history?page=1&page_size=200"
    ).json()["data"]
    assert first_page["total"] == 260
    assert all(item["severity"] == "P1" for item in first_page["items"])

    body = client.get("/api/v1/alerts/history/stats").json()["data"]
    assert "items" not in body
    assert body["total"] == 260
    assert body["p0"] == 60
    assert body["p1"] == 200
    assert body["p2"] == 0
    assert body["firing"] == 60
    assert body["resolved"] == 200


def test_alert_history_stats_rejects_counselor_role(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("counselor", 2)
    res = client.get("/api/v1/alerts/history/stats")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 8. 静默规则统计：反截断（该端点 page_size 上限 200）
# ---------------------------------------------------------------------------


def _seed_silences(db_session: AsyncSession) -> None:
    async def _seed() -> None:
        rows: list[AlertSilence] = []
        # 60 条生效（旧，窗口外）+ 200 条停用（新，窗口内）
        for i in range(_FEATURE):
            rows.append(
                AlertSilence(
                    name=f"old-{i}",
                    matcher={"alertname": "x"},
                    starts_at=_OLD,
                    ends_at=_OLD + timedelta(days=1),
                    is_active=True,
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        for i in range(_WINDOW_200):
            rows.append(
                AlertSilence(
                    name=f"new-{i}",
                    matcher={"alertname": "x"},
                    starts_at=_NEW,
                    ends_at=_NEW + timedelta(days=1),
                    is_active=False,
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        db_session.add_all(rows)
        await db_session.flush()

    run(_seed())


def test_silence_stats_not_truncated(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("admin", 3)
    _seed_silences(db_session)

    first_page = client.get(
        "/api/v1/alerts/silences?page=1&page_size=200"
    ).json()["data"]
    assert first_page["total"] == 260
    assert all(item["is_active"] is False for item in first_page["items"])

    body = client.get("/api/v1/alerts/silences/stats").json()["data"]
    assert "items" not in body
    assert body == {"total": 260, "active": 60, "inactive": 200}


# ---------------------------------------------------------------------------
# 9. 操作日志统计：角色分桶 + system 只进 total + 反截断
# ---------------------------------------------------------------------------


def _seed_operation_logs(db_session: AsyncSession) -> None:
    async def _seed() -> None:
        rows: list[OperationLog] = []
        # 60 条 user 角色（旧，窗口外）
        for i in range(_FEATURE):
            rows.append(
                OperationLog(
                    operator_id=1,
                    operator_role="user",
                    action_type="login",
                    created_at=_OLD + timedelta(minutes=i),
                )
            )
        # 100 条 counselor 角色（新，窗口内）
        for i in range(_WINDOW_100):
            rows.append(
                OperationLog(
                    operator_id=2,
                    operator_role="counselor",
                    action_type="counselor_view_user_list",
                    created_at=_NEW + timedelta(minutes=i),
                )
            )
        # 10 条 system 角色（只进 total，不进任何角色桶；时间最新，
        # 会占窗口前 10 条，故窗口断言用「无 user 角色」而非「全 counselor」）
        for i in range(10):
            rows.append(
                OperationLog(
                    operator_id=None,
                    operator_role="system",
                    action_type="alert_fired",
                    created_at=_NEW + timedelta(minutes=800 + i),
                )
            )
        db_session.add_all(rows)
        await db_session.flush()

    run(_seed())


def test_operation_log_stats_roles_and_system_rows(
    client: TestClient, db_session: AsyncSession, as_role
) -> None:
    as_role("admin", 3)
    _seed_operation_logs(db_session)

    first_page = client.get(
        "/api/v1/admin/operation-logs?page=1&page_size=100"
    ).json()["data"]
    assert first_page["total"] == 170
    assert all(item["operator_role"] != "user" for item in first_page["items"])

    body = client.get("/api/v1/admin/operation-logs/stats").json()["data"]
    assert "items" not in body
    assert body == {
        "total": 170,
        "user": 60,
        "counselor": 100,
        "admin": 0,
        "super_admin": 0,
    }
