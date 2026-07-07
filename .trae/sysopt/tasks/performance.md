# 性能维度任务清单 (Performance Tasks)

> 维度: performance | 负责人: - | 最后更新: 2026-06-29
> 评估来源: sysopt-performance assess 模式

## P0 任务 (必须立即处理)
- [x] PERF-P0-001: predict_fusion 同步等待 save_assessment_result + auto_create_review_task 阻塞响应 → 改为 fire-and-forget (model_predict.py:489) ✅ 2026-06-29
  - 新增 `_create_review_task` 异步函数 (独立 session 避免共享事务边界)
  - 新增 `_create_review_task_sync` fire-and-forget 包装 (与 `_save_assessment_sync` 一致)
  - predict_fusion 移除 `await save_assessment_result` 和内联 `await review_service.create_review_task`
  - 新增 16 个测试 (test_predict_fusion_fire_forget.py)，回归 86 个相关测试 + 302 个 API 测试全部通过
- [x] PERF-P0-002: predict_structured 串行执行 3 个实验性模型 → asyncio.gather 并行 + 异步任务 (model_engine.py:895) ✅ 2026-06-29
  - v121 和 v123 独立无依赖 (加载不同模型, 返回字段不冲突), 改为 asyncio.gather 并行
  - adapter 依赖 v123 的 experimental_external_score, 保持串行 await (在 v123 完成后执行)
  - 新增 10 个测试 (test_predict_structured_parallel.py), 覆盖源码静态检查+结果一致性+时序+异常隔离+集成
  - 回归 71 个相关测试通过 (5 个契约测试预先存在失败, git stash 验证与本次修改无关)

## P1 任务 (高优先级)
- [x] PERF-P1-001: observability API 拉取 10000 条 Python 聚合 → 强制时间范围 + SQL GROUP BY ✅ 2026-07-01
  - 新增 `_JsonExtract` + `_BucketExpr` 跨方言表达式 (SQLite json_extract + PG ::json->>, SQLite datetime() + PG to_timestamp)
  - 改造 6 个 `_compute_*` 函数 (trend/response_time/escalation/channel_stats/silence_hit_rate/am_sync)
  - 传输行数从 5000 降至几十/几百 (GROUP BY + COUNT/AVG/MIN/MAX)
  - 重写 test_observability_api.py (55 passed, mock → 真实 db_session 集成测试)
  - 重写 test_observability_perf.py (8 passed, P95 5s→500ms 目标达成)
  - 回归 observability 套件 127 passed (12 pre-existing 失败与本次改造无关)
- [x] PERF-P1-002: model_status 端点无缓存 → 加 30s Redis 缓存 ✅ 2026-07-02 (T-P2-011)
  - 在 app/api/v1/model_predict/status.py 新增 `_MODEL_STATUS_CACHE_KEY` + `_MODEL_STATUS_CACHE_TTL=30` 常量
  - 新增 `_get_cached_model_status()` 异步辅助函数 (cache miss 时计算并回填, cache_set 失败时降级为直接计算)
  - `model_status` 和 `model_performance_debug` 端点改用缓存读取
  - 复用 app/core/cache.py 的 `cache_get`/`cache_set` 工具 (带 Redis 断路器+内存 LRU+TTL 回退)
  - 新增 test_model_status_cache.py 6 个测试 (cache miss 回填 / cache hit 跳过计算 / cache_set 失败降级 / TTL 30s / cache key 稳定 / model_performance_debug 共享缓存)
  - 回归 259 tests passed (含 42 model_engine + 6 model_status_cache)
- [x] PERF-P1-003: observability cache TTL 固定 5min 雪崩风险 → TTL 加 ±60s 抖动 ✅ 2026-07-02 (T-P2-012, 在 PERF-P1-001 修复时一并完成)
  - app/api/v1/observability/__init__.py 新增 `CACHE_TTL_BASE=300` + `CACHE_TTL_JITTER=60` 常量
  - 新增 `_jittered_ttl()` 辅助函数 (`random.randint(-60, 60)` 抖动)
  - 所有 6 个 `cached_or_compute` 调用均使用 `ttl=_jittered_ttl()`
  - 实际 TTL ∈ [240, 360] 随机分布, 避免同一时刻大批 key 失效雪崩
- [x] PERF-P1-004: assess_structured 单次 5-7 次 DB 查询 → warning/intervention 异步化 ✅ 2026-07-01
  - 新增 `_warning_intervention_tasks` 任务集合 + `_log_warning_intervention_exception` 回调
  - 新增 `_trigger_warning_and_intervention` 异步函数 (独立 AsyncSessionLocal, 避免 session 共享)
  - 新增 `_schedule_warning_and_intervention` fire-and-forget 包装 (asyncio.ensure_future + GC 防护)
  - assess_structured 替换同步 `_check_warning_trigger` + `_auto_generate_intervention` 为 fire-and-forget
  - StructuredCollectResponse.warning_generated 改为 `bool | None` (None 表示 pending)
  - 新增 5 个 TestWarningInterventionFireAndForget 测试 + 2 个现有测试调整
  - 回归 228 tests passed (risk_service + user_data + resilience + predict_fusion + model_predict + fusion_enhanced + warning + intervention)
- [ ] PERF-P1-005: batch-export/excel 同步等待 → 添加异步版本
- [ ] PERF-P1-006: experiment/evaluate|compare 同步等待 ML → 改为 Celery 任务

## P2 任务 (中优先级)
- [ ] PERF-P2-001: start_training_job Celery 不可用时回退 daemon Thread → 移除回退返回 503
- [ ] PERF-P2-002: counselor list_my_users 子查询最新风险慢 → 增加 is_latest 标志位
- [ ] PERF-P2-003: risk_assessments 表无归档策略 → SQL 聚合 + 归档机制
- [ ] PERF-P2-004: get_risk_report/trend Python 内循环聚合 → SQL GROUP BY 聚合
- [ ] PERF-P2-005: OperationLog archive_old_logs 无自动调度 → beat_schedule 注册
- [ ] PERF-P2-006: 前端 ECharts 全量打包 → 按需 import
- [ ] PERF-P2-007: element-plus 整包合并单 chunk → chunkSizeWarningLimit=500
- [ ] PERF-P2-008: 前端未启用 brotli 预压缩 → vite-plugin-compression2
- [ ] PERF-P2-009: ML 推理无结果缓存 → 60s Redis 缓存 (输入哈希)

## P3 任务 (低优先级)
- [ ] PERF-P3-001: _inflight_futures 字典无清理 → TTL 清理
- [ ] PERF-P3-002: predict_physiological BN stats 异常重载 → 预加载校验
- [ ] PERF-P3-003: celery worker_prefetch_multiplier=1 → 拆分长短任务队列
- [ ] PERF-P3-004: ObservabilityCollector deque maxlen=1000 → 调大或批量 flush
- [ ] PERF-P3-005: /health 同步三重检查 → 标记 deprecated
- [ ] PERF-P3-006: 路由进度条 setInterval 200ms → requestAnimationFrame
- [ ] PERF-P3-007: predict_text_bert 无批处理 → micro-batching

---
## 进度统计
- P0: 2/2 ✅ PERF-P0-001/002
- P1: 4/6 ✅ PERF-P1-001/002/003/004
- P2: 0/9
- P3: 0/7
- **总计**: 6/24
