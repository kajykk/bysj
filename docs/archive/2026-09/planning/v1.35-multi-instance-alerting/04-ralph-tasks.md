# 04-ralph-tasks — v1.35-multi-instance-alerting

> **执行原则**: 按物理顺序执行。每完成标记 `[x]`。

---

## Phase 1: 跨实例去重 (P0)

### T1.1 创建 dedup_lock 模块

- [x] `app/monitoring/dedup_lock.py` 新建
- [x] `try_acquire_lock(fingerprint, ttl)` 异步函数
- [x] Redis 不可用时降级到 SQL (调用 v1.34 dedup)
- [x] 单元测试 (Redis up/down, lock acquire/release)

### T1.2 集成到 dedup

- [x] `app/monitoring/dedup.py::should_send` 优先 Redis
- [x] 获取锁成功 -> 返回 True (发送)
- [x] 获取锁失败 -> 返回 False (跳过)
- [x] 单元测试

---

## Phase 2: AlertArchive 模型 (P0)

### T2.1 创建 AlertArchive 模型

- [x] `app/models/admin.py` 新增 `AlertArchive`
- [x] 字段: id, original_id, rule, severity, status, message, labels, annotations, fingerprint, original_created_at, archived_at, detail
- [x] 索引: (rule, severity), (original_created_at)
- [x] 注册到 `app/models/__init__.py`

---

## Phase 3: 实际归档逻辑 (P0)

### T3.1 修改 _archive_impl

- [x] `app/tasks/alerts.py::_archive_impl` 改为真实 insert + delete
- [x] 事务: insert 1000 条 → delete 1000 条
- [x] 失败回滚
- [x] 单元测试 (使用 mock db)

### T3.2 归档查询 API

- [x] `app/api/v1/alerts.py` 新增 `GET /api/v1/alerts/archive`
- [x] admin 角色要求
- [x] 过滤: rule, severity, status, time range
- [x] 单元测试

---

## Phase 4: AlertManager 同步 (P1)

### T4.1 创建 am_sync 模块

- [x] `app/monitoring/am_sync.py` 新建
- [x] `push_silence(silence)` 调用 AM API
- [x] `pull_silences()` 从 AM 拉取 (定时任务)
- [x] 配置: ALERTMANAGER_URL, ALERTMANAGER_USER, ALERTMANAGER_PASSWORD

### T4.2 集成到 silences API

- [x] `app/api/v1/silences.py::create_silence` 调用 am_sync.push_silence
- [x] 失败降级 (本地创建, 同步失败记录)
- [x] 单元测试

### T4.3 AM webhook 接收

- [x] `app/api/v1/silences.py` 新增 `POST /api/v1/alerts/silences/sync`
- [x] 接收 AM 静默变更事件
- [x] 同步本地 is_active

---

## Phase 5: 回归测试 (P0)

### T5.1 核心测试组

- [x] tests/test_dedup_lock.py 全过
- [x] tests/test_alert_tasks.py 回归全过
- [x] tests/api/test_silences_api.py 回归全过
- [x] tests/test_dedup.py 回归全过
- [x] 现有 sentry / metrics / admin_metrics / audit_logs 不破坏

---

## 进度统计

- 总任务: 5 phases
- P0: 4 phases
- P1: 1 phase
- 完成: 5/5 (100%)
