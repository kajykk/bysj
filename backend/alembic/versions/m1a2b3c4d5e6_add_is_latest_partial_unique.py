"""add_is_latest_partial_unique_constraints

SEC-FIX-2026-10-05: 为 is_latest 与告警去重补数据库级唯一约束。

背景（审查发现的并发缺陷）:
    1. risk_assessments.is_latest 的写入是「先全清再插新」的 check-then-act
       （risk_service_assessment.py:206-226 与
       api/v1/model_predict/_common.py:118-141），其中 _common 那条
       fire-and-forget 任务使用**独立 session**。此前只有普通复合索引
       ix_risk_assessments_user_is_latest（user_id, is_latest），无唯一性。

       并发下两个 session 各自「UPDATE ... SET is_latest=False」+「INSERT
       (is_latest=True)」会在 READ COMMITTED 下交错 → 同一 user_id 出现
       2 条 is_latest=True。

       后果：is_latest 是「最新评估」的唯一真相来源（j1f6a7b8c9d0 迁移注释
       明言用于替代 GROUP BY + max(created_at)）。出现 2 条后，依赖
       WHERE is_latest=True 的查询（如 list_my_users）会返回**重复用户行**，
       咨询师工作台把同一学生列两次，max(created_at) 语义被破坏。

    2. warning_notifications.risk_assessment_id 的告警去重同样是
       check-then-act（risk_service_warning.py:77-102 先 SELECT 再 INSERT，
       靠捕获 SAIntegrityError 兜冲突）。但该列只有 index=True 没有唯一性
       → 那个 IntegrityError 永远不会触发，去重在并发下失效。

为何必须用数据库约束:
    应用层的检查无法覆盖两个独立 session / 独立事务的并发（check 与 act 之间
    存在窗口），只有唯一索引能真正兜底。

为何用**部分**索引:
    部分唯一索引（带 WHERE）只约束满足条件的行：
      - risk_assessments: WHERE is_latest —— 否则同一 user_id 的所有历史评估
        （is_latest=False）会因 user_id 重复而全部冲突；
      - warning_notifications: WHERE risk_assessment_id IS NOT NULL ——
        该列 nullable（评估删除时 SET NULL），历史上可能有多条 NULL 关联的
        告警行，全局 unique 会破坏既有数据。
    PG 与 SQLite 均支持部分索引（PG 9.0+ / SQLite 3.8.0+）。

Revision ID: m1a2b3c4d5e6
Revises: l3c5d7e9f0a1
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m1a2b3c4d5e6"
down_revision: Union[str, None] = "l3c5d7e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_true_expr() -> sa.TextClause:
    """返回与方言无关的「布尔真」表达式。

    SQLite 存 0/1（Boolean 映射为 INTEGER），PostgreSQL 是原生 boolean。
    部分索引的 WHERE 子句必须匹配各方言的实际存储。

    ⚠️ 注意必须返回 **未编译的表达式**（sa.text）：
    `.compile(dialect=...)` 返回的是 PGCompiler 对象，传给
    `op.create_index(..., postgresql_where=...)` 会抛
    `ArgumentError: SQL expression element for DDL constraint expected,
    got PGCompiler` —— 索引根本不会被创建，且异常发生在建索引那一步，
    看起来像是「迁移执行了但没生效」。
    """
    return sa.text("is_latest")


def upgrade() -> None:
    bind = op.get_bind()
    is_true = _is_true_expr()

    # ---- 1. risk_assessments: 每个 user_id 至多一条 is_latest ----
    # 清理可能已存在的重复（同一 user_id 多条 is_latest=True）。
    # 只保留 created_at 最大的一条 —— 即"最新评估"的既有语义。
    # 先记下要置为 False 的 id，避免边查边改导致游标失效。
    dup_ids: list[int] = []
    if bind.dialect.name == "postgresql":
        rows = bind.execute(
            sa.text(
                """
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY user_id
                               ORDER BY created_at DESC NULLS LAST, id DESC
                           ) AS rn
                    FROM risk_assessments
                    WHERE is_latest
                ) t
                WHERE rn > 1
                """
            )
        ).fetchall()
    else:
        # SQLite 窗口函数自 3.25 起支持；为兼容更老版本改用自连接写法。
        rows = bind.execute(
            sa.text(
                """
                SELECT a.id
                FROM risk_assessments a
                JOIN (
                    SELECT user_id, MAX(created_at) AS max_created
                    FROM risk_assessments
                    WHERE is_latest
                    GROUP BY user_id
                ) m ON m.user_id = a.user_id
                WHERE a.is_latest
                  AND (a.created_at < m.max_created
                       OR (a.created_at = m.max_created AND a.id <> (
                           SELECT MAX(id) FROM risk_assessments b
                           WHERE b.user_id = a.user_id AND b.is_latest)))
                """
            )
        ).fetchall()

    dup_ids = [r[0] for r in rows]
    if dup_ids:
        print(f"[m1a2b3c4d5e6] 清理 risk_assessments 重复 is_latest: {len(dup_ids)} 行")
        # 分批更新，避免超长 SQL 与 PG 参数上限
        batch = 500
        for i in range(0, len(dup_ids), batch):
            chunk = dup_ids[i : i + batch]
            bind.execute(
                sa.text(
                    "UPDATE risk_assessments SET is_latest = "
                    + ("false" if bind.dialect.name == "postgresql" else "0")
                    + " WHERE id IN ("
                    + ",".join(str(int(x)) for x in chunk)
                    + ")"
                )
            )
    else:
        print("[m1a2b3c4d5e6] risk_assessments 无重复 is_latest, 跳过清理")

    op.create_index(
        "uq_risk_assessments_latest",
        "risk_assessments",
        ["user_id"],
        unique=True,
        sqlite_where=is_true,
        postgresql_where=is_true,
    )

    # ---- 2. warning_notifications: 同一评估至多一条告警 ----
    # 先清理存量重复：同一 risk_assessment_id 保留最早一条（告警的语义是
    # 「首次触发时记录」，保留最早的更符合业务含义；若保留最新，早期告警
    # 会被静默丢弃，而 OperationLog 里没有完整快照可还原）。
    # 不清理则 create_index(unique) 直接抛 UniqueViolation，迁移失败。
    dup_warn: list[int] = []
    if bind.dialect.name == "postgresql":
        dup_warn = [
            r[0]
            for r in bind.execute(
                sa.text(
                    """
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY risk_assessment_id
                                   ORDER BY id ASC
                               ) AS rn
                        FROM warning_notifications
                        WHERE risk_assessment_id IS NOT NULL
                    ) t
                    WHERE rn > 1
                    """
                )
            ).fetchall()
        ]
    else:
        dup_warn = [
            r[0]
            for r in bind.execute(
                sa.text(
                    """
                    SELECT a.id
                    FROM warning_notifications a
                    JOIN (
                        SELECT risk_assessment_id, MIN(id) AS keep_id
                        FROM warning_notifications
                        WHERE risk_assessment_id IS NOT NULL
                        GROUP BY risk_assessment_id
                    ) k ON k.risk_assessment_id = a.risk_assessment_id
                    WHERE a.risk_assessment_id IS NOT NULL
                      AND a.id <> k.keep_id
                    """
                )
            ).fetchall()
        ]

    if dup_warn:
        print(f"[m1a2b3c4d5e6] 清理 warning_notifications 重复告警: {len(dup_warn)} 行")
        # 重复告警直接删除：它们是去重失效产生的冗余行，保留会造成
        # 咨询师工作台把同一次风险评估的告警显示多次。
        batch = 500
        for i in range(0, len(dup_warn), batch):
            chunk = dup_warn[i : i + batch]
            bind.execute(
                sa.text(
                    "DELETE FROM warning_notifications WHERE id IN ("
                    + ",".join(str(int(x)) for x in chunk)
                    + ")"
                )
            )
    else:
        print("[m1a2b3c4d5e6] warning_notifications 无重复告警, 跳过清理")

    op.create_index(
        "uq_warning_notifications_assessment",
        "warning_notifications",
        ["risk_assessment_id"],
        unique=True,
        sqlite_where=sa.text("risk_assessment_id IS NOT NULL"),
        postgresql_where=sa.text("risk_assessment_id IS NOT NULL"),
    )

    print("[m1a2b3c4d5e6] 部分唯一索引创建完成")


def downgrade() -> None:
    op.drop_index("uq_warning_notifications_assessment", table_name="warning_notifications")
    op.drop_index("uq_risk_assessments_latest", table_name="risk_assessments")
    print("[m1a2b3c4d5e6] 部分唯一索引已回滚")
