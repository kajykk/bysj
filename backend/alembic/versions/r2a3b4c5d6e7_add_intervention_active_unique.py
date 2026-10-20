"""add_intervention_active_per_user_unique_index

M13 修复（ROUND_23）：每用户至多一条 active 干预计划的数据库级部分唯一约束。

背景（审查报告 M13 / 并发缺陷）:
    干预计划的写入路径是 check-then-act（app/services/risk_service_warning.py
    的 _auto_generate_intervention：先 SELECT status='active'，查不到才
    _create_plan_from_template）。ISS-014 加的 with_for_update() 只锁
    **已存在**的行——空表（或该用户历史计划都已 cancelled）时两个并发
    事务都查不到行、都无行可锁，于是都 INSERT，同一 user_id 出现两条
    active。

    并发入口真实存在：文本/生理两路评估各自起**独立 AsyncSessionLocal**
    （app/services/risk_service.py 的 _trigger_warning_and_intervention，
    fire-and-forget 后台任务），两个独立事务各自 commit。

    后果：干预任务按 active 计划发放（InterventionService.get_active），
    两条 active ⇒ 任务重复发放、完成率分子膨胀（M11 刚修过的口径又被
    污染）、咨询师工作台把同一学生列两次。

为何必须用数据库约束:
    应用层的"先查再插"无法覆盖两个独立事务（check 与 act 之间有窗口），
    with_for_update() 对不存在的行无能为力，只有唯一索引能真正兜底。
    应用层仍保留先查（作为快路径与降级回查），但不是唯一性保证。

为何用**部分**索引:
    status 还有 cancelled/completed 等历史值，全局 unique(user_id) 会
    让历史计划全部冲突；WHERE status = 'active' 只约束活跃计划。
    PG 与 SQLite 均支持部分索引（PG 9.0+ / SQLite 3.8.0+）。

与 m1a2b3c4d5e6 的**刻意分歧**（存量重复处置）:
    那个迁移对 is_latest / 告警去重的存量重复是**静默清理**（UPDATE 置
    False / DELETE 冗余行）。本迁移**中止**——同一用户保留哪条 active
    计划是业务决策（可能关联在途任务、完成率历史），迁移无权代替人工
    决定，也不能静默删数据。检测到重复即抛错并打印冲突清单。

Revision ID: r2a3b4c5d6e7
Revises: n2b3c4d5e6f7
Create Date: 2026-10-20 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r2a3b4c5d6e7"
down_revision: Union[str, None] = "n2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_intervention_plans_active_per_user"

# 部分索引 WHERE 子句。必须传**未编译表达式**（sa.text）：
# `.compile(dialect=...)` 返回的是编译器对象，传给
# `op.create_index(..., postgresql_where=...)` 会抛 ArgumentError，
# 索引根本不会被创建（教训见 m1a2b3c4d5e6 docstring）。
_ACTIVE_WHERE = sa.text("status = 'active'")


def find_duplicate_active_plans(bind) -> list[tuple[int, int, list[int]]]:
    """返回同用户并存多条 active 计划的冲突清单。

    Returns:
        ``[(user_id, active_count, [plan_id, ...]), ...]``，无冲突返回 ``[]``。
        plan_ids 按 id 升序，便于人工核对时定位"哪条更可能在途"。
    """
    if bind.dialect.name == "postgresql":
        rows = bind.execute(
            sa.text(
                """
                SELECT user_id,
                       COUNT(*) AS n,
                       string_agg(id::text, ',' ORDER BY id) AS ids
                FROM intervention_plans
                WHERE status = 'active'
                GROUP BY user_id
                HAVING COUNT(*) > 1
                ORDER BY user_id
                """
            )
        ).fetchall()
    else:
        # SQLite 无 string_agg，GROUP_CONCAT 够用（迁移检测路径）。
        rows = bind.execute(
            sa.text(
                """
                SELECT user_id,
                       COUNT(*) AS n,
                       GROUP_CONCAT(id) AS ids
                FROM intervention_plans
                WHERE status = 'active'
                GROUP BY user_id
                HAVING COUNT(*) > 1
                ORDER BY user_id
                """
            )
        ).fetchall()
    return [
        (int(user_id), int(n), [int(x) for x in str(ids).split(",") if x.strip()])
        for user_id, n, ids in rows
    ]


def upgrade() -> None:
    bind = op.get_bind()

    # 数据前置：存量重复 active 必须让迁移**可见地失败**。
    # 不清理、不任意保留——保留哪条属业务决策（见模块 docstring）。
    conflicts = find_duplicate_active_plans(bind)
    if conflicts:
        lines = [
            f"user_id={uid} 并存 {n} 条 active: plan_ids={ids}"
            for uid, n, ids in conflicts
        ]
        raise RuntimeError(
            f"[{revision}] 检测到 {len(conflicts)} 个用户存量重复 active 干预计划，"
            "迁移中止（保留哪条属业务决策，本迁移不代替人工决定）：\n  "
            + "\n  ".join(lines)
            + "\n请人工核对后删除或置为非 active，再重跑升级。"
        )

    op.create_index(
        INDEX_NAME,
        "intervention_plans",
        ["user_id"],
        unique=True,
        sqlite_where=_ACTIVE_WHERE,
        postgresql_where=_ACTIVE_WHERE,
    )
    print(f"[{revision}] {INDEX_NAME} 部分唯一索引创建完成")


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="intervention_plans")
    print(f"[{revision}] {INDEX_NAME} 已回滚")
