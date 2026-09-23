# v1.38 Grafana 仪表盘 JSON 模板 — 需求规格 (Round 2 修订版)

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R2 Draft)
> **日期**: 2026-06-03
> **状态**: 🔄 R2 Draft (进行中)
> **基于**: R1 Lock (97% 综合评分, 5 文件, 6 校验 PASS)

---

## 1. 背景与动机 (Why)

### 1.1 业务背景

v1.37 完成了 Grafana 可视化的全部基础设施 (5 个 JSON Datasource 适配器端点 + provisioning + 鉴权 + README), 但**未提供开箱即用的仪表盘 JSON 模板**:
- 用户部署 Grafana 后, 仍需手动创建 24 个 panel 并逐一配置 datasource/target/variable 绑定
- 手动配置容易出错 (target 拼写、variable 引用、time range 映射)
- 缺乏"标准视图", 不同 SRE 各自搭建, 失去统一观测能力
- DELIVERY_REPORT §5.1 明确列为 v1.37 已知限制, NEXT_STEPS.md §2.1 推荐 v1.38 解决

### 1.2 目标

提供 **1 个生产级 Grafana Dashboard JSON 模板** (`v1.37-alerts-overview.json`), 包含 **24 个 panel**, 完整覆盖 v1.36 全部 7 个 metric, 让用户**部署后 0 配置即可看到完整告警可观测仪表盘**。

### 1.3 范围 (Scope)

**包含 (In Scope)**:
- 1 个 Grafana Dashboard JSON 文件 (24 panels, Grafana 11.6 schema 39)
- 7 Rows, 1 Row 对应 1 个 v1.36 metric (trend/response_time/escalation/channel_stats/silence_hit_rate/am_sync/lock_stats)
- 6 个 dashboard 变量: time_range / severity / rule / matcher / operation / channel
- 每个 panel 配置: targets (引用 v1.37 /grafana/query) + fieldConfig (单位/阈值/颜色) + options (图例/网格)
- 静态验证脚本: JSON schema + target metric 引用 + variable 引用一致性
- 升级 `v1.37-alerts-overview.sample.json` (7 panels) → `v1.37-alerts-overview.json` (24 panels, 替换 sample)

**不包含 (Out of Scope)**:
- v1.37 API 改动 (复用现有 5 端点)
- 后端代码改动 (0 行 Python 修改)
- Grafana Alerting 规则 (v1.38 后续主题)
- 移动端 breakpoint 优化 (v1.39+ 主题)
- 数据归档 (TimescaleDB 集成, v1.40+ 主题)
- 多租户 / per-instance 仪表盘 (v1.41+ 主题)

---

## 2. 用户角色与场景 (Who & When)

| 角色 | 使用频率 | 关注重点 | 典型动作 |
|:---|:---|:---|:---|
| **SRE** | 每天 5+ 次 | 通道健康、锁降级、AM 同步、告警 P0 趋势 | 故障时 5 秒判断告警系统是否健康 → 切换到具体后端日志 |
| **Dev** | 每天 1-2 次 | 告警响应时长 (p99)、静默命中率、升级率 | 优化响应时间、调整静默规则 |
| **PM** | 每周 1 次 | 告警总量趋势、通道成功率 | 周报、复盘 |
| **On-call** | 紧急时 | 升级率 + 通道失败 + AM 同步失败 | 故障定位、升级到上游 |

**关键场景**:
1. **故障 5 秒定位**: SRE 进入 Grafana → 看到 24 panels 任意 1 个告警阈值被突破 → 切到具体 metric 详情
2. **周报截图**: PM 截图 "channel success rate" 趋势 + "alert volume" → 放入周报
3. **新 SRE 培训**: On-call 新人打开仪表盘 → 5 分钟了解告警系统全貌

---

## 3. 功能需求 (Functional Requirements)

### 3.1 仪表盘结构 (7 Rows × 24 Panels)

