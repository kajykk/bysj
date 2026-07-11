# Grafana 仪表盘 (v1.37)

> **状态**: v1.37 已交付, 5 个 Grafana 适配器端点 + 1 个仪表盘 + 双路径鉴权.

本文档介绍 `bysj` 项目 v1.37 迭代引入的 **Grafana 仪表盘** 模块, 包括架构、部署、配置、故障排查.

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                          Grafana (3000)                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Dashboard: v1.37-alerts-overview (24 panels)           │    │
│  │  ├─ Timeseries: 告警趋势 (P0/P1/P2/P3)                  │    │
│  │  ├─ Stat: 响应时长 (mean/p50/p95/p99)                    │    │
│  │  ├─ Pie: 升级率 (by_level)                              │    │
│  │  ├─ BarGauge: 通道成功率 (webhook/slack/dingtalk/email) │    │
│  │  ├─ Gauge: 静默命中率 / AM 同步成功率                    │    │
│  │  └─ BarGauge: Redis 锁统计                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  DataSource: Observability API (simpod-json-datasource) │    │
│  │  URL: http://backend:8000/api/v1/alerts/observability   │    │
│  │  Auth: Bearer <GRAFANA_SA_TOKEN>                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │  (5 endpoints)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Backend FastAPI (8000)                          │
│  /api/v1/alerts/observability/grafana/                           │
│  ├── GET  /          → 根 (Test connection)                      │
│  ├── GET  /health    → 健康检查                                  │
│  ├── POST /metrics   → 7 metric 列表                             │
│  ├── POST /variable  → 4 变量类型 (rule/matcher/operation/channel)│
│  └── POST /query     → 主端点 (调用 v1.36 _compute_* 适配)        │
│                                                                  │
│  鉴权: require_sa_or_admin                                       │
│  ├─ SA Token 匹配 (settings.grafana_service_token) → 200          │
│  └─ Admin User JWT (get_current_user + role=admin) → 200         │
│     其它 → 401 / 403                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              v1.36 _compute_* (PostgreSQL + Redis)               │
│  _compute_trend / _compute_response_time / _compute_escalation  │
│  _compute_channel_stats / _compute_silence_hit_rate             │
│  _compute_am_sync / _compute_lock_stats                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 目录结构

```
infra/grafana/
├── README.md                          # 本文档
├── provisioning/                      # Grafana 启动时自动加载
│   ├── datasources/
│   │   └── observability-api.yaml    # DataSource 自动注册
│   └── dashboards/
│       └── v1.37-alerts.yaml         # Dashboard provider 配置
└── dashboards/                        # 仪表盘 JSON (挂载到容器)
    └── v1.37-alerts-overview.json    # 24-panel 仪表盘
```

挂载映射 (docker-compose.yml):

| 主机路径 | 容器路径 | 用途 |
|---|---|---|
| `./infra/grafana/provisioning` | `/etc/grafana/provisioning:ro` | 自动注册 datasources + dashboards providers |
| `./infra/grafana/dashboards` | `/var/lib/grafana/dashboards:ro` | 仪表盘 JSON 实际内容 |

---

## 3. 部署流程

### 3.1 前置条件

1. 后端 v1.37 已部署并启动 (端口 8000)
2. 至少有 1 个 admin 用户 (用于人类登录)
3. 已安装 `docker-compose` ≥ 2.20

### 3.2 创建 Grafana Service Account Token

Grafana 11.0+ 引入了 **Service Account**, 推荐使用 SA Token 而非 API Key:

```bash
# 1. 启动一次 Grafana 容器 (生成初始 admin 密码)
docker compose up -d grafana

# 2. 进入容器, 创建 SA
docker compose exec grafana bash
grafana-cli admin service-account create \
  --name "bysj-observability-api" \
  --role Admin \
  --is-disabled false

# 记录返回的 service account ID (如 42)

# 3. 为该 SA 创建 token
grafana-cli admin service-account-token create 42 \
  --name "bysj-token-1" \
  --ttl 0   # 0 = 永不过期 (生产建议设置 90d)

# 复制输出的 token (格式: glsa_xxxxxxxxxx)
exit
```

### 3.3 配置环境变量

在项目根目录的 `.env` 中填入:

```bash
# Grafana Admin 密码 (Grafana 容器初始化用)
GRAFANA_ADMIN_PASSWORD=your-secure-admin-password

# Grafana Service Account Token (Grafana 调用后端时使用)
GRAFANA_SA_TOKEN=glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

在 `backend/.env` 中填入**相同**的 token:

```bash
# 与根 .env 的 GRAFANA_SA_TOKEN 同步
GRAFANA_SERVICE_TOKEN=glsa_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

