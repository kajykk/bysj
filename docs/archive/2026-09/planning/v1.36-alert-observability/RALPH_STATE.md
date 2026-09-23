# RALPH_STATE — v1.36-alert-observability

<!-- 
AI 指令: 
1. 本文件是 Ralph 项目的**唯一事实来源 (Source of Truth)**，任何状态变更必须同步更新此文件。
2. **生命周期**: 必须遵循 Planning (3 Rounds) -> Implementation -> Testing 的标准流程。
3. **顺序强制**: 在开发与测试阶段，必须严格按照 `04-ralph-tasks.md` 和 `05-test-plan.md` 中的列表物理顺序执行，**严禁跳跃**或乱序执行。
4. **状态维护**: 每次 Skill 执行结束，必须更新此文件中的进度条 (Progress) 和状态 (Status)。
-->

> **当前上下文 (Current Context)**: 实施阶段 (Implementation)
> **迭代名称 (Iteration)**: v1.36-alert-observability
> **基础**: v1.35-multi-instance-alerting (DELIVERED)
> **核心目标**: 告警系统可视化与可观测性

---

## 1. 规划阶段 (Planning Phase)
> **目标**: 在编码前通过 3 轮迭代完善需求与架构。

| 轮次 (Round) | 步骤 1: 草稿 (Draft) | 步骤 2: 自查 (Critique) | 步骤 3: 调研 (Research) | 步骤 4: 推演 (Simulation) | 步骤 5: 锁定 (Lock) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Round 1** (基线) | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 |
| **Round 2** (修订) | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 |
| **Round 3** (终定) | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 |

**规划完成**: 🎉 **3/3 Rounds, 15/15 Steps 全部完成**

---

## 2. 开发阶段 (Implementation Phase)
> **目标**: 严格按顺序执行开发任务。
> **⚠️ 执行铁律**: 必须严格按照 `04-ralph-tasks.md` 中的列表顺序执行任务。**严禁跳跃**或乱序执行。

- **状态**: ✅ 全部完成 (17/17)
- **进度**: 17 / 17 任务完成
- **引用**: `docs/planning/v1.36-alert-observability/04-ralph-tasks.md`
- **任务清单**:
  - Phase 0: T0.1 cache 工具 ✅, T0.2 instance 工具 ✅ (2)
  - Phase 1: T1.1 notifier ✅, T1.2 am_sync ✅, T1.3 dedup_lock ✅, T1.4 索引 ✅ (4)
  - Phase 2: T2.1 路由骨架 ✅, T2.2 趋势 ✅, T2.3 响应时长 ✅, T2.4 升级率 ✅, T2.5 通道成功 ✅, T2.6 静默命中 ✅, T2.7 AM 同步 ✅, T2.8 锁统计 ✅ (8)
  - Phase 3: T3.1 E2E ✅, T3.2 性能 ✅, T3.3 工具测试 ✅ (3)
  - Phase 4: T4.1 回归 ✅ (1)

### T3.1 端到端测试 (✅ 已完成 2026-06-03)

- ✅ `tests/test_observability_e2e.py` 新建 - 6/6 通过
- ✅ test_e2e_alert_to_channel_stats: 告警 → webhook 通道 → notifier 写 alert_channel_sent → channel-stats API 查到 (success_rate=1.0)
- ✅ test_e2e_alert_channel_failure_to_channel_stats: 通道异常 → alert_channel_failed → channel-stats success_rate=0.0 + error 详情
- ✅ test_e2e_silence_to_am_sync: 推送静默 → AM 200 → am_sync_success → am-sync API total_success=1
- ✅ test_e2e_am_sync_failure_to_am_sync_api: AM 500 → am_sync_failed → am-sync API recent_failures 含错误
- ✅ test_e2e_lock_fallback_to_stats: 锁 fallback 3 次 → flush → dedup_lock_stats → lock-stats API recent_flushes+historical_recent
- ✅ test_e2e_lock_mixed_paths_to_stats: acquired+skipped+fallback 混合 → flush → lock-stats API 全部反映
- ✅ 修复: WebhookNotifier 内部 try/except 吞掉异常, 改用 _RaisingWebhookNotifier 触发 _dispatch 的 error_msg 捕获
- ✅ 修复: dedup_lock 测试 mock_client.set 必须用 AsyncMock 才能 await
- ✅ 完整 e2e 数据流: 真实 db_session + 真实 TestClient + as_role("admin") + mock 外部服务

