# v1.37 Grafana 仪表盘模板 — 需求规格 (Round 1 Step 1 Draft)

> **迭代**: v1.37-grafana-dashboards
> **作者**: Ralph Planner (R1 Draft)
> **日期**: 2026-06-03
> **状态**: 🔄 Draft (待 Round 1 Step 2 自查)
> **基于**: v1.36-alert-observability 7 个数据源端点

---

## 1. 背景与动机 (Why)

### 1.1 业务背景

v1.36 完成了告警系统后端可观测性的全部基础设施 (8 个 REST 端点 + 数据源改造 + 224 个测试),但**缺少统一的可视化呈现层**:

- SRE 团队需要进入后端 API 逐个查看 JSON 才能判断告警系统健康度
- 缺乏阈值可视化,无法一眼看出"通道成功率是否下降到 90% 以下"
- 缺乏时间序列趋势,无法快速对比 1h vs 24h 的告警量变化
- 缺乏统一的"告警系统健康仪表盘",故障定位时需跨多个工具

### 1.2 目标

交付 **1 个 Grafana 统一仪表盘**, 在 1 个屏幕内展示 v1.36 全部 7 个可观测端点的核心指标, 让 SRE / Dev / PM 能**5 秒内判断告警系统当前是否健康**。

### 1.3 范围

**包含** (In Scope):
- 1 个 Grafana Dashboard JSON 文件 (v1.37-alerts-overview)
- 7 个 Row, 覆盖 v1.36 全部 7 个数据源端点
- Grafana 变量: time range, severity, rule, channel, instance
- Service Account Token 认证配置示例
- Grafana Provisioning YAML (自动加载, 适合 Docker / K8s)
- README 导入指南

**不包含** (Out of Scope):
- Grafana Alerting 规则 (告警逻辑在业务后端, 仪表盘仅可视化)
- 后端代码改动 (Grafana 调用现有 v1.36 端点)
- Prometheus / InfluxDB 等指标系统 (v1.36 端点已封装数据)
- 多集群 / 多租户 (v1.36 单实例, v1.37 沿用)

---

## 2. 用户角色与场景 (Who & When)

| 角色 | 使用频率 | 关注重点 | 典型动作 |
|:---|:---:|:---|:---|
| **SRE** | 每天 5+ 次 | 通道健康、锁降级、AM 同步、告警 P0 趋势 | 故障时快速定位 → 切换到具体后端日志 |
| **Dev** | 每天 1-2 次 | 告警响应时长 (p99)、静默命中率、升级率 | 优化响应时间、调整静默规则 |
| **PM** | 每周 1 次 | 告警总量趋势、通道成功率 | 周报、复盘 |

**典型场景**:

1. **故障定位** (SRE):
   - 收到告警通知 → 打开仪表盘 → 1 眼看到 "Lock Stats" Row 的 fallback_rate 100% → 立即知道 Redis 挂了 → 切到 Redis 排查

2. **趋势对比** (Dev):
   - 周会前查看仪表盘 → 调整 time range 24h → 7d → 30d (注: 仪表盘支持但后端只缓存 5min) → 对比告警量变化

3. **周报生成** (PM):
   - 查看 "Alert Trend" Row → 截图 / 复制为 PNG → 嵌入周报

---

## 3. 仪表盘结构 (What)

### 3.1 顶部 Header (固定)

| 元素 | 类型 | 内容 |
|:---|:---:|:---|
| Dashboard Title | text | v1.37 Alerts Overview |
| Last Refreshed | indicator | time picker 默认 1m refresh |
| Instance ID | stat | 单实例 hostname-pid |

### 3.2 7 Rows (主体)

#### **Row 1: 告警趋势 (Alert Trend)**
- 数据源: `GET /api/v1/alerts/observability/trend?bucket=1h`
- 变量: severity (P0/P1/P2/P3/all), time range
- Panels (3):
  - **总告警量时间序列**: line graph, x=时间桶, y=count, split by status (firing/resolved)
  - **P0 告警量**: stat, 大数字显示当前 5min 窗口 P0 数量
  - **Top 5 规则**: bar gauge, 横向条形, top 5 触发最多的规则

#### **Row 2: 响应时长 (Response Time)**
- 数据源: `GET /api/v1/alerts/observability/response-time?severity=`
- Panels (3):
  - **p50/p95/p99 时序**: line graph, 3 条线对比
  - **p99 当前值**: gauge (0~300s, 绿色 < 60s, 黄色 < 120s, 红色 ≥ 120s)
  - **按严重度分位表**: table, 行=严重度, 列=count/mean/p95

