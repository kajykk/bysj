"""「最新风险评估」（``is_latest``）写入的统一入口。

缺陷（集成验证 E2E 复现）:
    PERF-P2-002 的 ``is_latest`` 维护是 check-then-act —— 先把该用户所有
    ``is_latest`` 行置为 False，再 INSERT 一条 True。此前有 3 条保存路径
    （``risk_service_assessment`` / ``user_data_service`` /
    ``api.v1.model_predict._common``），其中 ``_common`` 的 fire-and-forget
    任务使用**独立 session**。并发下两个事务的 UPDATE 互不可见，两条
    ``is_latest=True`` 都会走到唯一索引检查，后提交者撞
    ``uq_risk_assessments_latest``（IntegrityError）。HTTP 响应仍是 200，
    冲突只留在后台日志里，属于典型的「被 200 掩盖的写入失败」。

修复口径:
    写之前先取 PostgreSQL **事务级** advisory lock（namespace 2100，
    key = user_id），把同一用户的「清旧 + 插新」串行化到同一事务区间内；
    锁随 commit / rollback 自动释放，不需要额外清理。namespace 与既有设施
    错开（review_service=1000，canary_manager=2000）。

    仅靠「先清再插」不够——这本来就是原实现，缺的是**跨事务互斥**。

SQLite（开发 / 单测）不支持 advisory lock，且本身是单写者，按
``canary_manager`` / ``review_service`` 的同一口径跳过。
"""

from __future__ import annotations

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import RiskAssessment

#: advisory lock 命名空间。1000=review_task 创建，2000=金丝雀启动，
#: 2100=最新风险评估写入。不同用途必须错开，否则会互相关联到同一把锁。
LATEST_ASSESSMENT_LOCK_NAMESPACE: int = 2100


async def acquire_latest_assessment_lock(
    session: AsyncSession, user_id: int
) -> None:
    """对同一用户的「最新评估」写入取事务级互斥锁。

    PostgreSQL 走 ``pg_advisory_xact_lock``；其它方言（SQLite）直接返回，
    由数据库自身的写串行化兜底。
    """
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :user_id)"),
        {
            "namespace": LATEST_ASSESSMENT_LOCK_NAMESPACE,
            "user_id": int(user_id),
        },
    )


async def save_latest_assessment(
    session: AsyncSession,
    assessment: RiskAssessment,
    *,
    flush: bool = True,
) -> RiskAssessment:
    """把 ``assessment`` 作为该用户的最新一条风险评估写入。

    顺序固定为「取锁 → 清旧 → 插新 → flush」，三步都在调用方的事务内完成：
    调用方 commit 后锁释放，另一并发事务随后才能看到新行并把旧的 True 清掉，
    因此唯一索引不会再被两条 True 同时命中。

    Args:
        session: 调用方事务的 session（不在这里 commit，事务边界归调用方）。
        assessment: 已构造好、``is_latest=True`` 的 ORM 对象。
        flush: 是否立即 flush（默认 True，调用方通常紧接着需要 ``assessment.id``）。

    Returns:
        传入的 ``assessment``（同一实例，已 flush 时带主键）。
    """
    await acquire_latest_assessment_lock(session, assessment.user_id)
    await session.execute(
        update(RiskAssessment)
        .where(
            RiskAssessment.user_id == assessment.user_id,
            RiskAssessment.is_latest.is_(True),
        )
        .values(is_latest=False)
    )
    session.add(assessment)
    if flush:
        await session.flush()
    return assessment
