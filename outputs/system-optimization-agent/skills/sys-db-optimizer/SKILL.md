---
name: sys-db-optimizer
description: >-
  This skill should be used when optimizing database performance — "慢 SQL",
  "建索引", "长事务锁表", "大表全表扫描", "历史数据归档". It targets §4.1.2
  of the optimization plan using SQLAlchemy/Alembic on this project.
agent_created: true
---

# sys-db-optimizer

## 用途
消除数据库瓶颈：慢 SQL、缺失索引、长事务、全表扫描、历史数据膨胀。

## 何时使用
- `sys-perf-diagnosis` 指向 DB 为瓶颈。
- 用户要求「优化慢查询」「给高频查询建索引」。

## 执行流程
1. **抓慢 SQL**：开启慢查询日志 / SQLAlchemy `echo`，汇总 P95 最高的语句。
2. **EXPLAIN/ANALYZE**：确认是否走索引、是否全表扫描、行数估算偏差。
3. **建/调索引**：为高频 WHERE/JOIN/ORDER BY 列建复合索引；删除冗余/未用索引。
4. **缩小事务**：控制事务范围，避免长事务锁表；拆分大事务为小批。
5. **查询重写**：避免 `SELECT *`、N+1（用 `joinedload`/`selectinload`）、函数包裹索引列。
6. **历史数据治理**：对大表做分区 / 分表 / 归档冷数据（通过 Alembic 迁移）。
7. **回归验证**：用 `sys-load-testing` 复测，确认 P95 下降且无新全表扫描。

## 工具与脚本
- ORM：SQLAlchemy（`backend/app/models`、`app/db`）。
- 迁移：Alembic（`backend/alembic`、`alembic.ini`）。
- 本地库：`backend/depression_system.db`（SQLite）；生产多为 Postgres。
- 分析：`EXPLAIN (ANALYZE, BUFFERS)`、慢查询日志、`sqlcommenter`。

## 验收与 KPI（§3）
- 慢查询数量趋零、全表扫描显著下降。
- 高频接口 DB 耗时占比下降，P95 达标。

## 与本工程栈的对应
- 模型层在 `backend/app/models`；会话/引擎在 `backend/app/db` 或 `core`。
- 迁移脚本放 `backend/alembic/versions`，索引变更须向后兼容并走评审。

## 注意事项
- 索引/分区变更必须在测试环境验证并评估写入放大。
- 迁移脚本保持向后兼容，配合 `sys-release-governance` 灰度。