### T3.2 性能测试 (✅ 已完成 2026-06-03)

- ✅ `tests/performance/test_observability_perf.py` 新建 - 8/8 通过, 22.16s
- ✅ test_trend_7d_under_500ms: 10000 行 trend 计算 (LIMIT 模拟 100K 行) < 500ms
- ✅ test_trend_30d_under_1500ms: 30d 6h 桶聚合 < 1500ms
- ✅ test_response_time_7d_under_300ms: 5000 fired + 5000 acked self-JOIN < 300ms
- ✅ test_response_time_p99_calculation: 1..100 序列 p99 验证
- ✅ test_channel_stats_7d_under_200ms: 10000 行 4 通道聚合 < 200ms
- ✅ test_silence_hit_rate_under_100ms: 3000 fired + 1000 silenced < 100ms
- ✅ test_am_sync_under_100ms: 3000 success + 272 failed 聚合 < 100ms
- ✅ test_lock_stats_under_50ms: 500 flush 记录聚合 < 50ms
- ✅ 修复: 修正函数签名 `_compute_response_time(db,start,end,severity)` 不是 `(db,start,end,bucket,severity)`
- ✅ 修复: 自定义 _MultiResultSession 处理多 execute 调用 (fired/acked 拆分)
- ✅ 修复: channel_rows detail 构造中无效的条件 dict key 语法

### T3.3 工具模块测试 (✅ 已完成 2026-06-03)

- ✅ T3.3 子项均被 Phase 0 (T0.1/T0.2) 覆盖
- ✅ 29/29 tests/test_cache.py + tests/test_instance.py 通过, 20.74s
- ✅ test_make_cache_key_stable_for_same_params: 7 个 key 测试全过
- ✅ test_cache_get_hit_returns_parsed_value: redis 命中解析
- ✅ test_cache_set_redis_down_returns_false: redis 异常优雅降级
- ✅ test_get_instance_id_format: hostname-pid 格式 + 唯一性 + fallback

### T4.1 核心测试回归 (✅ 已完成 2026-06-03)

- ✅ 10 个核心测试文件 126/126 通过
- ✅ tests/test_dedup.py 7/7, tests/test_dedup_lock.py 20/20
- ✅ tests/test_am_sync.py 19/19, tests/test_alert_tasks.py 9/9
- ✅ tests/api/test_silences_api.py 8/8, tests/api/test_alerts_webhook.py 11/11
- ✅ tests/test_silence.py 11/11, tests/test_escalation.py 9/9
- ✅ tests/test_notifier.py 26/26, tests/api/test_alert_archive_api.py 6/6
- ⚠️ 2 个 RuntimeWarning (unawaited coroutine in test mocks, 非失败)



### T2.8 EP-7 Redis 锁可观测 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/lock-stats` 端点
- ✅ 数据源:
  - 内存: `dedup_lock._stats` (本进程) -> {acquired, skipped, fallback, errors}
  - 持久化: `OperationLog WHERE action_type='dedup_lock_stats' AND target_type='dedup_lock'`
- ✅ memory: 内存计数 + acquire_rate / fallback_rate / error_rate
- ✅ last_flush_at: `dedup_lock._last_flush_at` (ISO 8601)
- ✅ recent_flushes: 最近 10 条 flush 详情
- ✅ historical_recent: 最近 10 次 flush 累计 (含 fallback_rate / error_rate)
- ✅ 模块改造:
  - `dedup_lock.py` 新增 `_last_flush_at` 模块级变量
  - `dedup_lock.py` 新增 `get_last_flush_at()` / `set_last_flush_at()` 函数
  - `flush_lock_stats()` 成功后调用 `set_last_flush_at()` 记录时间
  - `reset_stats()` 同时重置 `_last_flush_at`
