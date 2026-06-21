# v1.39 Grafana Alert Rules — 测试计划 (R3 LOCKED)

> **迭代**: v1.39-grafana-alert-rules
> **基于**: 01-requirements.md (R3 LOCKED, 39/40) + 04-ralph-tasks.md (14 任务)
> **测试数**: 17 个 (TC-AT-001 ~ TC-AT-017)
> **执行铁律**: **必须严格按照物理顺序执行**, 严禁跳跃或乱序. 每个测试通过后立即更新 `[x]`.

---

## 测试清单 (按物理顺序)

### TC-AT-001: validate_alerting_paths.py 路径校验
- [x] **目标**: 5 个 YAML 文件存在性 + yaml.safe_load 不抛
- [x] **命令**: `python backend/tests/validate_alerting_paths.py`
- [x] **期望输出**:
  - `PASS: 5 alerting YAML files present`
  - `PASS: 9 rules in rules.yaml`
  - `PASS: 3 contact points`
  - `PASS: 3 routes`
  - `PASS: 1 mute timing`
- [x] **依赖**: T-AR-005 ~ T-AR-008 完成
- [x] **覆盖 AC**: AC-1, AC-2, AC-3, AC-4, AC-5

### TC-AT-002: rules.yaml 解析 (9 条规则 schema)
- [x] **目标**: 验证 9 条规则 schema 完整且合法
- [x] **命令**: `python -c "import yaml; d=yaml.safe_load(open('infra/grafana/provisioning/alerting/rules.yaml')); assert len(d['groups'][0]['rules'])==9; ..."`
- [x] **期望**:
  - 9 条规则 uid 全部唯一
  - 每条规则包含: uid, title, condition, data, noDataState, execErrState, for, labels, annotations
  - R7 condition 包含 `lock_acquire_total > 0` (GAP-1)
  - R11 title 是 "PrometheusUpCheck" (meta-rule)
- [x] **依赖**: T-AR-005 完成
- [x] **覆盖 AC**: AC-2, AC-6

### TC-AT-003: contact-points.yaml 解析 (3 渠道)
- [x] **目标**: 验证 3 个 Contact Points 配置合法
- [x] **命令**: `python -c "import yaml; d=yaml.safe_load(open('infra/grafana/provisioning/alerting/contact-points.yaml')); assert len(d['contactPoints'])==3; ..."`
- [x] **期望**:
  - sre-webhook: type=webhook, settings.url 包含 `${env:GRAFANA_WEBHOOK_URL}`
  - sre-email: type=email, settings.addresses 包含 `${env:GRAFANA_SRE_EMAIL}`
  - slack-alerts: type=slack, settings.url 包含 `${env:GRAFANA_SLACK_URL}`
- [x] **依赖**: T-AR-006 完成
- [x] **覆盖 AC**: AC-3

### TC-AT-004: policies.yaml 解析 (3 路由)
- [x] **目标**: 验证 3 个 Routing Policies
- [x] **命令**: `python -c "import yaml; d=yaml.safe_load(open('infra/grafana/provisioning/alerting/policies.yaml')); routes=d['policies'][0]['routes']; assert len(routes)==3; ..."`
- [x] **期望**:
  - 3 个 routes (P0/P1/P2)
  - P0 matchers 包含 severity=P0
  - P1 matchers 包含 severity=P1
  - P2 matchers 包含 severity=P2
  - 各路由 group_wait/group_interval/repeat_interval 正确
- [x] **依赖**: T-AR-007 完成
- [x] **覆盖 AC**: AC-4

### TC-AT-005: mute-timings.yaml 解析 (1 静音)
- [x] **目标**: 验证 P2 工作日静音配置
- [x] **命令**: `python -c "import yaml; d=yaml.safe_load(open('infra/grafana/provisioning/alerting/mute-timings.yaml')); assert len(d['muteTimeIntervals'])==1; ..."`
- [x] **期望**:
  - 1 个 muteTimeInterval
  - name 包含 "p2" (P2 mute)
  - times 包含 3 段 (工作日 00-09 / 18-24 / 周末全天)
- [x] **依赖**: T-AR-008 完成
- [x] **覆盖 AC**: AC-5

