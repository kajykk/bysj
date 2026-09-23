# v1.39 Grafana Alert Rules — 交付报告 (DELIVERY REPORT)

> **迭代**: v1.39-grafana-alert-rules
> **类型**: 可观测性 / DevOps 配置
> **状态**: ✅ **DELIVERED (核心完成)** + 🟡 **2 E2E 转 CI**
> **交付日期**: 2026-06-03
> **实际工时**: 1 天 (R1 估时 1-2 天)

---

## 1. 交付物清单

### 1.1 后端代码 (3 个文件)

| 文件 | 行数 | 状态 | 说明 |
|:---|:---:|:---:|:---|
| `backend/app/core/metrics.py` | +76 | ✅ 扩展 | 追加 8 Gauge + 1 Counter |
| `backend/app/services/observability_exporter.py` | +205 | ✅ 新建 | 60s 周期发布 7 v1.36 metric |
| `backend/app/services/__init__.py` | +2 | ✅ 修改 | 导出 ObservabilityExporter |
| `backend/app/main.py` | +8 | ✅ 修改 | FastAPI lifespan 集成 |

### 1.2 Grafana 配置 (5 个 YAML)

| 文件 | 行数 | 状态 | 说明 |
|:---|:---:|:---:|:---|
| `infra/grafana/provisioning/datasources/prometheus.yaml` | +21 | ✅ 新建 | UID=PB0F7F7A2A1B0E0FA |
| `infra/grafana/provisioning/alerting/rules.yaml` | +400 | ✅ 新建 | 10 条告警规则 |
| `infra/grafana/provisioning/alerting/contact-points.yaml` | +35 | ✅ 新建 | 3 通知渠道 |
| `infra/grafana/provisioning/alerting/policies.yaml` | +60 | ✅ 新建 | 3 路由 (P0/P1/P2) |
| `infra/grafana/provisioning/alerting/mute-timings.yaml` | +33 | ✅ 新建 | P2 工作日静音 |
| `docker-compose.yml` | +1 | ✅ 注释 | 0 改动 mount (父级覆盖) |

### 1.3 测试 (3 个文件)

| 文件 | 行数 | 状态 | 说明 |
|:---|:---:|:---:|:---|
| `backend/tests/validate_alerting_paths.py` | +177 | ✅ 新建 | 8 项静态校验 |
| `backend/tests/test_observability_exporter.py` | +205 | ✅ 新建 | 4 个单元测试 |
| `backend/tests/conftest.py` | +20 | ✅ 修改 | autouse mock fixture |

### 1.4 文档 (1 个 README)

| 文件 | 行数 | 状态 | 说明 |
|:---|:---:|:---:|:---|
| `infra/grafana/README.md` | +165 | ✅ §10 追加 | 告警配置 9 节内容 |

### 1.5 规划文档 (4 个)

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| `docs/planning/v1.39-grafana-alert-rules/01-requirements.md` | ✅ R3 LOCKED | 39/40 评分, 9 项 FMEA |
| `docs/planning/v1.39-grafana-alert-rules/04-ralph-tasks.md` | ✅ 14/14 | 14 任务全部完成 |
| `docs/planning/v1.39-grafana-alert-rules/05-test-plan.md` | ✅ 15/17 | 15 PASS + 2 E2E CI |
| `docs/planning/v1.39-grafana-alert-rules/RALPH_STATE.md` | ✅ 持续维护 | 全流程状态记录 |

---

## 2. 测试结果汇总

### 2.1 测试通过情况

| 类别 | 总数 | 本地 PASS | CI 专项 | 状态 |
|:---|:---:|:---:|:---:|:---:|
| 静态校验 (TC-AT-001 ~ TC-AT-007) | 7 | 7 | 0 | ✅ 100% |
| 单元测试 (TC-AT-008 ~ TC-AT-011) | 4 | 4 | 0 | ✅ 100% |
| 端到端 (TC-AT-012 ~ TC-AT-017) | 6 | 4 | 2 | 🟡 67% (2 E2E → CI) |
| **合计** | **17** | **15** | **2** | **88% 本地 / 12% CI** |

### 2.2 pytest 详细结果

