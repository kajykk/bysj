from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import Select, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.contracts import (
    DEFAULT_TENANT_ID,
    USER_ROLE_ADMIN,
    USER_ROLE_COUNSELOR,
    USER_ROLE_SUPER_ADMIN,
)
from app.core.degradation import record_silent_degradation
from app.core.event_bus import event_bus
from app.core.tenant_query import tenant_scoped_filter, user_tenant_scoped_query
from app.models.review import CrisisEvent, ReviewTask
from app.models.user import User
from app.schemas.review import (
    CrisisEventCreate,
    CrisisEventFilter,
    ReviewStats,
    ReviewTaskCreate,
    ReviewTaskFilter,
    ReviewTaskListResponse,
    ReviewTaskResponse,
)

logger = logging.getLogger(__name__)

# M-Svc-8 修复：危机事件处理 action 白名单，防止任意字符串写入 handled_action 字段
_ALLOWED_CRISIS_ACTIONS: frozenset[str] = frozenset({"escalate", "notify_counselor", "emergency_contact", "resolved"})

# ISS-072 修复：危机事件状态机
# detected → reviewed → escalated → resolved
# - reviewed → reviewed：允许追加处理动作（如再通知其他咨询师）
# - escalated → reviewed：允许降级回处理态（误升级修正）
# - resolved 为终态，不可再转换
_CRISIS_STATE_TRANSITIONS: dict[str, frozenset[str]] = {
    "detected": frozenset({"reviewed", "escalated", "resolved"}),
    "reviewed": frozenset({"reviewed", "escalated", "resolved"}),
    "escalated": frozenset({"reviewed", "resolved"}),
    "resolved": frozenset(),  # 终态
}


