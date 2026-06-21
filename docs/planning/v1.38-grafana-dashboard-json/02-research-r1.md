# v1.38 Grafana 仪表盘 JSON 模板 — 调研报告 (Round 1 Step 3 Research)

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R1 Research)
> **日期**: 2026-06-03
> **状态**: 🔄 Research (R1 Step 3 进行中)
> **基础**: R1 Step 1 Draft + R1 Step 2 Critique

---

## 1. 调研目标

针对 R1 Critique 中识别的 8 项修补, 做技术验证, 给出可落地规范。

---

## 2. 调研 1: Grafana 11.6 schema 39 关键字段

### 2.1 仪表盘顶层结构 (已用 sample 验证)

```json
{
  "title": "v1.37 Alerts Overview",
  "uid": "v137-alerts-overview",     // 全局唯一, 升级时保持兼容
  "schemaVersion": 39,                // Grafana 11.6 推荐
  "version": 1,                       // dashboard 内部版本号
  "tags": ["v1.37", "v1.38", "alerts", "observability", "bysj"],
  "timezone": "browser",
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "1m",
  "templating": { "list": [...] },
  "panels": [...]
}
```

**结论**: 顶层结构 v1.37 sample 已通过 `validate_grafana_assets.py` 验证 ✅

### 2.2 Panel 标准结构

```json
{
  "id": 1,                            // 全局唯一, 用于变量引用 ${__panels.id}
  "type": "timeseries",               // panel 类型
  "title": "Row 1 - Alert P0 (Trend)",
  "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 },
  "datasource": { "type": "simpod-json-datasource", "uid": "${DS_OBSERVABILITY_API}" },
  "targets": [
    {
      "refId": "A",                   // panel 内多 series 区分
      "datasource": { "type": "simpod-json-datasource", "uid": "${DS_OBSERVABILITY_API}" },
      "payload": {                    // simpod-json-datasource 扩展
        "metric": "trend",            // v1.37 metric 名
        "params": {
          "severity": "$severity",    // 变量引用
          "group_by": "severity",
          "bucket": "1h"
        }
      }
    }
  ],
  "fieldConfig": {
    "defaults": {
      "unit": "short",                // 单位: short/percent/ms/mbps
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "color": "green", "value": null },
          { "color": "yellow", "value": 50 },
          { "color": "red", "value": 100 }
        ]
      },
      "custom": { "lineWidth": 2, "fillOpacity": 10 }
    }
  },
  "options": {
    "legend": { "displayMode": "list", "placement": "bottom" },
    "tooltip": { "mode": "multi" }
  }
}
```

**关键字段**:
| 字段 | 必填 | 用途 |
|---|:---:|---|
| `id` | ✅ | 显式编号 1-24, 防顺序错乱 |
| `type` | ✅ | timeseries / stat / gauge / barchart / bargauge / piechart / table |
| `gridPos` | ✅ | x/y/w/h, 24 列网格, w 范围 1-24, h 范围 1-∞ |
| `datasource.uid` | ✅ | 引用 `templating.list[].name = "DS_OBSERVABILITY_API"` |
| `targets[].payload` | ✅ | simpod-json-datasource 扩展字段 |
| `fieldConfig.defaults.unit` | ✅ | 单位影响 tooltip/legend 显示 |
| `fieldConfig.defaults.thresholds` | ⚠️ 可选 | P0 panel 必填, 用于红/黄/绿 |

### 2.3 Templating (Variable) 结构

```json
{
  "name": "severity",                  // 引用名: $severity
  "type": "custom",                    // custom/query/interval/datasource
  "label": "Severity",
  "query": "all,P0,P1,P2,P3",         // custom: 静态值 (逗号分隔)
  "current": { "text": "all", "value": "all" },
  "hide": 0,                           // 0 显示, 1 标签, 2 隐藏
  "refresh": 1                         // 1=On dashboard load
}
```

**query 类型** (Grafana 从 v1.37 /grafana/variable 拉取):
```json
{
  "name": "rule",
  "type": "query",
  "datasource": { "type": "simpod-json-datasource", "uid": "${DS_OBSERVABILITY_API}" },
  "query": {
    "type": "rule",                    // v1.37 variable type
    "metric": ""                       // 暂留空
  },
  "refresh": 1,
  "includeAll": true,
  "allValue": "all"
}
```

**结论**: Variable `query` 类型需要 v1.37 /variable 端点配合, 已就绪 ✅

### 2.4 Datasource 引用规范

**方案 A (推荐)**: 显式 UID 引用
- 在 `templating.list` 添加一个 `datasource` 类型的变量
- Panel 中 `datasource.uid = "${DS_OBSERVABILITY_API}"`
- 优势: DataSource 改名不影响 dashboard

**方案 B (简单)**: 直接名称引用
- Panel 中 `datasource.name = "Observability API"`
- 优势: 简单
- 劣势: 重命名后需更新 24 panels

**v1.38 决策**: **方案 A** (更可移植, 符合 Grafana 最佳实践)

---

## 3. 调研 2: simpod-json-datasource Payload 规范

### 3.1 /query 请求 payload (v1.37 已用)

```json
{
  "metric": "trend",                   // 必填
  "params": {                          // 可选, metric-specific
    "severity": "P0",                  // 直接值 (无 $)
    "group_by": "severity"
  }
}
```

### 3.2 变量引用方式

**方式 1: payload 字符串内嵌 (Grafana 模板变量)**:
```json
"params": {
  "severity": "$severity"              // Grafana 自动替换
}
```