- ✅ 集成 cache (5min TTL) + instance_id + cached
- ✅ 单元测试 6/6 通过 (TC-OBS-007)
  - `test_lock_stats_basic` - 内存统计 + 比例计算
  - `test_lock_stats_recent_flushes` - 最近 flushes 详情
  - `test_lock_stats_historical_aggregation` - 累计历史
  - `test_lock_stats_empty` - 零数据不抛异常
  - `test_lock_stats_admin_required` - 未鉴权 401/403
  - `test_lock_stats_response_includes_instance_id` - 响应元信息

### T2.7 EP-6 AM 同步可观测 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/am-sync` 端点
- ✅ 数据源: `OperationLog WHERE action_type IN ('am_sync_success','am_sync_failed') AND target_type='alert_silence'`
- ✅ 统计: total_success / total_failed / total / success_rate
- ✅ by_operation: 按 push_silence / delete_silence / pull_silences 拆分
  - 含 success / failed / total / avg_duration_ms
- ✅ recent_failures: 最近 10 条失败 (operation, error, duration_ms, am_silence_id, created_at)
- ✅ avg_duration_ms: 全局平均同步耗时
- ✅ operation 参数过滤
- ✅ LIMIT 10000 兜底 (success/failed 各自)
- ✅ 集成 cache (5min TTL) + instance_id + cached + params
- ✅ 单元测试 7/7 通过 (TC-OBS-006)
  - `test_am_sync_stats_basic` - 8/2 = 80% 成功率
  - `test_am_sync_by_operation` - 3 种操作拆分
  - `test_am_sync_recent_failures` - 12 条失败只保留 10 条
  - `test_am_sync_operation_filter` - operation 过滤
  - `test_am_sync_empty` - 零数据不抛异常
  - `test_am_sync_admin_required` - 未鉴权 401/403
  - `test_am_sync_response_includes_instance_id` - 响应元信息

### T2.6 EP-5 静默命中率 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/silence-hit-rate` 端点
- ✅ 数据源: `OperationLog WHERE action_type IN ('alert_fired','alert_silenced') AND target_type='alert'`
- ✅ 命中率: `total_silenced / (total_fired + total_silenced)`
- ✅ by_matcher: 按 silence_name 拆分 (Top-20, 按 silenced_count 降序)
- ✅ by_severity: silenced 中的严重度分布 (含 ratio)
- ✅ by_matcher 内嵌 by_severity 子分布
- ✅ LIMIT 10000 兜底 (fired/silenced 各自)
- ✅ 集成 cache (5min TTL) + instance_id + cached + params
- ✅ 单元测试 6/6 通过 (TC-OBS-005)
  - `test_silence_hit_rate_basic` - 基础命中率 3/10 = 30%
  - `test_silence_hit_rate_by_matcher` - 3 个 matcher 拆分
  - `test_silence_hit_rate_by_severity` - by_severity 分布
  - `test_silence_hit_rate_empty` - 零数据不抛异常
  - `test_silence_hit_rate_admin_required` - 未鉴权 401/403
  - `test_silence_hit_rate_response_includes_instance_id` - 响应元信息

### T2.5 EP-4 通道成功率 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/channel-stats` 端点
- ✅ 数据源: `OperationLog WHERE action_type IN ('alert_channel_sent','alert_channel_failed') AND target_type='alert_channel'`
- ✅ SQL GROUP BY channel (in-memory 聚合)
- ✅ 计算: sent / failed / total / success_rate / avg_duration_ms / max_duration_ms
- ✅ 通道过滤参数 `channel` (webhook/slack/dingtalk/email)
- ✅ 全量统计: total_sent / total_failed / overall_success_rate
- ✅ LIMIT 10000 兜底
- ✅ 集成 cache (5min TTL) + instance_id + cached + params
- ✅ 单元测试 6/6 通过 (TC-OBS-004)
  - `test_channel_stats_basic` - 基础成功率 8/2 = 80%
  - `test_channel_stats_zero_failures` - 100% 成功率 (零失败)
  - `test_channel_stats_multiple_channels` - 4 通道分别统计 + channel 过滤
  - `test_channel_stats_duration_tracking` - avg/max duration_ms
  - `test_channel_stats_admin_required` - 未鉴权 401/403
  - `test_channel_stats_response_includes_instance_id` - 响应元信息

