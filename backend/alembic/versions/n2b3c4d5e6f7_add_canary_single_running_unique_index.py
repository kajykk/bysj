"""add_canary_single_running_unique_index

为 canary_records 增加「同一 route_prefix 至多一条 RUNNING」的部分唯一索引。

背景（配合 PR #85 的应用层修复）:
    CanaryManager.start_canary 是 check-then-insert。PR #85 已在应用层补上
    PostgreSQL `pg_advisory_xact_lock(2000, sha256(route_prefix))` +
    冲突查询 `with_for_update()`，能挡住本服务内部的并发启动；但它挡不住：
      - 非本服务写入（手工 SQL、其他服务、运维脚本）；
      - 历史遗留的重复 RUNNING 行。

    重复 RUNNING 的后果是可观测的故障：get_active_canary 的 scalar_one_or_none()
    会抛 MultipleResultsFound（fusion 层吞成 warning、API 层 500），且同一
    route_prefix 的两份流量百分比会互相覆盖，灰度分流语义失效。

为何必须用数据库约束:
    唯一索引是最后一道防线——应用层的锁只覆盖「同一个服务的并发路径」，
    绕过服务的写入路径无法被拦截。同 m1a2b3c4d5e6 对 is_latest 的处理逻辑。

为何用**表达式** + 部分索引:
    - route_prefix 可为 NULL（NULL = 全局金丝雀）。PostgreSQL/SQLite 的唯一
      索引把 NULL 视为互不相等，直接对 route_prefix 建唯一索引挡不住
      "多条 route_prefix IS NULL 的 RUNNING"（正是全局金丝雀的并发场景），
      故用表达式 `COALESCE(route_prefix, '')` 把 NULL 归一到一个哨兵值。
    - 部分索引 `WHERE status = 'running'`：同一 route_prefix 允许存在任意多条
      历史记录（rolled_back / completed），只有活跃金丝雀需要唯一。
    - 表达式索引 + 部分索引 PG 9.0+ / SQLite 3.9.0+ 均支持。

脏数据处理:
    上线前应先跑 scripts/check_canary_duplicate_running.py 查脏数据。本迁移在
    发现重复时**不删除行**（CanaryRecord 是灰度审计记录，删除会丢证据），
    而是把多余的 RUNNING 置为 rolled_back 并写明原因，保留 started_at 与
    rollback_reason 供事后追溯。

Revision ID: n2b3c4d5e6f7
Revises: m1a2b3c4d5e6
Create Date: 2026-10-10 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n2b3c4d5e6f7"
down_revision: Union[str, None] = "m1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_canary_records_single_running"
_ROLLBACK_REASON = "migration n2b3c4d5e6f7: duplicate RUNNING cleanup"


def _duplicate_running_ids(bind) -> list[int]:
    """返回每个 (route_prefix 作用域) 内多余的 RUNNING 行 id（保留 started_at 最新一条）.

    作用域键用 COALESCE(route_prefix, '') —— 与索引表达式保持一致，
    否则清理口径和唯一约束口径会不一致。
    """
    scope = sa.text("COALESCE(route_prefix, '')")
    if bind.dialect.name == "postgresql":
        sql = sa.text(
            """
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY COALESCE(route_prefix, '')
                           ORDER BY started_at DESC NULLS LAST, id DESC
                       ) AS rn
                FROM canary_records
                WHERE status = 'running'
            ) t
            WHERE rn > 1
            """
        )
    else:
        # SQLite 3.25+ 支持窗口函数；此处用自连接写法兼容更老版本。
        sql = sa.text(
            """
            SELECT c.id
            FROM canary_records c
            WHERE c.status = 'running'
              AND c.id <> (
                    SELECT k.keep_id FROM (
                        SELECT COALESCE(route_prefix, '') AS scope_key,
                               MAX(id) AS keep_id
                        FROM canary_records
                        WHERE status = 'running'
                        GROUP BY COALESCE(route_prefix, '')
                    ) k
                    WHERE k.scope_key = COALESCE(c.route_prefix, '')
              )
            """
        )
    rows = bind.execute(sql).fetchall()
    del scope  # 仅用于说明表达式一致性，实际方言已内联
    return [int(r[0]) for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    dup_ids = _duplicate_running_ids(bind)
    if dup_ids:
        print(f"[n2b3c4d5e6f7] 发现 {len(dup_ids)} 条重复 RUNNING 金丝雀, 置为 rolled_back")
        # 用 expanding bindparam 传 id，避免把 id 拼进 SQL 文本
        # （bandit B608 hardcoded SQL；分批仅为规避 PG 参数上限）
        stmt = sa.text(
            "UPDATE canary_records SET status = 'rolled_back', "
            "rollback_reason = :reason WHERE id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True))
        batch = 500
        for i in range(0, len(dup_ids), batch):
            bind.execute(
                stmt,
                {"reason": _ROLLBACK_REASON, "ids": dup_ids[i : i + batch]},
            )
    else:
        print("[n2b3c4d5e6f7] 无重复 RUNNING 金丝雀, 跳过清理")

    # ⚠️ 必须传**未编译**的表达式（sa.text），传编译后的对象会抛
    # ArgumentError: SQL expression element for DDL constraint expected
    op.create_index(
        INDEX_NAME,
        "canary_records",
        [sa.text("COALESCE(route_prefix, '')")],
        unique=True,
        sqlite_where=sa.text("status = 'running'"),
        postgresql_where=sa.text("status = 'running'"),
    )
    print(f"[{revision}] 部分唯一索引 {INDEX_NAME} 创建完成")


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="canary_records")
    print(f"[{revision}] 部分唯一索引 {INDEX_NAME} 已回滚")