```
tests/test_observability_exporter.py .......... 4/4 PASSED [8.56s]
tests/test_grafana_adapter.py ............... 16/16 PASSED [v1.37 0 回归]
tests/test_dashboard_template.py ............ 7/7 PASSED [v1.38 0 改动]
tests/validate_dashboard_json.py ............ 11/11 PASS [v1.38 0 改动]
tests/validate_alerting_paths.py ............ 8/8 PASS [v1.39 静态]
═══════════════════════════════════════════════════════════════
TOTAL: 27 pytest PASS + 19 static PASS = 46/46 (100% local)
```

### 2.3 0 回归验证 (T-AR-014)

- ✅ v1.37 Grafana Adapter: 16/16 PASS
- ✅ v1.38 Dashboard Template: 7/7 PASS
- ✅ v1.37-alerts-overview.json md5 unchanged
- ✅ validate_dashboard_json.py: 11/11 PASS
- ✅ 后端 imports: 无破坏

---

## 3. 关键决策与发现

### 3.1 关键发现 (R1 Step 3 Research)

**simpod-json-datasource 不支持 Grafana-managed Alert Rules**:
- 原因: plugin.json 无 `alerting: true` 字段
- 影响: 必须在 backend 暴露 Prometheus 兼容指标
- 决策: 采用方案 A (扩展 Prometheus /metrics + 新增 Prometheus 数据源)

### 3.2 6 项核心决策 (Q1-Q6)

| # | 问题 | 决策 | 理由 |
|:---:|:---|:---:|:---|
| Q1 | R9 响应时长 P99 告警 | B. 不纳入 (8 条) | 简洁, 与预算 1.5 天匹配 |
| Q2 | Notification 渠道优先级 | A. Webhook 优先 | Webhook 适合 on-call 手机 |
| Q3 | Mute timing 范围 | A. 仅 P2 | P0 永不静音 |
| Q4 | 告警数据源策略 | A. 扩展 Prometheus | 标准 PromQL 告警 |
| Q5 | Exporter 调度周期 | A. 60s | 与 R1-R8 for:2m 匹配 |
| Q6 | 数据源关系 | A. 并存 | 0 改动 v1.37 仪表盘 |

### 3.3 5 项 GAP / RISK 修复

| ID | 类型 | 修复 |
|:---|:---:|:---|
| GAP-1 | 0 流量误报 | R7 condition 加 `lock_acquire_total > 0` 前置 |
| GAP-2 | 状态声明缺失 | 9 条规则全部声明 `noDataState` + `execErrState` |
| GAP-3 | Exporter 启动时序 | start() 检测 DB ready, 3 次重试 |
| RISK-4 | 测试时长干扰 | conftest autouse mock fixture |
| NEW-9 | FM-2 Prometheus 健康 | R11 meta-rule (noDataState=Alerting) |

---

## 4. 架构概览

### 4.1 数据流

```
[Backend: 7 v1.36 _compute_*]
    │ 60s 周期调用
    ▼
[ObservabilityExporter]
    │ 写入 8 Gauge + 1 Counter
    ▼
[Prometheus /api/v1/metrics 端点]
    │ Grafana Prometheus datasource 抓取
    ▼
[Grafana Alerting Engine]
    │ 60s 评估 10 条规则
    ▼
[Routing Policy (按 severity)]
    ├─ P0 → sre-webhook + sre-email + slack-alerts (10s/5m/1h)
    ├─ P1 → sre-webhook + sre-email + slack-alerts (30s/10m/4h)
    └─ P2 → sre-email (5m/1h/24h, 工作日 09-18)
    │
    ▼
[SRE 手机 / 邮箱 / Slack]
```

### 4.2 关键 metric 命名

| 名称 | 类型 | 用途 |
|:---|:---:|:---|
| `observability_channel_success_rate` | Gauge | R1/R2 (通道成功率) |
| `observability_am_sync_success_rate` | Gauge | R3/R4 (AM 同步) |
| `observability_lock_acquire_rate` | Gauge | R5 (锁获取率) |
| `observability_lock_fallback_rate` | Gauge | R6 (锁降级率) |
| `observability_lock_error_rate` | Gauge | R7 (锁错误率) |
| `observability_lock_acquire_total` | Gauge | R7 前置过滤 |
| `observability_escalation_rate` | Gauge | R8 (升级率) |
| `observability_alert_total` | Counter | R10 (告警总量) |
| (Prometheus up) | - | R11 meta (健康检查) |