### T2.4 EP-3 升级率 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/escalation` 端点
- ✅ 数据源: `OperationLog WHERE action_type IN ('alert_fired','alert_escalated') AND target_type='alert'`
- ✅ 升级率: `total_escalated / total_fired`
- ✅ by_level: 统计每个升级目标级别 (e.g. P0/P1/L1/L2/L3)
- ✅ by_severity: 按严重度拆分升级率 (含 severity 过滤)
- ✅ by_rule: Top-20 规则按 escalated 降序, 含 fired/escalated/rate
- ✅ LIMIT 10000 兜底 (fired/esc 各自)
- ✅ 集成 cache (5min TTL) + instance_id + cached + params
- ✅ 单元测试 6/6 通过 (TC-OBS-003)
- ✅ 综合测试 30/30 通过 (T2.1 9 + T2.2 7 + T2.3 8 + T2.4 6)

### T2.3 EP-2 响应时长 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/response-time` 端点
- ✅ self-JOIN: alert_fired (fingerprint) + alert_acknowledged (fingerprint)
- ✅ 分位计算: `_percentile()` 工具 (线性插值, 支持 p50/p95/p99/max/min)
- ✅ LIMIT 10000 兜底 (fired/acked 各自)
- ✅ 统计: total_fired / total_acked / total_pending / ack_rate
- ✅ 严重度拆分: by_severity (count / mean / p95)
- ✅ 集成 cache (5min TTL) + instance_id + cached + params
- ✅ 单元测试 8/8 通过 (TC-OBS-002, 含 _percentile 工具 + severity breakdown)
- ✅ 综合测试 24/24 通过 (T2.1 9 + T2.2 7 + T2.3 8)

### T2.2 EP-1 告警趋势 (✅ 已完成 2026-06-03)

- ✅ `GET /alerts/observability/trend` 端点
- ✅ 参数: start_time, end_time (ISO 8601), bucket (5m/15m/1h/6h/1d), severity, status, group_by (severity/status/rule/none)
- ✅ 数据源: OperationLog WHERE action_type IN ('alert_fired','alert_resolved') AND target_type='alert'
- ✅ SQL LIMIT 10000 兜底, 后置过滤 severity/status (来自 JSON detail)
- ✅ 全量聚合: by_severity / by_status / by_rule (Top-20)
- ✅ 时间桶对齐: 向下对齐到 bucket 边界 (e.g. 1h -> :00:00)
- ✅ 集成 cache (5min TTL) + instance_id + cached + params
- ✅ 单元测试 7/7 通过 (TC-OBS-001)
- ✅ 综合测试 16/16 通过 (T2.1 9 + T2.2 7)

### T2.1 observability 路由骨架 (✅ 已完成 2026-06-03)

- ✅ `app/api/v1/observability.py` 新建 - 路由 prefix=`/alerts/observability`, tag=`observability`
- ✅ 注册到 `app/api/v1/__init__.py` (api_router.include_router)
- ✅ 公共依赖: `DbDep` (AsyncSession), `AdminDep` (User, require_role("admin"))
- ✅ 复用 cache 工具 (T0.1): `cached_or_compute` 包装函数
- ✅ 复用 instance 工具 (T0.2): `with_instance_meta` 附加 instance_id 元信息
- ✅ 路由注册验证: `/api/v1/alerts/observability/health` 出现在 `app.routes`
- ✅ 单元测试 9/9 通过: 导入/注册/助手/health/cached_or_compute/with_instance_meta
- ✅ T2.1 测试组命名: TC-OBS-000 (9/9 ✅)

### T1.4 OperationLog 复合索引 (✅ 已完成 2026-06-03)