#### **Row 3: 升级率 (Escalation)**
- 数据源: `GET /api/v1/alerts/observability/escalation`
- Panels (3):
  - **升级率趋势**: line graph, x=时间, y=escalation_rate
  - **按 level 拆分**: pie chart, 4 个 level 的占比
  - **升级 Top 5 规则**: bar gauge, top 5 最常升级的规则

#### **Row 4: 通道发送成功率 (Channel Stats)**
- 数据源: `GET /api/v1/alerts/observability/channel-stats?channel=`
- Panels (3):
  - **各通道成功状态**: stat panel × 4 (webhook/slack/dingtalk/email), 大数字显示 success_rate
  - **通道平均耗时**: bar gauge, x=通道, y=avg_duration_ms
  - **失败告警**: time series, x=时间, y=failed_count, 按通道 split

#### **Row 5: 静默命中率 (Silence Hit Rate)**
- 数据源: `GET /api/v1/alerts/observability/silence-hit-rate`
- Panels (3):
  - **命中率趋势**: line graph, x=时间, y=hit_rate
  - **按 matcher 拆分**: bar gauge, top 10 silence_name
  - **静默 vs 触发量**: stacked bar, x=时间, y=count (fired+silenced)

#### **Row 6: AM 同步可观测 (AM Sync)**
- 数据源: `GET /api/v1/alerts/observability/am-sync?operation=`
- Panels (3):
  - **同步成功率**: gauge, 0~100% (绿 > 95%, 黄 80~95%, 红 < 80%)
  - **按 operation 拆分**: table, 行=operation, 列=success/failed/total/avg_duration
  - **最近失败**: table, 10 条 recent_failures, 列=operation/error/created_at

#### **Row 7: Redis 锁可观测 (Lock Stats)**
- 数据源: `GET /api/v1/alerts/observability/lock-stats`
- Panels (3):
  - **fallback 比例**: gauge, 0~100% (绿 < 5%, 黄 5~15%, 红 > 15%)
  - **最近 flush 趋势**: bar gauge, 最近 10 次 flush 的 acquired/skipped/fallback
  - **历史累计**: stat panel × 4 (total_acquired/total_skipped/total_fallback/total_errors)

---

## 4. 变量 (Variables)

| 名称 | 类型 | 数据源 | 默认值 |
|:---|:---:|:---|:---:|
| `time_range` | time picker | Grafana 内置 | 1h |
| `severity` | custom | 静态 P0/P1/P2/P3/all | all |
| `channel` | custom | 静态 webhook/slack/dingtalk/email/all | all |
| `rule` | query | `GET /trend?group_by=rule` 返回 top 20 | all |
| `instance_id` | query | `GET /health` 返回 instance_id | auto |
| `refresh` | time picker | Grafana 内置 | 1m |

---

## 5. 数据源 (Backend API)

| Panel Row | HTTP Method | 端点 | 缓存 |
|:---|:---:|:---|:---:|
| Trend | GET | `/alerts/observability/trend` | 5min |
| Response Time | GET | `/alerts/observability/response-time` | 5min |
| Escalation | GET | `/alerts/observability/escalation` | 5min |
| Channel Stats | GET | `/alerts/observability/channel-stats` | 5min |
| Silence Hit Rate | GET | `/alerts/observability/silence-hit-rate` | 5min |
| AM Sync | GET | `/alerts/observability/am-sync` | 5min |
| Lock Stats | GET | `/alerts/observability/lock-stats` | 5min |
| Health | GET | `/alerts/observability/health` | - |