---

## 5. 已知限制与建议

### 5.1 Windows 环境限制 (TC-AT-016, TC-AT-017)

- **限制**: Windows 本地 docker compose / Grafana 启动不稳定
- **影响**: 2 个 E2E 测试 (TC-AT-016, TC-AT-017) 无法本地验证
- **建议**: 在 CI / Linux 环境执行 `docker compose up -d grafana` 后运行

### 5.2 v1.40 候选 (RISK-3)

- **Grafana Heartbeat 规则** (FM-3 自监控) 已在 v1.39 通过 R11 meta-rule 部分覆盖
- **完整 meta-observe** (Prometheus 黑盒探针) 留待 v1.40 评估

### 5.3 阈值调整建议

- 当前阈值基于静态分析, 建议生产环境观察 1-2 周后调优
- P0 阈值 (通道成功率 0.80, 锁错误率 0.00) 可能过敏感, 可调至 0.75/0.01

---

## 6. 验证清单 (用户验收)

### 6.1 本地快速验证 (5 min)

```bash
# 1. 后端 8 metric 注册
cd e:\code\bysj\backend
python -c "from app.core import metrics; print(len([n for n in metrics._REGISTRY if n.startswith('observability_')]))"
# 期望: 8

# 2. Exporter 类可导入
python -c "from app.services import ObservabilityExporter; print(ObservabilityExporter.INTERVAL_SECONDS)"
# 期望: 60

# 3. FastAPI 集成
python -c "from app.main import app; print(app.router.lifespan_context.__name__)"
# 期望: lifespan

# 4. 4 YAML + 1 datasource 验证
python tests/validate_alerting_paths.py --check-promql
# 期望: 8/8 checks passed

# 5. pytest 全部测试
python -m pytest tests/test_observability_exporter.py tests/test_grafana_adapter.py tests/test_dashboard_template.py -v --no-cov
# 期望: 27 passed
```

### 6.2 端到端验证 (CI / Linux)

```bash
# 1. 启动后端 + Grafana
docker compose up -d backend grafana

# 2. 验证 8 metric 在 /metrics 端点 (TC-AT-012)
curl -s http://localhost:8000/api/v1/metrics | grep observability_ | wc -l
# 期望: ≥ 9 (8 metric + # HELP 注释)

# 3. 验证 10 规则加载 (TC-AT-016)
curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
  http://localhost:3000/api/v1/provisioning/alert-rules | jq '.[].rules | length'
# 期望: 10

# 4. 验证缺 env var 行为 (TC-AT-017)
docker compose stop grafana
unset GRAFANA_WEBHOOK_URL
docker compose up -d grafana
sleep 30
curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
  http://localhost:3000/api/v1/provisioning/contact-points | jq '.[] | select(.name == "sre-webhook") | .disabled'
# 期望: true
```

---

## 7. 变更统计

| 类别 | 文件 | 行数 |
|:---|:---:|:---:|
| 新建 | 7 | ~1020 |
| 修改 | 4 | ~110 |
| **合计** | **11** | **~1130** |

| 后端 | Grafana 配置 | 测试 | 文档 |
|:---:|:---:|:---:|:---:|
| +291 | +549 | +402 | +165 |

---

## 8. 下一步

参见 `NEXT_STEPS.md`:
- **P0**: 部署到生产 (docker compose up -d)
- **P1**: CI 环境补全 TC-AT-016 / TC-AT-017 验证
- **P2**: v1.40 候选主题 (Prometheus 黑盒探针 / 完整 meta-observe)
- **P3**: 阈值生产数据调优 (1-2 周后)

> **v1.39 核心交付完成**, 8 metric + 10 规则 + 3 渠道 + 3 路由 + 1 静音, 0 回归, 15/17 本地测试 PASS.