- ✅ `app/models/admin.py::OperationLog.__table_args__` 增加 2 个复合索引
  - `idx_oplog_action_created` (action_type, created_at) - 告警通道/AM 同步/dedup_lock 统计的高频查询
  - `idx_oplog_target_action` (target_type, target_id, action_type) - 特定对象的审计追踪
- ✅ Alembic migration 生成: `a7b8c9d0e1f2_add_oplog_composite_indexes_v1_36.py` (down_revision=`6e25d8827741`)
- ✅ Alembic head 验证: `a7b8c9d0e1f2` 为新 head
- ✅ 单元测试 5/5 通过 (test_admin_models.py): 索引存在性 + 列序正确
- ✅ 综合回归 70/70 通过 (admin_models + dedup_lock + am_sync + notifier)

### T1.3 dedup_lock 内存计数 + flush (✅ 已完成 2026-06-03)

- ✅ `app/monitoring/dedup_lock.py` 增加模块级 `_stats: {acquired, skipped, fallback, errors}`
- ✅ `try_acquire_lock` 各路径增加对应计数 (acquired/skipped/fallback)
- ✅ 新增 `flush_lock_stats(db)` 写入 OperationLog (action_type=`dedup_lock_stats`, target_type=`dedup_lock`)
- ✅ 新增 `app/tasks/observability.py::flush_lock_stats_task` Celery 任务
- ✅ Celery beat 注册 60s 调度 (entry: `flush-lock-stats`)
- ✅ flush 失败不清零 (snapshot 模式, 只扣除已写入的计数, 下次重试)
- ✅ flush 全部为 0 时跳过写入 (避免噪音)
- ✅ 单元测试 9/9 通过 (acquired/skipped/fallback/no_redis_url + 4 个 flush 测试 + 1 个 includes_detail)
- ✅ 完整测试: `tests/test_dedup_lock.py` 20/20 通过
- ✅ 回归测试: `tests/test_dedup.py` 7/7 通过
- ✅ 模块导入验证: `from app.tasks.observability import flush_lock_stats_task` 成功

### T1.2 am_sync 记录同步结果 (✅ 已完成 2026-06-03)

- ✅ `app/monitoring/am_sync.py::push_silence` / `delete_silence` / `pull_silences` 改为 async, 增加 `db: AsyncSession | None = None` 参数
- ✅ 成功 → 写 OperationLog `am_sync_success` (target_type=`alert_silence`)
- ✅ 失败 → 写 OperationLog `am_sync_failed` (detail 含 `error` 字段)
- ✅ 三函数 (push_silence / delete_silence / pull_silences) 同理
- ✅ detail 字段: `operation`, `duration_ms`, `am_silence_id?`, `error?`, `count?` (pull)
- ✅ 写日志失败被 try/except 捕获, 不影响同步返回值
- ✅ 单元测试 4/4 通过 (`test_am_sync_success_logged`, `test_am_sync_failed_logged`, `test_am_sync_log_includes_am_silence_id`, `test_am_sync_log_failure_does_not_block_sync`)
- ✅ 完整测试: `tests/test_am_sync.py` 19/19 通过
- ✅ 回归测试: `tests/test_silence.py` 11/11 + `tests/api/test_silences_api.py` 8/8 通过
- ✅ 调用方已更新: `silences.py:109` 使用 `await push_silence(am_payload, db=db)`

### T1.1 notifier 记录通道发送 (✅ 已完成 2026-06-03)

- ✅ `app/monitoring/notifier.py::CompositeNotifier.send()` 改为 async, 增加 `db: AsyncSession | None = None` 参数
- ✅ 成功 → 写 OperationLog `alert_channel_sent` (target_type=`alert_channel`)
- ✅ 失败 → 写 OperationLog `alert_channel_failed` (detail 含 `error` 字段)
- ✅ detail 字段: `channel`, `duration_ms`, `rule`, `severity`, `status`, `fingerprint`, `error?`
- ✅ 写日志失败被 try/except 捕获, 不影响通知返回
- ✅ 单元测试 5/5 通过
- ✅ 完整测试: `tests/test_notifier.py` 26/26 通过
- ✅ 回归测试: `tests/api/test_alerts_webhook.py` 11/11 + `tests/test_escalation.py` 9/9 通过
- ✅ 调用方已更新: `alerts.py` 和 `escalation.py` 使用 `await notifier.send(payload, db=db)`

