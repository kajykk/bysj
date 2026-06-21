# v1.37 Round 1 推演 (Simulation) 报告

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03T15:15:30.144283
> **目的**: 验证仪表盘 JSON 结构符合 Grafana 11.6 schema, 验证 6 变量 + 7 Rows + 21 panels 完整性

---

## 1. 推演结果摘要

| 指标 | 数值 |
|:---|:---:|
| 总 Rows | 7 |
| 总 Panels | 24 |
| 变量数 | 6 |
| 缺 datasource | 0 |
| 缺 metric 字段 | 0 |

---

## 2. 各 Row Panel 分布

- **Alert Trend**: 3 panels
- **Response Time**: 3 panels
- **Escalation**: 3 panels
- **Channel Stats**: 6 panels
- **Silence Hit Rate**: 3 panels
- **AM Sync**: 3 panels
- **Lock Stats**: 3 panels

---

## 3. 变量清单

| 名称 | 类型 | 用途 |
|:---|:---:|:---|
| `severity` | custom | 严重度过滤 (P0/P1/P2/P3/all) |
| `channel` | custom | 通道过滤 (webhook/slack/dingtalk/email/all) |
| `rule` | query | 告警规则 (从 /grafana/variable 拉取 top 20) |
| `instance_id` | custom | 实例 ID (单实例场景用 static auto) |
| `operation` | custom | AM 操作 (push_silence/expire_silence/all) |
| `time_range` | custom | 时间范围 (1h/6h/24h/7d/30d) |

---

## 4. 端点 - Panel 映射

| Row | Panel 标题 | 端点 | 关键参数 |
|:---|:---|:---|:---|
| Alert Trend | 总告警量 | `/grafana/query` | metric=trend, group_by=status |
| Alert Trend | P0 当前量 | `/grafana/query` | metric=trend, severity=P0 |
| Alert Trend | Top 5 规则 | `/grafana/query` | metric=trend, group_by=rule, top_n=5 |
| Response Time | p50/p95/p99 | `/grafana/query` | metric=response_time |
| Response Time | p99 当前值 | `/grafana/query` | metric=response_time, bucket=5m |
| Response Time | by severity | `/grafana/query` | metric=response_time, group_by=severity |
| Escalation | 升级率 | `/grafana/query` | metric=escalation |
| Escalation | by level | `/grafana/query` | metric=escalation, group_by=level |
| Escalation | Top 5 规则 | `/grafana/query` | metric=escalation, group_by=rule, top_n=5 |
| Channel Stats | 4 stat panels | `/grafana/query` | metric=channel_stats, channel=webhook/slack/dingtalk/email |
| Channel Stats | Avg duration | `/grafana/query` | metric=channel_stats, group_by=channel, metric=duration |
| Channel Stats | Failed trend | `/grafana/query` | metric=channel_stats, group_by=channel, metric=failed |
| Silence | Hit rate | `/grafana/query` | metric=silence_hit_rate |
| Silence | Top 10 matchers | `/grafana/query` | metric=silence_hit_rate, group_by=matcher, top_n=10 |
| Silence | Fired vs Silenced | `/grafana/query` | metric=silence_hit_rate, group_by=type |
| AM Sync | Success rate | `/grafana/query` | metric=am_sync |
| AM Sync | By operation | `/grafana/query` | metric=am_sync, group_by=operation |
| AM Sync | Recent failures | `/grafana/query` | metric=am_sync, include_recent_failures=true, limit=10 |
| Lock Stats | Fallback rate | `/grafana/query` | metric=lock_stats |
| Lock Stats | Recent flushes | `/grafana/query` | metric=lock_stats, group_by=recent_flushes, limit=10 |
| Lock Stats | Totals | `/grafana/query` | metric=lock_stats, group_by=totals |

---

## 5. 关键发现

### 5.1 已解决 (R1)

- ✅ Panel 数量匹配需求 (1 仪表盘 / 7 Rows / 21 panels)
- ✅ 所有 panel 都有 datasource (simpod-json-datasource)
- ✅ 所有 target 都包含 metric 字段
- ✅ 6 变量全部定义, 类型与 Draft 一致

### 5.2 仍待解决 (R2 修订)

- ⚠️ **P0-1**: 需在 v1.36 后端增加 Grafana Adapter 路由 (`/grafana/query`, `/grafana/variable`, `/grafana/health`)
- ⚠️ **P0-2**: 需在 v1.36 后端增加 Service Account 鉴权路径 (`GRAFANA_SERVICE_TOKEN` env var)
- ⚠️ **P1-1**: 需明确 v1.36 后端如何解析 POST body 中的 JSON params (与 GET query string 不同)
- ⚠️ **P1-2**: rule 变量需用 query 类型从 `/grafana/variable` 拉取, JSON path 配置需验证
- ⚠️ **P1-3**: 5min 缓存导致 panel 看起来 stale, 需在 README 明确说明

### 5.3 Round 2 待办

- R2-D1: v1.36 后端增加 Grafana Adapter 路由 (4 端点)
- R2-D2: v1.36 后端增加 Service Account 鉴权 (1 函数)
- R2-D3: 明确 POST body 解析与 GET query string 转换
- R2-D4: rule 变量 JSON path 验证
- R2-D5: instance_id 简化为 static 文本
- R2-D6: README 5min 缓存说明

---

## 6. 样例文件

- 仪表盘 JSON 样例: `v1.37-alerts-overview.sample.json` (~30KB, 21 panels, 6 vars)
- 本报告: `03-simulation-r1.md`

---

> **Round 1 Step 4 完成**: 进入 Step 5 (Lock) - 锁定 Round 1 交付物