def _parse_crisis_keywords(raw: str | None, event_id: int | None = None) -> list:
    """容错解析 ``CrisisEvent.crisis_keywords``（JSON 数组文本列）。

    REV-2026-10-20 (S2)：该列历史上可能残留非 JSON 文本（旧版匿名化写入
    ``[ANONYMIZED]``）。原实现直接 ``json.loads`` 且无 try/except，
    单条坏数据会让整页危机事件抛 JSONDecodeError（列表推导一起失败）。
    这里个别坏行降级为 ``[]`` 并计数，不让一行业务数据打挂整页。

    注意：这不替代写入侧修复（gdpr_service_anonymize 已改为写合法 JSON），
    只保证存量脏数据可读、可清理。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        record_silent_degradation("services.review_service.crisis_keywords_parse")
        logger.warning(
            "crisis_event.crisis_keywords.invalid_json event_id=%s raw_prefix=%r",
            event_id,
            raw[:32],
        )
        return []
    if not isinstance(parsed, list):
        record_silent_degradation("services.review_service.crisis_keywords_not_list")
        logger.warning(
            "crisis_event.crisis_keywords.not_list event_id=%s type=%s",
            event_id,
            type(parsed).__name__,
        )
        return []
    return parsed


class ReviewStateConflict(ValueError):
    """复核任务状态冲突（并发已被他人处置 / 对终态再次操作）。

    M7 修复（ROUND_18）：沿用 ``ValueError`` 的捕获约定（既有调用方与用例都按
    ``ValueError`` 处理），但独立成类，供 API 层映射 409 —— "你读到的是旧状态"
    与"参数不合法"对客户端是两种处置，混用 400 会让调用方重试而不是重取。
    """


def _locked_review_stmt(review_id: int) -> Select:
    """按主键取复核任务并加 ``FOR UPDATE``（M7 行锁）。

    与 ``assign_review`` 同构：租户归属先由同事务的
    ``_ensure_review_in_tenant`` 校验，故这里不 JOIN users ——
    ``JOIN + FOR UPDATE`` 会在 PostgreSQL 上连带锁住 users 行，把复核处置
    变成用户表上的锁竞争（而 SQLite 下 FOR UPDATE 本就被忽略）。

    独立成模块级函数，是为了让闸门能编译**真实语句**并断言其带行锁，
    而不是在测试里重抄一份 SELECT。
    """
    return (
        select(ReviewTask)
        .where(ReviewTask.id == review_id)
        .with_for_update()
        .execution_options(tenant_exempt="tenant_checked_upstream_same_transaction")
    )


class ReviewService:
    """复核任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review_task(self, data: ReviewTaskCreate) -> ReviewTask:
        """根据预测结果创建复核任务"""
        # H-12 修复：使用 PostgreSQL Advisory Lock 防止并发竞态
        # 对 user_id 加事务级锁，确保同一用户的复核任务创建串行化
        # namespace=1000 表示 review_task 创建锁，避免与其他 advisory lock 冲突
        # SQLite 不支持 advisory lock，开发环境跳过（单线程无并发竞态）
        bind = self.db.bind
        if bind is not None and bind.dialect.name == "postgresql":
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(1000, :user_id)"),
                {"user_id": data.user_id},
            )

        # 检查是否已存在同一用户的 pending 复核任务
        # 使用 first() 而非 scalar_one_or_none()，避免多条 pending 记录时抛 MultipleResultsFound
        # P2-31：本查询按 user_id 幂等去重（系统内部写路径前置检查，不向租户用户
        # 返回数据），不经租户推导 —— 显式声明豁免而非默默裸查，理由已登记在
        # app/core/tenant_guard.py 的 EXEMPTION_REGISTRY。
        existing = await self.db.execute(
            select(ReviewTask)
            .where(
                ReviewTask.user_id == data.user_id,
                ReviewTask.status == "pending",
            )
            .limit(1)
            .execution_options(tenant_exempt="system_internal_idempotency_check")
        )
        existing_task = existing.scalars().first()

        if existing_task:
            # 更新现有任务
            existing_task.risk_level = data.risk_level
            existing_task.risk_score = data.risk_score
            existing_task.review_triggers = json.dumps(data.review_triggers)
            existing_task.crisis_override = data.crisis_override
            existing_task.priority = data.priority.value
            # ISS-041 修复：统一 naive UTC，避免 aware/naive datetime 混用
            existing_task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.db.commit()
            await self.db.refresh(existing_task)
            return existing_task

        # 创建新任务
        task = ReviewTask(
            user_id=data.user_id,
            risk_report_id=data.risk_report_id,
            risk_level=data.risk_level,
            risk_score=data.risk_score,
            review_triggers=json.dumps(data.review_triggers),
            crisis_override=data.crisis_override,
            status="pending",
            priority=data.priority.value,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        # R-C: 发布 review.submitted 事件到 EventBus, 实时更新 Prometheus 指标.
        # 仅在新建 ReviewTask 成功后发布; 更新已有任务 (existing_task 路径) 不发布.
        # 事件发布非阻塞 (put_nowait), 不影响业务主流程.
        try:
            await event_bus.publish(
                "review.submitted",
                {
                    "review_id": task.id,
                    "user_id": task.user_id,
                    "risk_level": task.risk_level,
                    "risk_score": task.risk_score,
                    "priority": task.priority,
                    "crisis_override": bool(task.crisis_override),
                    # ISS-041 修复：统一 naive UTC
                    "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                },
            )
        except Exception:
            # EventBus 发布失败不应影响业务主流程
            logger.warning("Failed to publish review.submitted event", exc_info=True)

        return task

    # P0-FIX-2026-10-11: ``review_tasks`` / ``crisis_events`` 两张表**都没有
    # tenant_id 列**（见 models/review.py），租户归属只能沿 ``user_id`` 关联到
    # ``users.tenant_id`` 推导。此前本服务所有读/写端点都是裸 ``select(...)``
    # 按主键取记录，意味着：**只要知道一个 id，任何租户的咨询师都能读写他校
    # 学生的危机事件与复核任务**（危机事件含 input_summary 自述原文与
    # crisis_keywords 自伤关键词，属最高敏感级数据）。
    #
    # 租户隔离必须落在**服务层**而不是 API 层：API 层已有若干 owner 校验，
    # 但那只挡「同租户内的水平越权」，挡不住跨租户；且 assign/resolve/
    # escalate 三条链路最终都经过 ``get_review_by_id``，在服务层加一道即可
    # 覆盖全部。因此这里把 ``tenant_id`` 设为**必填**（关键字参数，无默认值），
    # 漏传直接 TypeError，而不是静默返回跨租户数据。

    async def get_reviews(
        self,
        filter_data: ReviewTaskFilter,
        *,
        tenant_id: int,
    ) -> ReviewTaskListResponse:
        """查询复核任务列表（**必须**限定租户范围）"""
        # P2-31：review_tasks 无 tenant_id 列，统一走 user_tenant_scoped_query
        # （JOIN users 推导租户的 SSOT 构造）；裸 select(ReviewTask) 会被
        # 执行层闸门 app/core/tenant_guard 直接拦下。
        query = user_tenant_scoped_query(ReviewTask, tenant_id)

        if filter_data.status:
            query = query.where(ReviewTask.status == filter_data.status.value)
        if filter_data.priority:
            query = query.where(ReviewTask.priority == filter_data.priority.value)
        if filter_data.assigned_to:
            query = query.where(ReviewTask.assigned_to == filter_data.assigned_to)
        if filter_data.user_id:
            query = query.where(ReviewTask.user_id == filter_data.user_id)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(desc(ReviewTask.created_at))
        query = query.offset((filter_data.page - 1) * filter_data.page_size)
        query = query.limit(filter_data.page_size)

        result = await self.db.execute(query)
        tasks = result.scalars().all()

        return ReviewTaskListResponse(
            items=[self.to_response(t) for t in tasks],
            total=total,
            page=filter_data.page,
            page_size=filter_data.page_size,
        )

    async def get_review_by_id(
        self, review_id: int, *, tenant_id: int
    ) -> ReviewTask | None:
        """根据 ID 获取复核任务（**必须**限定租户范围）。

        P0-FIX-2026-10-11：跨租户返回 None，调用方按 404 处理，
        从而不泄露「该 id 在别的租户存在」这一事实。
        """
        stmt = user_tenant_scoped_query(ReviewTask, tenant_id).where(
            ReviewTask.id == review_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_review_in_tenant(self, review_id: int, tenant_id: int) -> None:
        """P0-FIX-2026-10-11：校验复核任务属于当前租户，否则抛 ValueError。

        与 ``get_review_by_id`` 的区别：这里要**响亮失败**并区分「不存在」与
        「跨租户」，供写操作（assign）使用；读操作用返回 None 的版本以免
        泄露 id 是否存在于他租户。
        """
        stmt = (
            select(ReviewTask.id)
            .join(User, User.id == ReviewTask.user_id)
            .where(
                ReviewTask.id == review_id,
                tenant_scoped_filter(User, tenant_id),
            )
        )
        if (await self.db.execute(stmt)).scalar_one_or_none() is None:
            logger.warning(
                "跨租户访问复核任务被拒绝: review_id=%s tenant_id=%s",
                review_id,
                tenant_id,
            )
            raise ValueError(f"Review task {review_id} not found")

    async def _ensure_assignee(self, assignee_id: int, tenant_id: int) -> User:
        """校验复核受派人（M8）。

        四道判据：**存在**、**同租户**、**有处置角色**、**未停用**。
        ``admin / super_admin`` 在允许集合内 —— 分配端点文档写明管理员
        "不传 assignee 则接管给自己"，若只认 counselor，这条既有行为会 400。
        普通用户（``role=user``）被拒：任务一旦转 in_review，普通用户既无
        ``review.handle`` 权限、也不在咨询师列表里，任务就锁死了。

        抛 ``ValueError``（400 语义）：这是"你给的参数不成立"，不是状态冲突。
        """
        assignee = await self.db.get(User, assignee_id)
        if assignee is None:
            raise ValueError(f"受派的咨询师不存在: {assignee_id}")
        if (assignee.tenant_id or DEFAULT_TENANT_ID) != (
            tenant_id or DEFAULT_TENANT_ID
        ):
            logger.warning(
                "跨租户分配复核任务被拒绝: assignee_id=%s assignee_tenant=%s tenant_id=%s",
                assignee_id,
                assignee.tenant_id,
                tenant_id,
            )
            raise ValueError("受派的咨询师不属于当前租户")
        if assignee.role not in {
            USER_ROLE_COUNSELOR,
            USER_ROLE_ADMIN,
            USER_ROLE_SUPER_ADMIN,
        }:
            raise ValueError("受派人不具备处置复核任务的角色")
        if assignee.status != "active":
            raise ValueError("受派的咨询师已停用")
        return assignee

    async def assign_review(
        self, review_id: int, counselor_id: int, *, tenant_id: int
    ) -> ReviewTask:
        """分配复核任务给咨询师（**必须**限定租户范围）"""
        # P0-FIX-2026-10-11：先做租户归属校验。不把它并进下面的
        # ``with_for_update()`` 查询，是因为 JOIN + FOR UPDATE 会在 Postgres 上
        # 连带锁住 users 行（增加锁竞争），且 SQLite 下 FOR UPDATE 本就被忽略。
        # 租户归属不随并发变化，先校验再按主键加锁是安全的。
        await self._ensure_review_in_tenant(review_id, tenant_id)
        # M8 修复（ROUND_18）：受派人必须真实存在、同租户、有处置角色。
        # 原实现直接 ``task.assigned_to = counselor_id`` ⇒ 管理员可把危机复核
        # 分配给不存在的 id / 普通用户 / 他租户咨询师；任务随即变 in_review，
        # 而合法咨询师按租户 JOIN 看不到它 —— 危机复核被锁进无人可见的状态。
        await self._ensure_assignee(counselor_id, tenant_id)

        # ISS-061 修复：使用 with_for_update() 行级锁，防止并发分配同一复核任务
        # P2-31：本语句按主键加锁取行，租户归属由上方同事务的
        # _ensure_review_in_tenant 保障（user_id 不可变，归属不随并发变化）——
        # 不把 JOIN 并进 FOR UPDATE 是为避免 Postgres 连带锁 users 行。
        # 豁免理由已登记（tenant_checked_upstream_same_transaction）。
        result = await self.db.execute(
            select(ReviewTask)
            .where(ReviewTask.id == review_id)
            .with_for_update()
            .execution_options(tenant_exempt="tenant_checked_upstream_same_transaction")
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status != "pending":
            raise ValueError(f"Cannot assign review with status {task.status}")

        task.assigned_to = counselor_id
        task.status = "in_review"
        # ISS-041 修复：统一 naive UTC
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def resolve_review(
        self,
        review_id: int,
        counselor_id: int,
        resolution_note: str,
        *,
        is_admin: bool = False,
        tenant_id: int,
        request: Request | None = None,
    ) -> ReviewTask:
        """处理复核任务（**必须**限定租户范围）。

        M7 修复（ROUND_18），三处补齐：

        1. **行锁**：写路径与 ``assign_review`` 同构 —— 先同事务校验租户归属，
           再按主键 ``FOR UPDATE`` 取行。原实现是普通 SELECT，两个并发请求都能
           通过 ``status in (pending, in_review)``，后提交者静默覆盖
           ``resolution_note / resolved_by``，第一份临床处置结论与处置人永久丢失。
        2. **审计**：处置结论落 ``operation_logs``（``review.resolved``）。原实现
           是本服务里唯一不写审计的写操作（assign / escalate / 危机事件都写了）。
           审计只记 ``previous_status`` 与备注**长度** —— 处置备注是临床内容，
           不复制进审计表，避免二次扩散。
        3. **状态冲突**：对终态再操作抛 ``ReviewStateConflict``（API 映射 409），
           与 400 参数错误区分开。
        """
        await self._ensure_review_in_tenant(review_id, tenant_id)

        task = (await self.db.execute(_locked_review_stmt(review_id))).scalar_one_or_none()
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status not in ["pending", "in_review"]:
            raise ReviewStateConflict(
                f"Cannot resolve review with status {task.status}"
            )

        # P1-SEC-007 修复：越权检查 - 仅分配的咨询师或管理员可处理
        if not is_admin and task.assigned_to is not None and task.assigned_to != counselor_id:
            raise ValueError("无权处理此复核任务：任务已分配给其他咨询师")

        previous_status = task.status
        task.resolved_by = counselor_id
        task.resolution_note = resolution_note
        task.status = "resolved"
        # ISS-041 修复：统一 naive UTC
        task.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await record_audit(
            self.db,
            actor_id=counselor_id,
            actor_role=USER_ROLE_ADMIN if is_admin else USER_ROLE_COUNSELOR,
            action="review.resolved",
            target_type="review_task",
            target_id=review_id,
            detail={
                "resolved_by": counselor_id,
                "previous_status": previous_status,
                # 只记长度，不落处置备注原文（临床内容不进审计表）
                "resolution_note_chars": len(resolution_note or ""),
            },
            request=request,
            tenant_id=tenant_id,
        )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def escalate_review(
        self,
        review_id: int,
        counselor_id: int,
        reason: str,
        *,
        is_admin: bool = False,
        tenant_id: int,
        # P2-33 第六批：审计上下文由调用方穿入（API 端点传 request + 操作者租户；
        # 任务/旧测试不传则记 None/平台默认）。
        request: Request | None = None,
    ) -> ReviewTask:
        """升级复核任务（**必须**限定租户范围）"""
        task = await self.get_review_by_id(review_id, tenant_id=tenant_id)
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status not in ["pending", "in_review"]:
            raise ValueError(f"Cannot escalate review with status {task.status}")

        # P1-SEC-007 修复：越权检查 - 仅分配的咨询师或管理员可升级
        if not is_admin and task.assigned_to is not None and task.assigned_to != counselor_id:
            raise ValueError("无权升级此复核任务：任务已分配给其他咨询师")

        # M-Svc-6 修复：escalate 不应复用 resolved_by/resolved_at 字段（语义不一致：
        # 升级并非解决）。ReviewTask 模型无 escalated_by 字段，改为在 OperationLog.detail
        # 中记录升级操作者，保留审计链清晰。
        previous_status = task.status
        task.resolution_note = reason
        task.status = "escalated"
        # ISS-041 修复：统一 naive UTC
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # 记录升级审计日志，detail 中明确 escalate_by（避免与 resolved_by 混淆）
        # P2-33 第六批：改走 record_audit（SSOT）——ip 从 request 取、tenant_id 落列，
        # 不再手写 json.dumps + db.add。
        await record_audit(
            self.db,
            actor_id=counselor_id,
            actor_role=USER_ROLE_ADMIN if is_admin else USER_ROLE_COUNSELOR,
            action="review.escalated",
            target_type="review_task",
            target_id=review_id,
            detail={
                "escalated_by": counselor_id,
                "reason": reason,
                "previous_status": previous_status,
            },
            request=request,
            tenant_id=tenant_id,
        )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_review_stats(
        self,
        days: int = 30,
        *,
        assigned_to: int | None = None,
        tenant_id: int,
    ) -> ReviewStats:
        """获取复核统计.

        ISS-071 修复: 支持 assigned_to 范围过滤, 使统计卡口径与
        list_reviews (咨询师仅看分配给自己的任务) 一致; 为 None 时统计全部。

        P0-FIX-2026-10-11: ``tenant_id`` 必填。原实现统计全平台复核任务数，
        租户 A 的管理员能从「危机数 / 高危数」反推他校的心理危机规模。
        """
        scope_filters = [tenant_scoped_filter(User, tenant_id)]
        if assigned_to is not None:
            scope_filters.append(ReviewTask.assigned_to == assigned_to)

        # OPT-P2-002：合并 4 条串行 count 查询为单条条件聚合
        # （COUNT(*) FILTER 与 monitoring.py 的 H-07 修复同模式，SQLite/PG 兼容）
        total_expr = func.count().label("total")
        pending_expr = func.count().filter(ReviewTask.status == "pending").label("pending")
        in_review_expr = func.count().filter(ReviewTask.status == "in_review").label("in_review")
        resolved_expr = func.count().filter(ReviewTask.status == "resolved").label("resolved")
        escalated_expr = func.count().filter(ReviewTask.status == "escalated").label("escalated")
        crisis_expr = func.count().filter(ReviewTask.crisis_override.is_(True)).label("crisis_count")
        high_risk_expr = func.count().filter(ReviewTask.priority == "high_risk_review").label("high_risk_count")

        stats_query = select(
            total_expr,
            pending_expr,
            in_review_expr,
            resolved_expr,
            escalated_expr,
            crisis_expr,
            high_risk_expr,
        )
        # P0-FIX-2026-10-11: review_tasks 无 tenant_id 列，JOIN User 推导租户
        stats_query = stats_query.select_from(
            ReviewTask.__table__.join(User.__table__, User.id == ReviewTask.user_id)
        ).where(*scope_filters)
        row = (await self.db.execute(stats_query)).one()

        return ReviewStats(
            total=row.total,
            pending=row.pending,
            in_review=row.in_review,
            resolved=row.resolved,
            escalated=row.escalated,
            crisis_count=row.crisis_count,
            high_risk_count=row.high_risk_count,
        )

    def to_response(self, task: ReviewTask) -> ReviewTaskResponse:
        """转换为响应模型"""
        return ReviewTaskResponse(
            id=task.id,
            user_id=task.user_id,
            risk_report_id=task.risk_report_id,
            risk_level=task.risk_level,
            risk_score=task.risk_score,
            review_triggers=json.loads(task.review_triggers or "[]"),
            crisis_override=bool(task.crisis_override),
            status=task.status,
            priority=task.priority,
            assigned_to=task.assigned_to,
            resolved_by=task.resolved_by,
            resolution_note=task.resolution_note,
            created_at=task.created_at,
            updated_at=task.updated_at,
            resolved_at=task.resolved_at,
        )


class CrisisEventService:
    """危机事件审计服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_crisis_event(self, data: CrisisEventCreate) -> CrisisEvent:
        """记录危机事件"""
        # M-Svc-7 修复：验证 crisis_keywords 长度，避免过大 payload 导致
        # JSON 字段溢出或序列化性能问题（每个 keyword ≤100 字符，总数 ≤50）
        keywords = list(data.crisis_keywords or [])
        if len(keywords) > 50:
            raise ValueError("crisis_keywords 数量不能超过 50 个")
        for kw in keywords:
            if len(str(kw)) > 100:
                raise ValueError(f"单个 crisis_keyword 长度不能超过 100 字符: {str(kw)[:20]}...")

        event = CrisisEvent(
            user_id=data.user_id,
            report_id=data.report_id,
            trigger_source=data.trigger_source,
            crisis_keywords=json.dumps(keywords),
            crisis_score=data.crisis_score,
            input_summary=data.input_summary,
            review_task_id=data.review_task_id,
            status="detected",
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_crisis_events(
        self,
        filter_data: CrisisEventFilter,
        tenant_id: int,
    ) -> dict:
        """查询危机事件（**必须**限定租户范围）。

        AUDIT-2026-10-08 (P1-4)：原实现是裸 ``select(CrisisEvent)``，无任何租户
        条件。危机事件含 ``input_summary``（用户自述原文摘要）与
        ``crisis_keywords``（自伤/自杀等关键词），属**最高敏感级**数据；跨租户
        泄露的后果不是「多看到几条记录」，而是直接暴露他校学生的心理危机内容。

        为什么必须 JOIN ``User``：``crisis_events`` 表**本身没有 tenant_id 列**
        （``models/review.py`` 中无 tenant_id 映射），无法像多数表那样直接
        ``tenant_scoped_query(CrisisEvent, ...)`` —— 那会抛
        ``TenantColumnMissingError``。租户归属只能沿 ``user_id`` 关联到
        ``users.tenant_id`` 推导，P2-31 起该正确写法封装为 SSOT 函数
        ``user_tenant_scoped_query``（本方法即经它构造）；执行层另有
        ``app/core/tenant_guard`` 兜底裸查询。

        为什么 ``tenant_id`` 是**必填**而非 ``None`` 时兜底默认租户：
        ``crisis_event.view`` 权限在 ``app/core/deps.py`` 里对 admin/super_admin
        开放，若在此处给 ``None`` 一个「看起来能跑」的默认值，等于把「调用方忘记
        传租户」变成静默的全量返回（租户 1），而不是响亮失败。宁可调用方编译不过，
        也不要跨租户危机数据被读出来。
        """
        query = user_tenant_scoped_query(CrisisEvent, tenant_id)

        if filter_data.status:
            query = query.where(CrisisEvent.status == filter_data.status)
        if filter_data.start_date:
            query = query.where(CrisisEvent.created_at >= filter_data.start_date)
        if filter_data.end_date:
            query = query.where(CrisisEvent.created_at <= filter_data.end_date)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(desc(CrisisEvent.created_at))
        query = query.offset((filter_data.page - 1) * filter_data.page_size)
        query = query.limit(filter_data.page_size)

        result = await self.db.execute(query)
        events = result.scalars().all()

        return {
            "items": [self._to_response(e) for e in events],
            "total": total,
            "page": filter_data.page,
            "page_size": filter_data.page_size,
        }

    async def get_stats(self, tenant_id: int) -> dict:
        """危机事件状态分布统计（P1-15 / F-03 修复）。

        原前端 ``page_size:200`` 拉全量事件到浏览器 filter：事件超 200 条时
        分子截断、分母不截断，分布是错的；且危机事件含 ``input_summary``
        （用户自述原文摘要）与 ``crisis_keywords``，传输 200 条完整记录的
        泄露面也随放大。改为 SQL 层条件聚合。

        口径与 ``get_crisis_events``（不带任何过滤）一致：
        - 范围同样 JOIN ``User`` 推导租户（crisis_events 无 tenant_id 列，
          理由见 get_crisis_events 文档），``tenant_id`` 必填；
        - total 统计全部状态（含 closed 等未展示状态），四个状态桶各计各的，
          与前端卡片「总数 + 四状态」的结构一致。
        """
        stmt = (
            select(
                func.count().label("total"),
                func.count()
                .filter(CrisisEvent.status == "detected")
                .label("detected"),
                func.count()
                .filter(CrisisEvent.status == "reviewed")
                .label("reviewed"),
                func.count()
                .filter(CrisisEvent.status == "escalated")
                .label("escalated"),
                func.count()
                .filter(CrisisEvent.status == "resolved")
                .label("resolved"),
            )
            .select_from(
                CrisisEvent.__table__.join(
                    User.__table__, User.id == CrisisEvent.user_id
                )
            )
            .where(tenant_scoped_filter(User, tenant_id))
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "total": int(row.total or 0),
            "detected": int(row.detected or 0),
            "reviewed": int(row.reviewed or 0),
            "escalated": int(row.escalated or 0),
            "resolved": int(row.resolved or 0),
        }

    async def handle_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        action: str,
        note: str | None = None,
        *,
        tenant_id: int,
        operator_role: str,
        # P2-33 第六批：审计上下文（透传给 _write_crisis_audit_log）
        request: Request | None = None,
    ) -> CrisisEvent:
        """处理危机事件 (status: detected/reviewed/escalated → reviewed)

        P0-FIX-2026-10-11：``tenant_id`` 为必填。原实现按主键裸取，任何租户
        的咨询师都能把**他校学生**的危机事件改成「已处理」——不只是读到
        input_summary，而是能直接改写危机处置状态，后果是真实的危机被静默关闭。

        ISS-072 修复：
        - 状态从 "handled" 改为 "reviewed"（与前端筛选器一致）
        - 新增状态机校验（detected|reviewed|escalated → reviewed）
        - 新增审计日志写入 OperationLog
        """
        # M-Svc-8 修复：白名单校验 action，防止任意字符串写入 handled_action 字段
        if action not in _ALLOWED_CRISIS_ACTIONS:
            raise ValueError(f"无效的 action: {action}，允许值: {', '.join(sorted(_ALLOWED_CRISIS_ACTIONS))}")

        event = await self._get_crisis_event_scoped(event_id, tenant_id)
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        # ISS-072 状态机校验
        self._validate_crisis_transition(event.status, "reviewed")

        # ISS-005 修复: 状态变更与审计日志写入同一 savepoint, 统一 commit
        event.handled_by = handled_by
        event.handled_action = action
        event.status = "reviewed"
        # ISS-041 修复：统一 naive UTC
        event.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.db.begin_nested():
            await self.db.flush()
            await self._write_crisis_audit_log(
                operator_id=handled_by,
                action_type="crisis_event_handle",
                event_id=event_id,
                detail={"action": action, "note": note, "new_status": "reviewed"},
                operator_role=operator_role,
                request=request,
                tenant_id=tenant_id,
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def escalate_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        reason: str,
        *,
        tenant_id: int,
        operator_role: str,
        # P2-33 第六批：审计上下文（透传给 _write_crisis_audit_log）
        request: Request | None = None,
    ) -> CrisisEvent:
        """升级危机事件 (status: detected|reviewed → escalated)

        P0-FIX-2026-10-11：``tenant_id`` 为必填（同 handle_crisis_event）。

        ISS-072 修复：新增端点，将事件升级到 escalated 状态（通知更高层级介入）。
        """
        event = await self._get_crisis_event_scoped(event_id, tenant_id)
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        self._validate_crisis_transition(event.status, "escalated")

        # ISS-005 修复: 状态变更与审计日志写入同一 savepoint, 统一 commit
        event.handled_by = handled_by
        event.handled_action = "escalate"
        event.status = "escalated"
        # ISS-041 修复：统一 naive UTC
        event.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.db.begin_nested():
            await self.db.flush()
            await self._write_crisis_audit_log(
                operator_id=handled_by,
                action_type="crisis_event_escalate",
                event_id=event_id,
                detail={"reason": reason, "new_status": "escalated"},
                operator_role=operator_role,
                request=request,
                tenant_id=tenant_id,
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def close_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        note: str | None = None,
        *,
        tenant_id: int,
        operator_role: str,
        # P2-33 第六批：审计上下文（透传给 _write_crisis_audit_log）
        request: Request | None = None,
    ) -> CrisisEvent:
        """关闭危机事件 (status: detected|reviewed|escalated → resolved)

        P0-FIX-2026-10-11：``tenant_id`` 为必填。resolved 是**终态**，
        被跨租户关闭后在本租户内不可再开启——这是三个端点里后果最重的一个。

        ISS-072 修复：新增端点，将事件关闭到 resolved 终态。
        """
        event = await self._get_crisis_event_scoped(event_id, tenant_id)
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        self._validate_crisis_transition(event.status, "resolved")

        # ISS-005 修复: 状态变更与审计日志写入同一 savepoint, 统一 commit
        event.handled_by = handled_by
        event.handled_action = "resolved"
        event.status = "resolved"
        # ISS-041 修复：统一 naive UTC
        event.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.db.begin_nested():
            await self.db.flush()
            await self._write_crisis_audit_log(
                operator_id=handled_by,
                action_type="crisis_event_close",
                event_id=event_id,
                detail={"note": note, "new_status": "resolved"},
                operator_role=operator_role,
                request=request,
                tenant_id=tenant_id,
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def _get_crisis_event_scoped(
        self, event_id: int, tenant_id: int
    ) -> CrisisEvent | None:
        """P0-FIX-2026-10-11：按「事件 + 所属学生租户」取单条危机事件。

        与 ``get_crisis_events`` 同源：``crisis_events`` 无 tenant_id 列，
        只能 JOIN ``User`` 推导。跨租户返回 None（调用方按 404 处理）。
        """
        stmt = user_tenant_scoped_query(CrisisEvent, tenant_id).where(
            CrisisEvent.id == event_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def _validate_crisis_transition(self, current: str, target: str) -> None:
        """ISS-072 修复：危机事件状态机校验，禁止非法状态跳变."""
        allowed = _CRISIS_STATE_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise ValueError(
                f"非法状态转换: {current} → {target}，当前状态 {current} 仅允许转换到 "
                f"{sorted(allowed) or '（终态，不可转换）'}"
            )

    async def _write_crisis_audit_log(
        self,
        operator_id: int,
        action_type: str,
        event_id: int,
        detail: dict,
        *,
        # AUDIT-2026-10-13 (P1-21)：操作者角色由调用方如实传入。改前硬编码
        # "admin"，而危机处置端点对 counselor / admin / super_admin 均放行 ——
        # 咨询师关闭危机事件在审计里被记成 "admin"，第二人复核时会误判处置人
        # 身份。无默认值：漏传直接 TypeError。
        operator_role: str,
        # P2-33 第六批：审计上下文由调用方穿入（API 端点传 request + 操作者租户；
        # 任务/旧调用不传则记 None/平台默认）。
        request: Request | None = None,
        tenant_id: int | None = None,
    ) -> None:
        """ISS-072 修复：危机事件状态流转审计日志.

        权限/安全/数据一致性场景，写入 OperationLog 供第二人复核。
        ISS-005 修复：仅 flush 不 commit, 由调用方在 savepoint 内统一 commit.
        """
        # P2-33 第六批：改走 record_audit（SSOT）——ip 从 request 取、tenant_id 落列。
        await record_audit(
            self.db,
            actor_id=operator_id,
            actor_role=operator_role,
            action=action_type,
            target_type="crisis_event",
            target_id=event_id,
            # L-API-3 修复：截断 detail 至 5000 字符，避免超 DB 字段限制
            detail=detail,
            request=request,
            tenant_id=tenant_id,
        )

    def _to_response(self, event: CrisisEvent) -> dict:
        """转换为响应"""
        return {
            "id": event.id,
            "user_id": event.user_id,
            "report_id": event.report_id,
            "trigger_source": event.trigger_source,
            "crisis_keywords": _parse_crisis_keywords(event.crisis_keywords, event.id),
            "crisis_score": event.crisis_score,
            "input_summary": event.input_summary,
            "review_task_id": event.review_task_id,
            "status": event.status,
            "handled_by": event.handled_by,
            "handled_action": event.handled_action,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "handled_at": event.handled_at.isoformat() if event.handled_at else None,
        }