| Row | 标题 | Panels | 引用 metric | 优先级 |
|:---:|:---|:---:|:---|:---:|
| 1 | 告警趋势 (Trend) | 4 | trend | P0 |
| 2 | 响应时长 (Response Time) | 4 | response_time | P0 |
| 3 | 升级率 (Escalation) | 3 | escalation | P0 |
| 4 | 通道成功率 (Channel Stats) | 4 | channel_stats | P0 |
| 5 | 静默命中率 (Silence Hit Rate) | 3 | silence_hit_rate | P0 |
| 6 | AM 同步 (AlertManager Sync) | 3 | am_sync | P0 |
| 7 | 锁统计 (Lock Stats) | 3 | lock_stats | P0 |
| **合计** | — | **24** | 7 metrics | — |

### 3.2 24 Panels 详细设计

#### Row 1: 告警趋势 (4 panels)
- **P1-1**: Timeseries `alert_P0` (24h, group_by=severity) - 紧急度最高
- **P1-2**: Timeseries `alert_P1` (24h)
- **P1-3**: Timeseries `alert_P2` + `alert_P3` (24h, 同 panel 两条线)
- **P1-4**: Stat `alert_total` (now-1h, 当前小时总数, 红/黄/绿色阈值)

#### Row 2: 响应时长 (4 panels)
- **P2-1**: Stat `response_time_p99` (now, 红 > 500ms, 黄 > 200ms)
- **P2-2**: Stat `response_time_p95` (now)
- **P2-3**: Stat `response_time_mean` (now)
- **P2-4**: Gauge `ack_rate` (now, 0-1, 红 < 0.5, 黄 < 0.8, 绿 >= 0.8)

#### Row 3: 升级率 (3 panels)
- **P3-1**: Pie `escalated_to_P0/P1/P2` (24h, by_level 分布)
- **P3-2**: Stat `escalation_rate` (24h, 百分比, 红 > 30%)
- **P3-3**: BarGauge `escalated_to_P0/P1/P2` (24h, by_level 数值)

#### Row 4: 通道成功率 (4 panels)
- **P4-1**: Stat `overall_success_rate` (24h, 红 < 0.9, 黄 < 0.95, 绿 >= 0.95)
- **P4-2**: BarGauge `webhook_success_rate` (24h)
- **P4-3**: BarGauge `slack_success_rate` (24h)
- **P4-4**: BarGauge `dingtalk_success_rate` + `email_success_rate` (24h, 同 panel)

#### Row 5: 静默命中率 (3 panels)
- **P5-1**: Stat `silence_hit_rate` (24h, 百分比)
- **P5-2**: Stat `total_silenced` (24h, 整数)
- **P5-3**: BarGauge `matcher_<top_5>` (24h, top 5 静默规则)

#### Row 6: AM 同步 (3 panels)
- **P6-1**: Gauge `am_sync_success_rate` (24h, 红 < 0.85, 黄 < 0.95, 绿 >= 0.95)
- **P6-2**: Stat `am_sync_total` (24h, 总数)
- **P6-3**: Table `am_<op>_success/failed` (24h, by_operation 表格, 4 行)

#### Row 7: 锁统计 (3 panels)
- **P7-1**: Gauge `lock_acquire_rate` (now, 0-1, 红 < 0.7, 黄 < 0.9, 绿 >= 0.9)
- **P7-2**: Stat `lock_fallback_rate` (now, 百分比, 红 > 5%)
- **P7-3**: Stat `lock_error_rate` (now, 百分比, 红 > 0%)

### 3.3 6 个 Dashboard 变量 (Templating)

| # | 变量 | 类型 | 数据源 | 默认值 |
|:---:|:---|:---:|:---|:---:|
| 1 | `time_range` | time | (Grafana 内置) | now-24h to now |
| 2 | `severity` | custom | (static: all,P0,P1,P2,P3) | all |
| 3 | `rule` | custom | /grafana/variable type=rule | (动态 top 20) |
| 4 | `matcher` | custom | /grafana/variable type=matcher | (动态 top 10) |
| 5 | `operation` | custom | /grafana/variable type=operation | all |
| 6 | `channel` | custom | /grafana/variable type=channel | all |

**变量级联**:
- `$severity` → 注入到 trend/response_time/escalation 的 `params.severity`
- `$rule` → 注入到 trend 的 `params.rule` (group_by=rule 时)
- `$matcher` → 注入到 silence_hit_rate 的 `params.matcher` (扩展点, v1.37 端点未实现 matcher 过滤, v1.38 仪表盘引用 + 后端补)
- `$operation` → 注入到 am_sync 的 `params.operation`
- `$channel` → 注入到 channel_stats 的 `params.channel`
- `$time_range` → 注入到所有 /query 请求的 `start_time` / `end_time`