**数据源类型**: Grafana JSON Datasource Plugin (https://github.com/grafana/grafana-json-datasource)

**认证**: Bearer Token (Service Account)

```
Authorization: Bearer ${GRAFANA_SA_TOKEN}
```

---

## 6. 交付物 (Deliverables)

| 路径 | 用途 |
|:---|:---|
| `infra/grafana/dashboards/v1.37-alerts-overview.json` | 主仪表盘 JSON (Grafana export 格式) |
| `infra/grafana/provisioning/dashboards/v1.37-alerts.yaml` | Provisioning 配置 (YAML) |
| `infra/grafana/provisioning/datasources/observability-api.yaml` | JSON Datasource 配置 |
| `infra/grafana/README.md` | 导入指南 (manual + provisioning 两种方式) |
| `tests/test_dashboard_json.py` | JSON schema 验证 (Python) |
| `tests/test_dashboard_panels.py` | panel 数量/类型/datasource 验证 |

---

## 7. 验收标准 (Acceptance Criteria)

### 7.1 功能验收 (P0)

- [ ] **AC-1**: JSON 文件可被 Grafana 10.x / 11.x 导入无错误
- [ ] **AC-2**: 7 个 Row 全部就位, 每个 Row 至少 1 个 panel
- [ ] **AC-3**: 6 个变量 (time_range/severity/channel/rule/instance/refresh) 全部可下拉选择
- [ ] **AC-4**: 切换 time_range 后, 所有 panel 正确重新查询
- [ ] **AC-5**: 切换 severity 后, response-time / escalation / trend 等 panel 过滤正确
- [ ] **AC-6**: 每个 panel 的 datasource 指向 v1.36 后端端点, URL 正确
- [ ] **AC-7**: Service Account Token 通过 `Authorization: Bearer` 头部传递
- [ ] **AC-8**: Provisioning YAML 在 `docker-compose up grafana` 后自动加载仪表盘

### 7.2 性能验收 (P1)

- [ ] **AC-9**: 仪表盘首次加载 < 3s (7 个 panel 并发查询)
- [ ] **AC-10**: 仪表盘手动 refresh < 2s
- [ ] **AC-11**: 单 panel 后端响应 < 500ms (受 v1.36 5min 缓存保护)

### 7.3 文档验收 (P1)

- [ ] **AC-12**: README 包含手动导入步骤 (截图/文字)
- [ ] **AC-13**: README 包含 Provisioning 自动加载步骤
- [ ] **AC-14**: README 包含 Service Account Token 创建步骤
- [ ] **AC-15**: README 包含故障排查 (常见错误 + 解决)

### 7.4 测试验收 (P0)

- [ ] **AC-16**: `tests/test_dashboard_json.py` 全过 (JSON schema 验证)
- [ ] **AC-17**: `tests/test_dashboard_panels.py` 全过 (panel 完整性验证)
- [ ] **AC-18**: `tests/test_provisioning.py` 全过 (YAML 语法 + 配置正确性)

---

## 8. 测试场景 (Test Scenarios)

### 8.1 场景 1: 手动导入 (Manual Import)

1. 用户登录 Grafana
2. 进入 "+" → Import Dashboard
3. 上传 `v1.37-alerts-overview.json`
4. 选择 datasource "Observability API"
5. 点击 Import
6. **预期**: 仪表盘出现, 7 个 Row 全部显示数据

### 8.2 场景 2: Provisioning 自动加载 (Docker)

1. `docker-compose up -d grafana`
2. 等待 10s
3. 访问 `http://localhost:3000`
4. 登录 admin
5. 进入 Dashboards → Browse
6. **预期**: 看到 "v1.37 Alerts Overview" 自动出现

### 8.3 场景 3: 变量过滤

1. 在仪表盘顶部 "Severity" 下拉选择 P0
2. 等待自动 refresh
3. **预期**: response-time / escalation / trend 三个 Row 的 panel 全部只显示 P0 数据

### 8.4 场景 4: 故障可视化 (P0 演示)

1. 在后端 mock 一次 "channel webhook 失败"
2. 等待 v1.36 notifier 写 OperationLog (≈ 1s)
3. 仪表盘手动 refresh
4. **预期**: "Channel Stats" Row 中 webhook 的 success_rate 下降, "失败告警" panel 出现新点

---

## 9. 风险与缓解 (Risks)

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---:|:---:|:---|
| Grafana JSON Datasource 插件未预装 | 中 | 高 | README 明确说明,Provisioning 自动安装 |
| v1.36 端点返回数据格式与 Grafana panel 不匹配 | 中 | 高 | Round 3 之前用 mock 数据 dry-run |
| Service Account Token 过期 | 低 | 中 | 文档说明 30 天轮换 + 告警 |
| 7 个 panel 性能超 AC-9 (3s) | 中 | 中 | 利用 5min 缓存, 避免重复查询 |

---

## 10. 未来扩展 (Out of Scope for v1.37)

- v1.38: 增加 alert notification Slack/PagerDuty 直接集成
- v1.39: Prometheus 兼容 (Grafana scrape) - 替代 JSON datasource
- v1.40: 多集群仪表盘 (multi-tenant)
- v1.41: AI 异常检测 (在 trend 上叠加预测带)

---

> **Round 1 Step 1 完成**: 进入 Step 2 (Critique) - 自查需求完整性、可行性、可测试性
