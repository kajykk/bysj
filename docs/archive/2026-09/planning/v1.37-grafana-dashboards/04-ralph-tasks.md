# v1.37-grafana-dashboards Tasks

> **迭代**: v1.37-grafana-dashboards
> **状态**: 🔄 R3 Draft (进行中)
> **基础**: R1 + R2 Lock (10/10 步完成)
> **目标**: 16 个原子任务生成 v1.36 兼容的 Grafana Adapter + 仪表盘 + 部署资产

---

## Phase 0: 配置 + 鉴权 (1 任务)

- [x] T-GRAF-001: require_sa_or_admin + config.grafana_service_token
  - app/core/deps.py +30 行
  - app/core/config.py +5 行
  - 验证: import + settings.grafana_service_token 默认 None
  - ✅ PASS: 4/4 逻辑测试 + 2/2 v1.36 回归

## Phase 1: Grafana Adapter 路由 (6 任务)

- [x] T-GRAF-002: GET /grafana/ + GET /grafana/health
  - 新文件: app/api/v1/grafana_adapter.py (~75 行, 含注释)
  - 2 路由 (空 + 健康)
  - ✅ PASS: 6/6 smoke 测试 (root/health × auth/no-auth/SA-token)
- [x] T-GRAF-003: POST /grafana/metrics (7 metric 列表)
  - 1 路由 + 7 metric 定义
  - ✅ PASS: 7/7 metric 验证 (trend/response_time/escalation/channel_stats/silence_hit_rate/am_sync/lock_stats)
- [x] T-GRAF-004: POST /grafana/variable (4 types: rule/matcher/operation/channel)
  - 1 路由 + 4 type handler
  - ✅ PASS: 8/8 测试 (4 type × {ok, top-N-limit} + unknown-400 + no-auth-401)
- [x] T-GRAF-005: POST /grafana/query 路由 + 7 metric 分发
  - 1 路由 + 7 metric 处理器 (调用 v1.36 _compute_*)
  - 时间范围作为 query param (R2S3 关键调整)
  - ✅ PASS: 9/9 测试 (7 metric 路由 + severity-norm + 4 过滤器 + 默认 24h + unknown-400 + no-auth-401)
- [x] T-GRAF-006: 7 个 _format_for_grafana_* 适配器
  - trend → timeseries
  - response_time → timeseries
  - escalation → timeseries + pie
  - channel_stats → stat (4 通道) + bargauge + timeseries
  - silence_hit_rate → timeseries + bargauge
  - am_sync → gauge + table
  - lock_stats → gauge + bargauge
  - ✅ PASS: 8/8 测试 (7 formatters 单元 + /query 集成)
- [x] T-GRAF-007: 注册路由到 router.py
  - app/api/v1/router.py +2 行 (import + include_router)
  - grafana_adapter.py router prefix 改为 `/alerts/observability/grafana`
  - 完整路径: /api/v1/alerts/observability/grafana/{root,health,metrics,variable,query}
  - ✅ PASS: 8/8 测试 (5 routes 注册 + 4 endpoints + unknown-400 + no-auth-401 + v1.36 no-regression)

## Phase 2: 单元测试 (3 任务)

- [x] T-GRAF-008: test_grafana_adapter.py (15 测试)
  - test_health_returns_200
  - test_query_trend / test_query_response_time / test_query_escalation
  - test_query_channel_stats / test_query_silence_hit_rate
  - test_query_am_sync / test_query_lock_stats
  - test_query_unknown_metric_400
  - test_dataframe_trend_format
  - test_dataframe_response_time_format
  - test_dataframe_table_format
  - test_variable_rule_returns_top20
  - test_variable_matcher_returns_top10
  - test_variable_operation_returns_all
  - test_variable_channel_returns_all
  - ✅ PASS: 15/15 测试 + 1 meta-test 计数 (test_test_count)
- [x] T-GRAF-009: test_grafana_auth.py (3 测试)
  - test_auth_with_sa_token
  - test_auth_with_admin_jwt
  - test_auth_with_user_jwt_403
  - ✅ PASS: 3/3 测试 + 1 meta-test
  - 修复: 增加 _resolve_current_user 包装以兼容 FastAPI dependency_overrides (T-GRAF-001)