⚠️ **警告**:
- **GRAFANA_SA_TOKEN** (根 .env) 用于 Grafana provisioning 时注入到 datasource
- **GRAFANA_SERVICE_TOKEN** (backend/.env) 用于后端鉴权
- 两个值**必须相同**, 否则 Grafana 调用会被 401 拒绝

### 3.4 启动

```bash
# 1. 重建并启动所有服务
docker compose up -d

# 2. 验证 Grafana 启动
docker compose logs -f grafana
# 看到 "HTTP Server Listen" 表示成功

# 3. 浏览器访问
open http://localhost:3000
# 用户: admin
# 密码: $GRAFANA_ADMIN_PASSWORD 的值
```

### 3.5 验证数据源连通性

1. 登录 Grafana → Configuration → Data sources
2. 点击 "Observability API"
3. 点击 "Test connection" 按钮
4. 应该看到绿色 ✓ "Connected to backend"

如果失败, 检查:
- 后端是否运行: `curl http://localhost:8000/api/v1/alerts/observability/grafana/health`
- Token 是否一致: `grep GRAFANA_SA_TOKEN .env && grep GRAFANA_SERVICE_TOKEN backend/.env`
- 容器网络: `docker compose exec grafana curl http://backend:8000/api/v1/alerts/observability/grafana/health`

---

## 4. 仪表盘使用

### 4.1 访问

浏览器: `http://localhost:3000/d/v1.37-alerts-overview`

左侧菜单: Observability → v1.37 Alerts Overview

### 4.2 Panel 列表 (24 个)

| # | 类别 | 类型 | Metric | 说明 |
|---|---|---|---|---|
| 1-4 | 告警趋势 | Timeseries | `trend` | P0/P1/P2/P3 趋势线 (按时间桶) |
| 5-11 | 响应时长 | Stat × 7 | `response_time` | mean/p50/p95/p99/ack_rate/total_fired/total_pending |
| 12-14 | 升级 | Stat | `escalation` | P0/P1 升级数 + 总升级率 |
| 15-19 | 通道 | BarGauge × 4 | `channel_stats` | webhook/slack/dingtalk/email 成功率 |
| 20-22 | 静默 | Gauge + Stat | `silence_hit_rate` | 总命中率 + matcher Top-N |
| 23 | AM 同步 | Gauge | `am_sync` | 同步成功率 |
| 24 | 锁 | Stat × 3 | `lock_stats` | acquire_rate/fallback_rate/error_rate |

### 4.3 时间范围

仪表盘顶部可选择时间范围 (默认: 最近 6 小时). 时间范围通过 Grafana 全局变量 `$__from` / `$__to` 传给后端, 后端解析为 `start_time` / `end_time` query param.

### 4.4 Variables (变量)

- **Severity** (P0/P1/P2/P3/ALL): 过滤告警严重程度
- **Status** (Firing/Resolved/ALL): 过滤告警状态
- **Rule** (top 20): 动态加载自 `/grafana/variable?type=rule`
- **Matcher** (top 10): 动态加载自 `/grafana/variable?type=matcher`
- **Channel** (静态): webhook/slack/dingtalk/email
- **Operation** (静态): push_silence/delete_silence/...

---

## 5. 鉴权机制详解

### 5.1 双路径设计

```python
async def require_sa_or_admin(request, token, db) -> User:
    # 路径 1: Service Account Token (Grafana 调用)
    if settings.grafana_service_token and token == settings.grafana_service_token:
        return 虚拟 admin User (id=0, role='admin', status='active')

    # 路径 2: Admin User JWT (人类管理员)
    user = await get_current_user(request, token, db)
    if user.role != 'admin':
        raise HTTPException(403, "需要管理员权限")
    return user
```

### 5.2 为什么需要 SA Token?

Grafana JSON Datasource 插件在**无状态 HTTP 调用**时使用, 它的特点是:
- 没有用户上下文 (Grafana 不知道是哪个用户在浏览)
- 长时间运行 (Dashboard 自动刷新时持续调用)
- 不支持 OAuth flow (Service Account 方式更简单)

### 5.3 禁用 SA 鉴权

如需禁用 SA 鉴权 (仅允许 Admin User JWT), 留空 `backend/.env`:

```bash
GRAFANA_SERVICE_TOKEN=
```