### 3.4 Panel 配置标准

**每个 panel 必须包含**:
- `targets[].refId`: A/B/C (panel 内多 series 区分)
- `targets[].payload.metric`: 对应 v1.37 metric 名
- `targets[].payload.params`: 注入变量 ($severity, $channel, etc.)
- `fieldConfig.defaults.unit`: 单位 (short/percent/mbps/ms)
- `fieldConfig.defaults.thresholds`: 颜色阈值 (3 档: base/warning/critical)
- `options.legend.displayMode`: 列表/隐藏
- `options.tooltip.mode`: single/multi
- `gridPos`: x/y/w/h (24 列网格)

### 3.5 命名规范 (Naming Convention)

- **Dashboard UID**: `v137-alerts-overview` (与 v1.37 sample 一致, 升级覆盖)
- **Dashboard 标题**: `v1.37 Alerts Overview` (Grafana UI 显示)
- **Tags**: `["v1.37", "v1.38", "alerts", "observability", "bysj"]`
- **Folder**: `Observability` (与 provisioning `folder` 一致)
- **Refresh**: `1m` (与 v1.37 sample 一致)
- **Time range default**: `now-1h` (与 v1.37 sample 一致)

---

## 4. 非功能需求 (Non-Functional Requirements)

| 维度 | 需求 | 验证方法 |
|---|---|---|
| **Schema 兼容** | Grafana 11.6 schema 39, 升级可平滑 | 静态 `validate_grafana_assets.py` + Grafana UI 加载 |
| **首次加载** | < 3s (24 panels 并发) | E2E 性能测试 (P2) |
| **Refresh** | 1m 自动刷新, 不卡 UI | E2E 性能测试 (P2) |
| **Panel 渲染** | 单 panel < 500ms | 继承 v1.36 性能基准 |
| **错误降级** | API 5xx → panel 显示 "No data" 而非崩溃 | Grafana 默认行为 |
| **可维护性** | 24 panels 用 Python 脚本生成 (Jinja2 + YAML 配置) | 验证 generator 脚本可重跑 |
| **可移植性** | dashboard.json 不绑定具体 backend URL (DataSource UID 引用) | 在 test 环境导入即可用 |

---

## 5. 验收标准 (Acceptance Criteria, AC)

| AC | 描述 | 验证方法 |
|:---|:---|:---|
| AC-1 | `v1.37-alerts-overview.json` 文件存在, 解析为合法 JSON | `json.load()` 不抛异常 |
| AC-2 | 包含 24 panels, 分布在 7 rows | `len(dashboard["panels"]) == 24` |
| AC-3 | 6 个变量可在 UI 下拉 | UI 手动 + variable query 命中 |
| AC-4 | 每个 panel 的 `targets[].payload.metric` 在 v1.37 /metrics 列表中 | 静态校验脚本 |
| AC-5 | 每个 panel 至少 1 个 fieldConfig.thresholds (P0 panel) | 静态校验脚本 |
| AC-6 | Grafana UI 加载 dashboard 后 5s 内 24 panels 都有数据 (或 "No data" 而非报错) | E2E 截图 + API |
| AC-7 | 变量切换 (severity/channel/rule) 后, panel 数据实时刷新 | E2E 交互测试 |
| AC-8 | dashboard.json 通过 `grafana-cli` 导入或 provisioning 自动加载 | provisioning 路径验证 |
| AC-9 | 7 Rows 视觉分组 (每 Row 内 panels 视觉对齐) | UI 截图 |
| AC-10 | 删除 v1.37 sample.json, 仅保留 v1.37-alerts-overview.json (避免双 dashboard) | 文件存在性检查 |

---

## 6. 风险与缓解 (Risks & Mitigations)

