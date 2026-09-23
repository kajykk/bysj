# MIGRATION HEAD MERGE REPORT — v1.20

> **日期**: 2026-05-01
> **Alembic 版本**: 1.14

---

## 1. 合并前状态

```
alembic heads:
  a1b2c3d4e5f6 (head) — add_review_and_crisis_tables
  b1a7c0d9f4e8 (head) — add_schema_model_constraints

alembic current:
  eab25055097a — consolidated_initial_schema
```

**问题**: 数据库实际已有所有表（包括 refresh_token_sessions, review_tasks, crisis_events, monitoring_logs 等），但 alembic 版本表仅追踪到初始 schema。双 head 导致 `upgrade head` 歧义。

---

## 2. 合并操作

```bash
# Step 1: 创建 merge revision
alembic merge a1b2c3d4e5f6 b1a7c0d9f4e8 -m "merge dual heads v1.20"
→ 生成: 6e25d8827741_merge_dual_heads_v1_20.py

# Step 2: Stamp 数据库到最新 head
alembic stamp b1a7c0d9f4e8
alembic stamp 6e25d8827741

# Step 3: 验证
alembic upgrade head → 无错误 (no DDL changes needed)
alembic heads → 6e25d8827741 (head) — 单 head ✅
alembic current → 6e25d8827741 (head) (mergepoint)
```

---

## 3. 合并后 Revision Tree

```
eab25055097a (consolidated_initial_schema)
    │
    └── 5f2c9d3a1b7e (add_refresh_token_sessions)
             │
             ├── a1b2c3d4e5f6 (add_review_and_crisis_tables)
             │        │
             │        └── b1a7c0d9f4e8 (add_schema_model_constraints)
             │
             └── 6e25d8827741 (merge dual heads v1.20)  ← NEW HEAD
```

---

## 4. Downgrade 策略

Merge revision 6e25d8827741 是纯逻辑合并，不包含 DDL 变更。Downgrade 行为：
- `alembic downgrade -1` 将回退到 `b1a7c0d9f4e8`（但不会执行反向 DDL，因为 stamp 而非实际迁移）

**注意**: 由于数据库状态通过 `stamp` 而非实际迁移对齐，downgrade 不会删除已有表。如果有新迁移创建了表，downgrade 会正常执行 `drop_table`。

---

## 5. 验证清单

- [x] `alembic heads` 仅输出一个 head: 6e25d8827741
- [x] `alembic upgrade head` 无错误
- [x] `alembic current` 显示 mergepoint
- [x] 核心表（review_tasks, crisis_events）存在
- [x] 已有数据未丢失