此时:
- Grafana 仪表盘无法加载数据 (401)
- 但 Postman / curl + Admin JWT 仍可调用
- 适合**临时维护**或**调试**场景

---

## 6. 故障排查 (Troubleshooting)

### 6.1 仪表盘显示 "No data"

1. **检查后端**: `curl http://localhost:8000/api/v1/alerts/observability/grafana/health`
   - 返回 `{"status": "ok"}` → 后端正常
   - 返回 401 → Token 不匹配, 检查 `GRAFANA_SERVICE_TOKEN`
2. **检查 Grafana 日志**: `docker compose logs -f grafana`
3. **手动测试 SA token**:
   ```bash
   curl -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
        http://localhost:8000/api/v1/alerts/observability/grafana/metrics
   ```
   - 200 + 7 metrics → 成功
   - 401 → Token 不匹配

### 6.2 Test connection 失败

按 §3.5 步骤检查. 最常见原因:
- `backend/.env` 的 `GRAFANA_SERVICE_TOKEN` 未设置
- 容器网络不通 (防火墙/网络模式)
- Token 拼写错误 (注意 `glsa_` 前缀)

### 6.3 变量下拉为空

- `type=rule` 变量: 依赖告警数据, 如无告警则为空
- `type=matcher` 变量: 依赖静默数据, 如无静默则为空
- `type=operation` / `type=channel`: 静态列表, 应始终有 5 个选项

### 6.4 仪表盘加载缓慢 (> 5s)

- 减少面板数量
- 调整时间范围为更短区间
- 检查后端数据库索引 (v1.16+ 优化)

### 6.5 SA Token 过期

- 检查 token TTL: `grafana-cli admin service-account-token list 42`
- 重新创建: 按 §3.2 流程

---

## 7. 安全注意事项

1. **不要**将 `GRAFANA_SA_TOKEN` 提交到 git
2. **不要**在生产环境使用默认密码 `changeme`
3. **建议**生产环境使用强密码 (≥ 16 字符, 字母+数字+符号)
4. **建议**SA Token 设置 90 天 TTL, 定期轮换

---

## 10. 告警规则 (v1.39)

> **状态**: v1.39 已交付, 10 条告警规则 (P0: 3, P1: 5, P2: 2) + 3 Contact Points + 3 Routing Policies + 1 Mute Timing.
>
> 把"观测"升级为"响应": 当通道成功率 < 80%、锁错误率 > 0% 等异常发生时, SRE 通过 Webhook/Email/Slack 立即收到告警.

### 10.1 架构概览

```
┌──────────────────────────────────────────────────────────┐
│                    Grafana (3000)                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Alert Rules (10)                                  │  │
│  │  ├─ R1/R2: 通道成功率 (P0/P1)                       │  │
│  │  ├─ R3/R4: AM 同步成功率 (P0/P1)                    │  │
│  │  ├─ R5/R6/R7: 锁统计 (P1/P1/P0)                    │  │
│  │  ├─ R8: 升级率 (P1)                                │  │
│  │  ├─ R10: 告警总量 (P2)                              │  │
│  │  └─ R11: Prometheus 健康检查 (P2 meta)               │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Contact Points (3)                                │  │
│  │  ├─ sre-webhook (P0/P1 即时)                       │  │
│  │  ├─ sre-email (P0/P1 存档)                         │  │
│  │  └─ slack-alerts (P0/P1 协同)                      │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  DataSource: Prometheus (uid=PB0F7F7A2A1B0E0FA)    │  │
│  │  URL: http://backend:8000                          │  │
│  │  Scrape: /api/v1/metrics (ObservabilityExporter)    │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                              │  (10 rules)
                              ▼
┌──────────────────────────────────────────────────────────┐
│              Backend /api/v1/metrics                      │
│  ObservabilityExporter (60s 周期)                         │
│  ├─ observability_channel_success_rate                    │
│  ├─ observability_am_sync_success_rate                    │
│  ├─ observability_lock_acquire_rate/fallback/error/total  │
│  ├─ observability_escalation_rate                         │
│  └─ observability_alert_total (counter)                  │
└──────────────────────────────────────────────────────────┘
```

### 10.2 9 条核心告警规则 (R1-R8 + R10)