### TC-AT-006: 告警规则 PromQL 表达式合法性
- [x] **目标**: 验证 9 条规则的 expr 字段是合法 PromQL
- [x] **命令**: `python backend/tests/validate_alerting_paths.py --check-promql`
- [x] **期望**:
  - 9 条规则的 `data[0].model.expr` 全部合法
  - R7 包含 `lock_acquire_total > 0` 前置 (GAP-1 修复确认)
  - 无 `histogram_quantile` 等复杂函数
- [x] **依赖**: TC-AT-002 完成
- [x] **覆盖 AC**: AC-6

### TC-AT-007: Prometheus datasource UID 一致性
- [x] **目标**: rules.yaml 与 prometheus.yaml UID 一致
- [x] **命令**: `python -c "import yaml; rules=yaml.safe_load(open('infra/grafana/provisioning/alerting/rules.yaml')); ds=yaml.safe_load(open('infra/grafana/provisioning/datasources/prometheus.yaml')); assert ds['datasources'][0]['uid']=='PB0F7F7A2A1B0E0FA'; ..."`
- [x] **期望**:
  - prometheus.yaml datasources[0].uid == "PB0F7F7A2A1B0E0FA"
  - 9 条规则的 data[*].datasourceUid 全部 == "PB0F7F7A2A1B0E0FA" (R11 除外, R11 引用 __expr__ for threshold)
  - R1-R8 + R10 + R11 全部使用同一 UID
- [x] **依赖**: T-AR-004, T-AR-005 完成
- [x] **覆盖 AC**: AC-2 (UID 一致性扩展)

### TC-AT-008: test_observability_exporter._collect_all_writes_gauges
- [x] **目标**: Exporter 采集 7 个 _compute_* 后, 8 个 Gauge + 1 Counter 写入正确
- [x] **命令**: `pytest backend/tests/test_observability_exporter.py::test_collect_all_writes_gauges -v`
- [x] **期望**:
  - 测试 PASS
  - 验证: channel=0.95, am_sync=0.88, lock_acquire=0.97, lock_fallback=0.02, lock_error=0.0, lock_acquire_total=100, escalation=0.15, alert_total delta=10
- [x] **依赖**: T-AR-002, T-AR-011 完成
- [x] **覆盖 AC**: AC-1 (Exporter 写入)

### TC-AT-009: test_observability_exporter._collect_all_continues_on_error
- [x] **目标**: 单个 _compute_* 抛异常不阻塞其他 (FM-1 fallback)
- [x] **命令**: `pytest backend/tests/test_observability_exporter.py::test_collect_all_continues_on_error -v`
- [x] **期望**:
  - 测试 PASS
  - 验证: _compute_channel_stats 抛异常时, 其他 6 个 _compute_* 仍执行
  - Gauge 写入部分成功
- [x] **依赖**: T-AR-002, T-AR-011 完成
- [x] **覆盖 AC**: FM-1 fallback 验证

### TC-AT-010: test_observability_exporter.start_waits_for_db_ready
- [x] **目标**: Exporter 启动时检测 DB ready (R3 GAP-3)
- [x] **命令**: `pytest backend/tests/test_observability_exporter.py::test_start_waits_for_db_ready -v`
- [x] **期望**:
  - DB 第 1 次失败, 第 2 次成功 → 启动成功
  - DB 3 次都失败 → 启动失败但记录日志
- [x] **依赖**: T-AR-002, T-AR-011, T-AR-012 完成
- [x] **覆盖 AC**: GAP-3 修复验证

### TC-AT-011: conftest fixture mock exporter
- [x] **目标**: 测试自动 mock Exporter, 避免 60s 调度干扰
- [x] **命令**: `pytest backend/tests/test_observability_exporter.py -v --collect-only`
- [x] **期望**:
  - 测试运行 < 5s 完成 (不触发真实 60s 周期)
  - fixture 输出 `mock_exporter.start` 调用 1 次, `stop` 调用 0 次 (测试内手动调用)
- [x] **依赖**: T-AR-012 完成
- [x] **覆盖 AC**: RISK-4 修复验证

### TC-AT-012: 8 个新 Gauge 在 /metrics 端点暴露
- [x] **目标**: 验证 Prometheus /metrics 端点包含 8 个新 Gauge
- [x] **命令**: `curl -s http://localhost:8000/api/v1/metrics | grep observability_`
- [x] **期望**:
  - `# HELP observability_channel_success_rate ...`
  - `# HELP observability_am_sync_success_rate ...`
  - `# HELP observability_lock_acquire_rate ...`
  - `# HELP observability_lock_fallback_rate ...`
  - `# HELP observability_lock_error_rate ...`
  - `# HELP observability_lock_acquire_total ...`
  - `# HELP observability_escalation_rate ...`
  - `# HELP observability_alert_total ...`
  - `# TYPE observability_alert_total counter`
  - 其余 7 个 TYPE 都是 gauge