---

## 3. 测试阶段 (Testing Phase)
> **目标**: 使用测试计划验证功能。
> **⚠️ 执行铁律**: 必须严格按照 `05-test-plan.md` 中的列表顺序执行测试。**严禁跳跃**或乱序执行。

- **状态**: 🔄 进行中 (TC-CACHE 7/7 + TC-INSTANCE 2/2 + TC-DATA 5+4+5+2/2 = 25/25 + TC-OBS 9+7+8+6+6+6+7+6/6 = 80/80 + TC-INT 6/3 = 86/83)
- **进度**: 86 / ~83+ 测试通过（严禁没有修改 05-test-plan.md 测试状态就修改这里）
- **引用**: `docs/planning/v1.36-alert-observability/05-test-plan.md`
- **测试组**:
  - TC-CACHE-001 (7/7) ✅ - Phase 0
  - TC-INSTANCE-001 (2/2) ✅ - Phase 0
  - TC-DATA-001 (5/5) ✅ - Phase 1 (T1.1)
  - TC-DATA-002 (4/4) ✅ - Phase 1 (T1.2)
  - TC-DATA-003 (5/5) ✅ - Phase 1 (T1.3)
  - TC-DATA-004 (2/2) ✅ - Phase 1 (T1.4)
  - TC-OBS-000 (9/9) ✅ - Phase 2 (T2.1)
  - TC-OBS-001 (7/7) ✅ - Phase 2 (T2.2)
  - TC-OBS-002 (8/8) ✅ - Phase 2 (T2.3)
  - TC-OBS-003 (6/6) ✅ - Phase 2 (T2.4)
  - TC-OBS-004 (6/6) ✅ - Phase 2 (T2.5)
  - TC-OBS-005 (6/6) ✅ - Phase 2 (T2.6)
  - TC-OBS-006 (7/7) ✅ - Phase 2 (T2.7)
  - TC-OBS-007 (6/6) ✅ - Phase 2 (T2.8) **新增 2026-06-03**
  - TC-INT-001 (6/3) ✅ - Phase 3 (T3.1) **新增 2026-06-03, 3 个必选 + 3 个增强 (failure + mixed paths)**
  - TC-PERF-001 (8/8) ✅ - Phase 3 (T3.2) **新增 2026-06-03, 8 项性能基准**
  - TC-REG-001 (10/10) ✅ - Phase 4 (T4.1) **完成 2026-06-03, 126/126 核心测试通过**

---

## 4. 项目交付 (Project Delivery)
- **最终审查**: [ ] (待用户验收 2026-06-03)
- **用户验收**: [ ] (待用户决定下一步)

---

## 5. 累计产出文档

| # | 文档 | 用途 |
|:--|:---|:---|
| 1 | 01-requirements.md | 需求 (Round 3 终稿) |
| 2 | 01a-critique-r1.md | Round 1 自查 |
| 3 | 01b-research-r1.md | Round 1 调研 |
| 4 | 01c-simulation-r1.md | Round 1 推演 |
| 5 | 01d-critique-r2.md | Round 2 自查 |
| 6 | 01e-research-r2.md | Round 2 调研 |
| 7 | 01f-simulation-r2.md | Round 2 推演 |
| 8 | 01g-critique-r3.md | Round 3 自查 |
| 9 | 01h-research-r3.md | Round 3 调研 |
| 10 | 01i-simulation-r3.md | Round 3 推演 |
| 11 | 02-architecture.md | 架构 |
| 12 | 03-pre-flight-check.md | 前期准备 |
| 13 | 04-ralph-tasks.md | 任务 (17 P0) |
| 14 | 05-test-plan.md | 测试 (5 phase) |
| 15 | 06-learnings.md | 经验教训 |

**总文档**: 15 个, 涵盖完整 3 轮规划。