**方式 2: datasource query payload (动态变量)**:
- `query` 类型变量调 `/variable` 时, Grafana POST:
  ```json
  { "type": "rule" }                   // → v1.37 解析
  ```

### 3.3 time_range 传递方式

v1.37 端点已支持 (R2S3 决策):
- URL query param: `?start_time=2026-06-03T00:00:00Z&end_time=...`
- 格式: ISO 8601 with Z suffix

**Grafana 内置变量**:
- `$__from` / `$__to`: 时间范围 (epoch ms, 整数)
- `$__timeFrom()` / `$__timeTo()`: ISO 字符串 (10位epoch s, 与 v1.37 不匹配, **存在隐患**)

**v1.38 建议**:
- 用 `datasources[].jsonData.timeField` 不适用 (Grafana 内置)
- 用 URL query param 传入 v1.37 端点:
  - 在每个 panel target 加 `urlData` 或 `extraParams` 字段
  - simpod-json-datasource 默认行为: 把 `$__from`/`$__to` 转为 query param
- **验证**: 在 R2 Simulation 中跑一次, 确认 v1.37 端点能解析

---

## 4. 调研 3: Panel 类型选择矩阵

| Panel 类型 | 用途 | 适用场景 | v1.38 适用数 |
|---|---|---|:---:|
| `timeseries` | 时间序列 | 趋势 (P1, P4 部分) | 4-6 |
| `stat` | 大数字 + 颜色 | 当前值 (P2-1, P3-2, P4-1, P5-1/2, P6-2) | 8-10 |
| `gauge` | 仪表盘 (0-100%) | 比率 (P2-4, P6-1, P7-1) | 3 |
| `bargauge` | 横向条形 | 分类对比 (P3-3, P4-2/3/4, P5-3, P7-2/3) | 7-8 |
| `piechart` | 饼图 | 分布 (P3-1) | 1 |
| `table` | 表格 | 明细 (P6-3) | 1 |
| **合计** | — | — | **24** |

**颜色调色板** (Grafana standard):
- `palette-classic`: 蓝/绿/黄/红/紫 (5 色, 默认)
- 阈值色: `green` (<50%), `yellow` (50-100%), `red` (>100%) — 仅 P0 panel

---

## 5. 调研 4: v1.37 /metrics 端点返回的 metric 列表

(用于 AC-4 静态校验)

```python
# v1.37 已实现
GET POST /api/v1/alerts/observability/grafana/metrics
→ 返回 7 metric: trend / response_time / escalation / channel_stats / silence_hit_rate / am_sync / lock_stats
```

**结论**: AC-4 可全自动校验 (调用 v1.37 /metrics 后, 与 dashboard target.metric 集合做差集)

---

## 6. 调研 5: GridPos 分配 (24 panels 排版)

24 列网格, 标准 Row 高度 8px:

| Row | 范围 y | Panels | 排版 |
|:---:|:---:|:---:|:---|
| 1 (Trend) | 0-7 | 4 | 6+6+6+6 (4 panels 一行, 16x8) |
| 2 (Response Time) | 8-15 | 4 | 6+6+6+6 (4 panels 一行) |
| 3 (Escalation) | 16-23 | 3 | 8+8+8 (3 panels 一行, pie + stat + bargauge) |
| 4 (Channel) | 24-31 | 4 | 6+6+6+6 (4 panels 一行) |
| 5 (Silence) | 32-39 | 3 | 8+8+8 (3 panels 一行) |
| 6 (AM Sync) | 40-47 | 3 | 8+8+8 (3 panels 一行) |
| 7 (Lock) | 48-55 | 3 | 8+8+8 (3 panels 一行) |

**校验**: 静态脚本验证 `sum(gridPos.w for p in panels where p.gridPos.y == Y) <= 24`

---

## 7. R1 调研结论与 R2 行动

### 7.1 关键决策 (R2 采纳)

| # | 决策 | 来源 |
|:---:|:---|:---|
| D-1 | **DataSource 引用用 UID 方式** (`${DS_OBSERVABILITY_API}`) | 调研 2.4 |
| D-2 | **时间范围用 URL query param 传递** (依赖 simpod-json-datasource 默认行为) | 调研 3.3 |
| D-3 | **颜色用 Grafana standard 调色板** (palette-classic + 阈值 green/yellow/red) | 调研 4 |
| D-4 | **panel.id 显式编号 1-24** (避免顺序错乱) | 调研 2.2 |
| D-5 | **静态校验脚本调用 v1.37 /metrics 端点** (AC-4) | 调研 5 |

### 7.2 仍待 R2 解决

- **Q1**: v1.37 sample.json (7 panels) 是否升级为正式 24-panel JSON, 还是新建 dashboard-24p.json?
- **Q2**: variable `$matcher` 引用方式: 注入 silence_hit_rate 的 params.matcher (需后端扩展) 还是仅展示?
- **Q3**: dashboard tags 是否包含 `v1.38`?

### 7.3 仍待 R2 验证 (Simulation)

- D-2 验证: simpod-json-datasource 是否真的把 `$__from`/`$__to` 转为 URL query param
- D-5 验证: 静态校验脚本如何与 v1.37 /metrics 端点集成 (需 backend 启动)

---

> **R1 Step 3 完成**: 进入 R1 Step 4 (Simulation) - 推演 24 panel 渲染 + 变量切换全流程