| UID | Title | Severity | 条件 | for |
|:---|:---|:---:|:---|:---:|
| r-channel-critical | ChannelSuccessRateCritical | P0 | `channel_success_rate{channel="all"} < 0.80` | 2m |
| r-channel-low | ChannelSuccessRateLow | P1 | `< 0.90` | 5m |
| r-am-sync-critical | AmSyncCritical | P0 | `am_sync_success_rate < 0.70` | 5m |
| r-am-sync-low | AmSyncLow | P1 | `< 0.85` | 10m |
| r-lock-acquire-low | LockAcquireRateLow | P1 | `lock_acquire_rate < 0.90` | 5m |
| r-lock-fallback-high | LockFallbackRateHigh | P1 | `lock_fallback_rate > 0.05` | 5m |
| r-lock-error-high | LockErrorRateHigh | P0 | `lock_error_rate > 0.00 AND lock_acquire_total > 0` | 5m |
| r-escalation-high | EscalationRateHigh | P1 | `escalation_rate > 0.30` | 1h |
| r-alert-total-spike | AlertTotalSpike | P2 | `sum(increase(alert_total[1h])) > 500` | 1h |
| meta-prometheus-up | PrometheusUpCheck | P2 | `up{job="backend"} == 1` | 5m |

**GAP-1 修复**: R7 增加 `lock_acquire_total > 0` 前置过滤, 避免 0 流量误报.

### 10.3 3 个 Contact Points

```yaml
sre-webhook:    # P0/P1 即时通道 (R1 决策 Q2 优先)
  type: webhook
  url: ${env:GRAFANA_WEBHOOK_URL}

sre-email:      # P0/P1 存档通道
  type: email
  addresses: ${env:GRAFANA_SRE_EMAIL}

slack-alerts:   # P0/P1 协同通道
  type: slack
  url: ${env:GRAFANA_SLACK_URL}
  channel: ${env:GRAFANA_SLACK_CHANNEL}
```

### 10.4 3 个 Routing Policies

| Severity | Receiver | group_wait | group_interval | repeat_interval | Mute |
|:---:|:---|:---:|:---:|:---:|:---:|
| P0 | sre-webhook | 10s | 5m | 1h | ❌ (24×7 通知) |
| P1 | sre-webhook | 30s | 10m | 4h | ❌ (24×7 通知) |
| P2 | sre-email | 5m | 1h | 24h | ✅ (工作日 09-18) |

### 10.5 1 个 Mute Timing

**p2-business-hours-mute** (R1 决策 Q3, 仅 P2 静音):
- 工作日 00:00-09:00: 静音
- 工作日 18:00-24:00: 静音
- 周末 00:00-24:00: 静音
- 时区: UTC (默认)

**P0/P1 不受此 mute 影响** — 故障 24×7 通知 SRE.

### 10.6 缺 env var 行为 (RISK-2)

| env var | 缺失行为 | 实际影响 |
|:---|:---|:---|
| `GRAFANA_WEBHOOK_URL` | contact point 自动 `disabled` | P0/P1 通知失败 (走 email+slack 兜底) |
| `GRAFANA_SRE_EMAIL` | contact point 自动 `disabled` | P0/P1 通知失败 (走 webhook+slack 兜底) |
| `GRAFANA_SLACK_URL` | contact point 自动 `disabled` | P0/P1 通知失败 (走 webhook+email 兜底) |

**建议**: 至少配置 2 个渠道的 env var, 避免单点失败.

### 10.7 阈值调整指南

修改 `infra/grafana/provisioning/alerting/rules.yaml` 中对应规则的 `conditions[*].evaluator.params` 数组, 调整后重启 Grafana 容器即可.

**注意**:
- 阈值调整后, 历史告警规则的状态可能重置 (建议在非高峰时段调整)
- `for` 字段影响告警持续时间, 越小越敏感但也越易误报
- `noDataState: OK` (R1-R10) 避免 Exporter 短暂失败时误报
- `noDataState: Alerting` (R11) 确保 Prometheus 抓取失败时立即告警

### 10.8 部署与验证

```bash
# 1. 启动后端 (包含 ObservabilityExporter)
docker compose up -d backend

# 2. 验证 8 metric 暴露
curl -s http://localhost:8000/api/v1/metrics | grep observability_

# 3. 启动 Grafana (含 alerting provisioning)
docker compose up -d grafana

# 4. 验证 9 规则加载
curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
  http://localhost:3000/api/v1/provisioning/alert-rules | jq '.[] | length'
# 期望: 10

# 5. 静态验证
python backend/tests/validate_alerting_paths.py --check-promql
# 期望: 8/8 PASS
```

### 10.9 故障排查