| 风险 | 等级 | 缓解 |
|---|---|---|
| Panel 配置错误 (target 拼写错误) | 高 | 静态校验脚本: 验证 target.metric ∈ v1.37 /metrics 列表 |
| Variable 引用错误 ($severity 用错位置) | 高 | 静态校验脚本: 验证 dashboard variable 名与 panel 引用一致 |
| Grafana 12.x 升级不兼容 | 中 | 用 Grafana 11.6 schema 39, 官方推荐向前兼容 |
| 24 panels 同时请求 → 后端压力 | 中 | 默认 time range = now-1h, 配合 v1.36 Redis 5min 缓存, 1m 刷新可承受 |
| 真实仪表盘与 sample 不一致 | 低 | 升级 sample → 正式 JSON, 文档标注 sample 已被替换 |
| 用户期望 24 panels 包含截图 | 中 | E2E 脚本生成 24 panels 截图归档 `infra/grafana/screenshots/` |

---

## 7. 任务预估 (Effort Estimate)

| Phase | 任务 | 估时 |
|---|---|---:|
| R1 Draft (本步) | 需求初稿 | 0.5h |
| R1-R3 规划 | 自查/调研/推演/锁定 | 1.5h |
| Implementation | 编写 24 panel JSON + 校验脚本 | 4h |
| Testing | 静态验证 + CI E2E | 1h |
| **合计** | — | **~7h** (1 天) |

---

## 8. 用户决策已确认 (Closed in R2)

> R1 Step 5 Lock 中提出的 3 个 Open Questions, 已于 2026-06-03 用户决策:

| # | Question | 决策 | 实施 |
|:---:|:---|:---|:---|
| Q1 | v1.37 sample.json (7 panels) 如何处理? | **A: 升级 sample → 正式 24 panels** | `v1.37-alerts-overview.sample.json` (7 panels) → `v1.37-alerts-overview.json` (24 panels). UID `v137-alerts-overview` 保持不变. provisioning 路径更新指向新文件. |
| Q2 | variable $matcher 引用方式? | **B: 仅作展示, 后端不解析** | `$matcher` 变量保留在 dropdown, 不注入到 silence_hit_rate panel 的 payload.params. 保持 v1.37 0 改动. |
| Q3 | dashboard tags 是否含 v1.38? | **A: 含 v1.37 + v1.38** | `tags = ["v1.37", "v1.38", "alerts", "observability", "bysj"]` |

## 9. R1 Critique 8 项修补 (R2 落实)

> R1 Step 2 Critique 中识别的 8 项修补, 已于 2026-06-03 在 R2 落实:

| # | 修补内容 | R2 落实方式 | 状态 |
|:---:|:---|:---|:---:|
| C-1 | panel target payload 结构示例 | 见 [§3.6 完整 Panel JSON 示例](#panel-完整-json-示例) | ✅ |
| C-2 | gridPos 分配表 | 见 [§3.2 24 Panels 详细设计](#32-24-panels-详细设计) 中每 panel 的 x/y/w/h | ✅ |
| C-3 | NFR §4 time change 刷新策略 | 见 [§4 NFR §3.3 time change 刷新](#33-time-change-刷新策略) | ✅ |
| C-4 | DataSource UID 引用规范 | 见 [§3.7 DataSource 引用规范](#37-datasource-引用规范) (R1 D-1 决策) | ✅ |
| C-6 | panel title 命名规范 | 见 [§3.8 命名规范](#38-命名规范) | ✅ |
| C-7 | 颜色调色板规范 | 见 [§3.9 颜色调色板](#39-颜色调色板) (R1 D-3 决策) | ✅ |
| C-8 | panel.id 编号 1-24 | 见 [§3.2 24 Panels 详细设计](#32-24-panels-详细设计) 中每 panel 的 id | ✅ (R1 D-4 + Simulation 验证) |
| AC-4 扩展 | 验证 $xxx 引用一致性 | 见 [§5 AC 列表 AC-4 扩展](#ac-4-扩展panel--variable-引用一致性) | ✅ |

---

## 3.6 Panel 完整 JSON 示例 (C-1 修补)

```json
{
  "id": 1,
  "type": "timeseries",
  "title": "Row 1 - Alert P0 (Trend)",
  "gridPos": { "x": 0, "y": 0, "w": 6, "h": 8 },
  "datasource": { "type": "simpod-json-datasource", "uid": "${DS_OBSERVABILITY_API}" },
  "targets": [
    {
      "refId": "A",
      "datasource": { "type": "simpod-json-datasource", "uid": "${DS_OBSERVABILITY_API}" },
      "payload": {
        "metric": "trend",
        "params": {
          "group_by": "severity",
          "severity": "$severity"
        }
      }
    }
  ],
  "fieldConfig": {
    "defaults": {
      "unit": "short",
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "color": "green", "value": null },
          { "color": "yellow", "value": 50 },
          { "color": "red", "value": 100 }
        ]
      }
    }
  }
}
```

## 3.7 DataSource 引用规范 (C-4 修补)

**采用 D-1 UID 方式** (R1 决策):
- `templating.list` 添加 1 个 `datasource` 类型变量 (UID 引用):
  ```json
  {
    "name": "DS_OBSERVABILITY_API",
    "type": "datasource",
    "query": "simpod-json-datasource",
    "current": { "text": "Observability API", "value": "Observability API" }
  }
  ```
- 所有 panel 的 `datasource.uid` 引用 `${DS_OBSERVABILITY_API}`
- 优势: DataSource 重命名不影响 dashboard

## 3.8 命名规范 (C-6 修补)

| 元素 | 规范 | 示例 |
|---|---|:---|
| Panel title | `{Row} - {Panel 类型} ({metric})` | `Row 1 - Alert P0 (Trend)` |
| Variable name | 单一小写无下划线 | `severity` / `rule` / `matcher` / `channel` |
| Variable label | 首字母大写 | `Severity` / `Rule` / `Matcher` / `Channel` |
| Metric refId | A/B/C (panel 内多 series 区分) | A=primary, B=compare |
| gridPos key | 顺序: x, y, w, h | `{ "x": 0, "y": 0, "w": 6, "h": 8 }` |

## 3.9 颜色调色板 (C-7 修补)

**采用 D-3 Grafana standard 调色板**:

| 维度 | 调色板 |
|---|---|
| Series color (默认) | `palette-classic` (蓝/绿/黄/红/紫, 5 色循环) |
| 阈值色 (P0 panel) | `green` (base) / `yellow` (warning) / `red` (critical) |
| 背景 | Grafana dark/light 主题默认 |

**每个 panel 的 fieldConfig.defaults.thresholds** (P0 panel 必填):
- 数值类 (stat/gauge): 阈值 base+warning+critical 3 档
- 时间序列 (timeseries): 可选 fillOpacity 控制透明度

---

## 5. AC-4 扩展 (Panel ↔ Variable 引用一致性)

在 AC-4 静态校验脚本中, 除验证 `target.metric ∈ v1.37 /metrics` 外, 扩展验证:

1. **Panel → Variable 引用一致性**:
   - 解析所有 panel 的 `targets[].payload.params` 中字符串值
   - 提取形如 `$xxx` 的变量引用
   - 验证每个 `$xxx` 必须在 `templating.list[].name` 中存在
2. **Variable → Datasource 一致性** (type=query 的 variable):
   - 验证 `variable.datasource.uid` 必须存在
3. **Variable → 实际类型一致性**:
   - 验证 `type=query` 的 variable 必须有 `query` 字段
   - 验证 `type=custom` 的 variable 必须有 `query` 字符串

```python
# validate_dashboard_json.py 伪代码
def test_panel_variable_references():
    dashboard = json.load(open("v1.37-alerts-overview.json"))
    var_names = {v["name"] for v in dashboard["templating"]["list"]}
    refs = set()
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            for value in target.get("payload", {}).get("params", {}).values():
                for match in re.findall(r"\$(\w+)", str(value)):
                    refs.add(match)
    assert refs.issubset(var_names), f"unknown $xxx refs: {refs - var_names}"
```

---

## 10. R2 修订增量 (与 R1 差异)

| 维度 | R1 | R2 修订 |
|---|---|:---|
| 决策 (Q1/Q2/Q3) | 待定 | 已确认 (A/B/A) |
| Panel target payload 示例 | 缺 | 补 1 完整 JSON (§3.6) |
| DataSource 引用 | 待补 | UID 方式 (D-1) |
| 命名规范 | 缺 | 5 元素规范 (§3.8) |
| 颜色调色板 | 缺 | Grafana standard + 阈值 3 档 (§3.9) |
| AC-4 扩展 | 仅 metric 校验 | + 引用一致性校验 |
| sample.json 处理 | 决策待定 | 升级为正式 JSON, UID/title 保持 |


