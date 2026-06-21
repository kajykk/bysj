# 04-ralph-tasks — v1.32-observability-complete

> **执行原则**: 按物理顺序执行。每完成标记 `[x]`。

---

## Phase 1: Grafana Dashboard (P0)

### T1.1 创建 Grafana dashboard.json

- [x] 路径: `monitoring/grafana/dashboard.json`
- [x] HTTP RPS / 延迟 / 错误率面板
- [x] WebSocket 活跃连接面板
- [x] 模型推理次数 / 延迟面板
- [x] 数据库连接池面板
- [x] 应用信息面板

---

## Phase 2: Prometheus Alert Rules (P0)

### T2.1 创建 alerts.yml

- [x] 路径: `monitoring/prometheus/alerts.yml`
- [x] HighErrorRate (Critical, >5%)
- [x] HighLatencyP99 (Warning, >1s)
- [x] ModelInferenceFailure (Critical, >10%)
- [x] ModelInferenceLatency (Warning, P95>2s)
- [x] WebSocketConnectionsHigh (Warning, >1000)
- [x] DatabasePoolExhausted (Critical, >90%)
- [x] ApplicationDown (Critical, 1m)
- [x] 3 个 info 级告警 (ElevatedErrorRate / SlowRequestRate / RequestVolumeSpike)
- [x] 5+ 记录规则 (rate5m, error_rate5m, p99_5m, p50_5m, model_inference)

---

## Phase 3: Sentry 集成增强 (P0)

### T3.1 升级 Sentry 性能追踪

- [x] `app/core/sentry.py` 修复 `push_scope` 弃用 → `new_scope`
- [x] 性能追踪 (`traces_sample_rate`, `profiles_sample_rate`)
- [x] FastApiIntegration + SqlalchemyIntegration
- [x] `tests/test_sentry.py` 4/4 通过

---

## Phase 4: 模型推理指标 (P0)

### T4.1 添加 track_model_inference 上下文管理器

- [x] `app/core/metrics.py` 新增 `track_model_inference`
- [x] 记录 total counter (success/error)
- [x] 记录 duration histogram
- [x] 异常自动吞掉 (不影响主流程)

### T4.2 接入 model_predict 端点

- [x] `predict_tabular` 包装
- [x] `predict_text` 包装
- [x] `predict_physiological` 包装
- [x] `predict_fusion` 包装

### T4.3 编写测试

- [x] `tests/test_model_inference_metrics.py` 5/5 通过
- [x] 验证 success/error 状态
- [x] 验证 duration 记录
- [x] 验证指标失败不影响主流程
- [x] 验证嵌套调用

---

## Phase 5: Admin Metrics Summary (P0)

### T5.1 创建 /api/v1/admin/metrics-summary 端点

- [x] `app/api/v1/admin_metrics.py` 新建
- [x] router prefix 修正 (避免双前缀)
- [x] 收集 HTTP 指标 (total / 5xx / top_paths)
- [x] 收集 WebSocket 指标
- [x] 收集 DB 池指标
- [x] 收集模型推理指标
- [x] 注册到 `app/api/v1/__init__.py`

### T5.2 版本字符串同步

- [x] `metrics.py` 中 `app_info.version` 更新到 v1.32
- [x] `admin_metrics.py` 返回 `version` 更新到 v1.32

### T5.3 编写测试

- [x] `tests/api/test_admin_metrics.py` 3/3 通过
- [x] 验证 admin 角色要求
- [x] 验证 HTTP stats 收集
- [x] 验证响应结构

---

## Phase 6: Audit-Logs 合规端点 (P1)

### T6.1 AdminService.list_audit_logs

- [x] `app/services/admin_service.py` 新增
- [x] 多 action_type 过滤
- [x] target_type 过滤
- [x] compliance 统计 (action_breakdown, retention_days, earliest/latest)

### T6.2 /api/v1/admin/audit-logs 端点

- [x] `app/api/v1/admin.py` 新增
- [x] page_size 默认 50, max 200
- [x] 接受 action_types 列表参数

### T6.3 编写测试

- [x] `tests/api/test_audit_logs_api.py` 5/5 通过
- [x] 验证 admin 可查询
- [x] 验证非 admin 被拒
- [x] 验证多 action_type 过滤
- [x] 验证 target_type 过滤
- [x] 验证分页

---

## Phase 7: 回归测试 (P0)

### T7.1 核心测试组

- [x] tests/api/test_metrics.py 全过
- [x] tests/test_observability_service.py 全过
- [x] tests/test_model_inference_metrics.py 全过
- [x] tests/api/test_admin_metrics.py 全过
- [x] tests/api/test_audit_logs_api.py 全过
- [x] tests/api/test_operation_logs_api.py 全过
- [x] tests/test_sentry.py 全过 (无 push_scope 警告)

---

## 进度统计

- 总任务: 7 phases
- P0: 6 phases
- P1: 1 phase
- 完成: **7/7 (100%)**