| 症状 | 可能原因 | 解决 |
|:---|:---|:---|
| 规则不触发 | Exporter 未启动 | 检查后端日志 `ObservabilityExporter started` |
| 规则永远 firing | threshold 设置过低 | 调整 `evaluator.params` |
| 通知失败 | env var 缺失 | 设置 `GRAFANA_WEBHOOK_URL` 等 |
| 0 流量误报 (R7) | GAP-1 未应用 | 确认 R7 expr 包含 `lock_acquire_total > 0` |
| 告警风暴 | `group_interval` 太小 | 调整为 5m+ |

5. **建议**Grafana 容器暴露在内部网络, 不直接暴露公网

---

## 8. 卸载

```bash
# 1. 停止并移除容器
docker compose down grafana

# 2. 清理数据 (可选)
docker volume rm dws_grafana_data
```

---

## 9. 扩展开发

### 9.1 添加新 Metric

1. 在 `backend/app/api/v1/grafana_adapter.py` 的 `_METRICS` 列表追加
2. 在 `_METRIC_HANDLERS` 添加 handler
3. 在 `_FORMATTERS` 添加 formatter
4. 重启后端, Grafana 会在下一次 Refresh 时看到新 metric

### 9.2 添加新 Dashboard

1. 在 `infra/grafana/dashboards/` 添加新 JSON 文件
2. 命名为 `<dashboard-name>.json`
3. 重启 Grafana: `docker compose restart grafana`
4. 或等待 30s (provider `updateIntervalSeconds: 30`)

### 9.2.1 v1.38 标准仪表盘 (24 panels) ⭐ 推荐

v1.38 提供开箱即用的 `v1.37 Alerts Overview` 仪表盘 (24 panels, 7 Rows, 6 变量):

| 资产 | 路径 |
|---|---|
| **YAML 配置** | `infra/grafana/dashboards/v1.37-alerts-overview.yaml` |
| **Jinja2 模板** | `infra/grafana/dashboards/templates/panel_{type}.json.j2` |
| **生成 JSON** | `infra/grafana/dashboards/v1.37-alerts-overview.json` (脚本产出) |
| **Provisioning** | `infra/grafana/provisioning/dashboards/alerts-overview.yaml` |
| **构建脚本** | `infra/grafana/scripts/build_dashboard.py` |

**修改面板 (推荐流程)**:
1. 编辑 `v1.37-alerts-overview.yaml` (添加/修改 panel)
2. 运行: `python infra/grafana/scripts/build_dashboard.py`
3. 等待 30s, Grafana 自动加载新 JSON (无需重启)

**7 Rows × 24 Panels 结构**:
- **Row 1 (告警趋势)**: P0/P1/P2/P3 趋势 + 总量 (4 panels)
- **Row 2 (响应时长)**: p99/p95/Mean + Ack Rate (4 panels)
- **Row 3 (升级率)**: 分布饼图 + 升级率 + by Level (3 panels)
- **Row 4 (通道成功率)**: Overall + Webhook/Slack/DingTalk+Email (4 panels)
- **Row 5 (静默命中率)**: Hit Rate + Total + Top Matchers (3 panels)
- **Row 6 (AM 同步)**: Success Rate + Total + by Operation (3 panels)
- **Row 7 (锁统计)**: Acquire Rate + Fallback + Error Rate (3 panels)

**6 Dashboard 变量**:
- `time_range` (time, Grafana 内置)
- `severity` (custom: all/P0/P1/P2/P3)
- `rule` (query, /grafana/variable type=rule)
- `matcher` (query, /grafana/variable type=matcher, 仅展示)
- `operation` (custom: all/create/update/delete/read)
- `channel` (custom: all/webhook/slack/dingtalk/email)

**v1.38 静态校验**:
```bash
python backend/tests/validate_dashboard_json.py   # 11 项校验
python -m pytest backend/tests/test_dashboard_template.py -v   # 7 单元测试
```

### 9.3 修改 Provisioning

修改 `infra/grafana/provisioning/` 下的 YAML 后:
- 数据源变更: `docker compose restart grafana`
- 仪表盘 provider 变更: `docker compose restart grafana`
- 仅 dashboard JSON 内容变更: 无需重启, 30s 内自动加载

---

## 10. 参考

- [Grafana JSON Datasource Plugin](https://grafana.com/grafana/plugins/simpod-json-datasource/)
- [Grafana Provisioning Docs](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Grafana Service Accounts](https://grafana.com/docs/grafana/latest/administration/service-accounts/)
- 后端 `/grafana/*` API 文档: 启动后端访问 `http://localhost:8000/docs`
- 规划文档: `docs/planning/v1.37-grafana-dashboards/`