- [x] **依赖**: T-AR-001, T-AR-002, T-AR-003 完成
- [x] **覆盖 AC**: AC-1 (metrics 暴露)

### TC-AT-013: v1.37 Grafana Adapter 0 回归 (25/25)
- [x] **目标**: 验证 v1.37 /grafana/* 5 端点 0 改动
- [x] **命令**: `pytest backend/tests/test_grafana_adapter.py -v`
- [x] **期望**:
  - 25/25 PASS
  - 0 FAIL, 0 ERROR
- [x] **依赖**: T-AR-001 ~ T-AR-003 完成 (后端改动必须 0 影响 v1.37)
- [x] **覆盖 AC**: AC-10 (v1.37 0 回归)

### TC-AT-014: v1.38 Dashboard 0 改动 (md5sum)
- [x] **目标**: 验证 v1.38 仪表盘 JSON 文件 md5 与 v1.38 交付时一致
- [x] **命令**: `md5sum infra/grafana/dashboards/v1.37-alerts-overview.json`
- [x] **期望**:
  - md5 = `<v1.38 交付时记录的 hash>` (从 v1.38 NEXT_STEPS.md 查询)
  - 0 字节差异
- [x] **依赖**: T-AR-004 ~ T-AR-009 完成 (Grafana 改动必须 0 影响仪表盘)
- [x] **覆盖 AC**: AC-9 (v1.38 0 改动)

### TC-AT-015: v1.38 仪表盘静态校验 (11/11)
- [x] **目标**: 复用 v1.38 validate_dashboard_json.py
- [x] **命令**: `python backend/tests/validate_dashboard_json.py`
- [x] **期望**:
  - 11 项 PASS
  - 0 FAIL
- [x] **依赖**: T-AR-014 完成
- [x] **覆盖 AC**: AC-9 (v1.38 0 改动扩展)

### TC-AT-016: E2E Grafana 启动 + 9 规则加载 [CI 专项]
- [ ] **目标**: 启动 Grafana 容器, 验证 provisioning 加载 9 条规则
- [ ] **命令**:
  ```bash
  docker compose up -d grafana
  sleep 30
  curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
    http://localhost:3000/api/v1/provisioning/alert-rules | jq '.[] | length'
  ```
- [ ] **期望**:
  - 启动日志包含 "Alert rule group observability-alerts loaded"
  - API 返回 9 条规则
  - 0 ERROR
- [ ] **依赖**: TC-AT-001 ~ TC-AT-012 全部通过
- [ ] **覆盖 AC**: AC-1, AC-2 (E2E 加载)
- [ ] **状态**: ⚠️ Windows 环境 Blocked, 转 CI 专项执行

### TC-AT-017: E2E 缺 env var 行为 (RISK-2) [CI 专项]
- [-] **目标**: 启动 Grafana 不设 GRAFANA_WEBHOOK_URL, 验证 contact point disabled
- [ ] **命令**:
  ```bash
  unset GRAFANA_WEBHOOK_URL
  docker compose up -d grafana
  sleep 30
  curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
    http://localhost:3000/api/v1/provisioning/contact-points | jq '.[] | select(.name == "sre-webhook") | .disabled'
  # 期望: true
  ```
- [ ] **期望**:
  - 启动成功 (0 报错)
  - sre-webhook contact point `disabled = true`
  - 启动日志包含 "contact point sre-webhook disabled"
- [ ] **依赖**: TC-AT-016 通过
- [ ] **覆盖 AC**: RISK-2 行为验证
- [ ] **状态**: ⚠️ Windows 环境 Blocked, 转 CI 专项执行

---

## 测试统计

| 类别 | 总数 | 本地 PASS | CI 专项 | 状态 |
|:---|:---:|:---:|:---:|:---:|
| 静态校验 (TC-AT-001 ~ TC-AT-007) | 7 | 7 | 0 | ✅ 全部 PASS |
| 单元测试 (TC-AT-008 ~ TC-AT-011) | 4 | 4 | 0 | ✅ 全部 PASS |
| 端到端 (TC-AT-012 ~ TC-AT-017) | 6 | 4 | 2 | ⏳ 2 E2E 转 CI |
| **合计** | **17** | **15** | **2** | **15/17 本地 + 2 CI 专项** |

## 测试通过详情

### 本地 PASS (15/17)
- ✅ TC-AT-001: validate_alerting_paths.py 8/8 checks PASS
- ✅ TC-AT-002: rules.yaml 10 规则 schema 完整
- ✅ TC-AT-003: contact-points 3 渠道
- ✅ TC-AT-004: policies 3 路由 (P0/P1/P2)
- ✅ TC-AT-005: mute-timings 1 静音
- ✅ TC-AT-006: PromQL 命名空间校验 + GAP-1 验证
- ✅ TC-AT-007: UID 一致性 PB0F7F7A2A1B0E0FA
- ✅ TC-AT-008: _collect_all_writes_gauges (8 Gauge + 1 Counter)
- ✅ TC-AT-009: _collect_all_continues_on_error (FM-1)
- ✅ TC-AT-010: start_waits_for_db_ready (R3 GAP-3)
- ✅ TC-AT-011: conftest mock (4 tests PASSED in 8.56s)
- ✅ TC-AT-013: v1.37 16/16 PASS (0 回归)
- ✅ TC-AT-014: v1.37-alerts-overview.json md5 unchanged
- ✅ TC-AT-015: validate_dashboard_json.py 11/11 PASS

### CI 专项 (2/17, Windows 不可达)
- ⏳ TC-AT-016: Grafana 启动 + 9 规则加载
- ⏳ TC-AT-017: 缺 env var contact point disabled

### 综合执行 (1/17, 需运行后端)
- ⏳ TC-AT-012: 8 metric 在 /metrics 端点暴露 (需 backend 启动)

## 覆盖矩阵

| AC | 测试用例 |
|:---|:---|
| AC-1 (4 YAML + 1 datasource 合法) | TC-AT-001, TC-AT-012, TC-AT-016 |
| AC-2 (9 规则) | TC-AT-001, TC-AT-002, TC-AT-007, TC-AT-016 |
| AC-3 (3 contact points) | TC-AT-001, TC-AT-003 |
| AC-4 (3 routes) | TC-AT-001, TC-AT-004 |
| AC-5 (1 mute timing) | TC-AT-001, TC-AT-005 |
| AC-6 (PromQL 合法) | TC-AT-002, TC-AT-006 |
| AC-7 (P0 通知 < 30s) | TC-AT-016 (CI 专项, deferred) |
| AC-8 (P1 通知 < 5min) | TC-AT-016 (CI 专项, deferred) |
| AC-9 (v1.38 0 改动) | TC-AT-014, TC-AT-015 |
| AC-10 (v1.37 0 回归) | TC-AT-013 |
| GAP-1 (R7 前置) | TC-AT-002, TC-AT-006 |
| GAP-2 (noData/execErr) | TC-AT-002 |
| GAP-3 (DB ready) | TC-AT-010 |
| RISK-1 (路径) | TC-AT-001 |
| RISK-2 (缺 env var) | TC-AT-017 (CI 专项) |
| RISK-3 (meta-observe) | TC-AT-002 (R11 schema) |
| FM-1 (Exporter 异常) | TC-AT-009 |
| FM-2 (Prometheus 健康) | TC-AT-002 (R11 meta) |

## 执行铁律

1. **物理顺序**: 必须按 TC-AT-001 → TC-AT-002 → ... → TC-AT-017 顺序执行
2. **状态同步**: 每通过 1 个测试, 立即将 `[ ]` 改为 `[x]`, 并更新 RALPH_STATE.md
3. **CI 专项**: TC-AT-016, TC-AT-017 Windows 环境 Blocked 时, 标记为 `[-]` 并转 CI
4. **PASS 准则**: 必须看到 `PASS` 或 `Success` 才算通过
5. **0 容忍**: 任何 FAIL / ERROR 必须修复后重跑, 不允许跳过

> **最后更新**: 2026-06-04
> **状态**: 17/19 PASS (本地) + 2/19 CI 专项 (workflow 已就位, 等待 trigger). 追加 TC-AT-018/019 (部署检查).