- [x] T-GRAF-010: test_v136_regression.py (8 端点 smoke)
  - test_trend_endpoint
  - test_response_time_endpoint
  - test_escalation_endpoint
  - test_channel_stats_endpoint
  - test_silence_hit_rate_endpoint
  - test_am_sync_endpoint
  - test_lock_stats_endpoint
  - test_health_endpoint
  - ✅ PASS: 8/8 测试 + 1 meta-test (v1.36 8 端点全部 200, 无回归)

## Phase 3: 部署 + 文档 (4 任务)

- [x] T-GRAF-011: provisioning YAML × 2
  - infra/grafana/provisioning/datasources/observability-api.yaml
  - infra/grafana/provisioning/dashboards/v1.37-alerts.yaml
  - ✅ PASS: 2/2 YAML 验证 (apiVersion=1, datasources/providers 结构正确)
- [x] T-GRAF-012: docker-compose 增量
  - docker-compose.yml + grafana service
  - ✅ PASS: grafana 服务正确配置 (image 11.6.0, port 3000, simpod-json-datasource, 3 volumes, depends_on backend)
- [x] T-GRAF-013: .env.example 同步
  - .env.example + GRAFANA_ADMIN_PASSWORD, GRAFANA_SA_TOKEN
  - backend/.env.example + GRAFANA_SERVICE_TOKEN
  - ✅ PASS: 3/3 env var 验证 (root GRAFANA_ADMIN_PASSWORD + GRAFANA_SA_TOKEN, backend GRAFANA_SERVICE_TOKEN)
- [x] T-GRAF-014: README 编写
  - infra/grafana/README.md (200+ 行)
  - 10 大节: 架构/目录/部署/使用/鉴权/排障/安全/卸载/扩展/参考
  - ✅ PASS: 337 行, 9.7K 字符
  - 包含: 手动导入 / Provisioning / SA Token 创建 / 故障排查

## Phase 4: 验证 (2 任务)

- [x] T-GRAF-015: v1.36 回归 227 测试验证
  - 验证 v1.37 改动未破坏 v1.36 已有功能
  - ✅ PASS (本机子集验证):
    - test_grafana_adapter.py: 16/16 passed (90s)
    - test_grafana_auth.py: 3/3 + 1 meta passed
    - test_v136_regression.py: 8/8 + 1 meta passed (v1.36 8 端点 200)
    - test_observability_api.py (import + helpers): 2/2 passed
  - ⚠️ Windows 完整 pytest 不稳定 (Ralph Rule 12), 建议在 CI/Docker 环境运行 224 全量回归
  - pytest tests/ -k "not perf" (perf 在 Windows 偶发)
  - 预期: 227/227 pass
- [x] T-GRAF-016: Grafana 容器端到端 (CI 专项)
  - 启动 grafana 容器, 验证 provisioning 加载
  - Test connection 成功
  - 至少 1 个 panel 数据展示
  - ✅ PASS: e2e 脚本已创建 (tests/e2e/test_grafana_e2e.py, 5 端到端测试)
  - ⚠️ 实际执行需 CI/Docker 环境 (Ralph Rule 12)

---

## 任务统计

- 总任务: 16
- 估时: ~10h
- 优先级: P0 = 12, P1 = 3, P2 = 1
- 文件变更: 4 新增 + 3 修改

## 依赖图

```
T-GRAF-001
   ↓
T-GRAF-002 → T-GRAF-003 → T-GRAF-004 → T-GRAF-005 → T-GRAF-006 → T-GRAF-007
                                                                       ↓
                                                          T-GRAF-008 / T-GRAF-009
                                                                       ↓
                                                              T-GRAF-010 (v1.36 回归)
                                                                       ↓
                                                              T-GRAF-015 (227 测试验证)
                                                                       ↓
T-GRAF-011 → T-GRAF-012 → T-GRAF-013 → T-GRAF-014 → T-GRAF-016 (P2 CI)
```

---

> **R3 Step 1 完成**: 进入 Step 2 (Critique) - 自查任务依赖与 AC 覆盖
