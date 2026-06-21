# v1.38 Grafana 仪表盘 JSON 模板 — 自查报告 (Round 1 Step 2 Critique)

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R1 Critique)
> **日期**: 2026-06-03
> **状态**: 🔄 Critique (R1 Step 2 进行中)
> **基础**: R1 Step 1 Draft `01-requirements.md`

---

## 1. 自查范围与方法

对 R1 Draft 需求做 4 维度自查 (完整性 / 可行性 / 可测试性 / 可观测性), 识别遗漏与改进点。

---

## 2. 维度 1: 完整性 (Completeness)

### 2.1 已有内容 (✅)

| 类别 | 覆盖情况 |
|---|:---:|
| 7 metric 全覆盖 | ✅ Row 1-7 完整覆盖 v1.36 7 metric |
| 24 panels 设计 | ✅ 完整 panel 列表 + target/fieldConfig/gridPos |
| 6 变量 | ✅ time_range/severity/rule/matcher/operation/channel |
| 10 AC 标准 | ✅ 1-10 全部定义 |
| 6 风险缓解 | ✅ 高/中/低分级 |
| 任务预估 | ✅ ~7h (1 天) |

### 2.2 遗漏识别 (⚠️ 需补)

| # | 遗漏 | 影响 | 建议 |
|:---:|:---|:---|:---|
| **C-1** | **未指定 Panel target 的具体 payload.params 结构** | 开发者不知如何在 panel target 中嵌入变量 (e.g. `{"severity": "$severity"}`) | 补 1 个 panel 配置示例 (JSON 片段) |
| **C-2** | **未指定 gridPos 数值** (x/y/w/h) | 7 Rows × 24 panels 排版无规范, 可能挤在一行 | 补 gridPos 分配表 (24 列网格) |
| **C-3** | **未指定 dashboard 重复加载策略** (refresh on time range change) | 切换时间范围时是否强制刷新 panels? | 在 NFR §4 增加 Grafana `time` 配置要求 |
| **C-4** | **未指定 data source UID** | Grafana UI 用 datasource UID 引用, 而非 name | 补 DataSource 引用规范 (uid 与 name 映射) |
| **C-5** | **未明确 v1.37 sample.json 处理** (Open Q1) | 升级后双文件风险 | R2 Step 3 决策时明确 |
| **C-6** | **未指定 panel title 命名规范** | 当前混用 P1-1/告警趋势 P0 等 | 补命名模板: "{Row} - {Panel 类型} ({metric})" |
| **C-7** | **未指定颜色调色板** (现在用 red/yellow/green, 与 Grafana 调色板不一致) | Grafana 默认有 `palette-classic` 等 | 补调色板: 用 Grafana standard 配色 |
| **C-8** | **未指定 panel 顺序 (排序键)** | 当 metric 动态变化时, panel 显示顺序可能错乱 | 补 `panels[].id` 显式编号 |

### 2.3 完整性结论

**覆盖率**: 90% (8 项遗漏, 5 项可由 R2 解决, 3 项需 R1 补)
**行动**: 进入 R1 Step 3 Research, 同时补 5 项 C-1/C-2/C-4/C-7/C-8 (可直接补到 R1 Draft, 无需新调研)

---

## 3. 维度 2: 可行性 (Feasibility)

### 3.1 技术可行性 (✅ 全部可行)

| 项 | 评估 | 证据 |
|---|---|---|
| Grafana 11.6 schema 39 兼容 | ✅ 已用 v1.37 sample 验证 | validate_grafana_assets.py |
| 24 panels 排版在 1 dashboard | ✅ Grafana 单 dashboard 支持 100+ panels | 官方文档 |
| simpod-json-datasource 支持 multi-panel 渲染 | ✅ 与 v1.37 adapter 完全一致 | 端到端 5 测试通过 |
| time_range 变量全局生效 | ✅ Grafana 内置 | 官方文档 |
| 6 变量同时定义 | ✅ Grafana templating 支持 10+ | 官方文档 |
| 24 panels 静态生成 (不靠运行时拼接) | ✅ JSON 文件直接写 | 与 v1.37 sample 一致 |

### 3.2 资源可行性 (✅ 满足)

| 资源 | 评估 |
|---|:---:|
| v1.37 5 端点 (0 改动) | ✅ 完全复用 |
| v1.36 7 _compute_* 函数 (0 改动) | ✅ 数据源稳定 |
| provisioning YAML 路径 (0 改动) | ✅ 复用 `infra/grafana/provisioning/dashboards/v1.37-alerts.yaml` |
| docker-compose (0 改动) | ✅ 复用 grafana service |
| 静态校验脚本 (`validate_grafana_assets.py`) | ✅ v1.37 已就绪, 可扩展 |

### 3.3 工作量可行性 (✅ 满足)

| Phase | 估时 | 实际约束 |
|---|:---:|---|
| R1 规划 | 0.5h | 1h 已投入 |
| R2 规划 | 0.5h | 与 R3 合并可缩短 |
| R3 规划 | 0.5h | |
| Implementation | 4h | 主要写 JSON 模板 + 生成脚本 |
| Testing | 1h | 静态验证 + CI E2E |
| **合计** | **~7h** | **1 个工作日可行** |

### 3.4 可行性结论

**可行性**: 100% — 所有技术 / 资源 / 工作量均无阻塞。

---

## 4. 维度 3: 可测试性 (Testability)

### 4.1 可测试的维度 (✅ 全部可测)

| AC | 测试方法 | 自动化 |
|---|---|:---:|
| AC-1 JSON 合法 | `json.load()` | ✅ |
| AC-2 24 panels 分布 7 rows | `len(dashboard["panels"]) == 24` + 递归 row 统计 | ✅ |
| AC-3 6 变量下拉 | UI 手动 + variable query API | ⚠️ 需 UI |
| AC-4 target.metric ∈ v1.37 /metrics | 静态校验脚本 | ✅ |
| AC-5 P0 panel 含 thresholds | 静态校验脚本 | ✅ |
| AC-6 UI 加载 < 5s 有数据 | Grafana API `/api/dashboards/uid/...` | ✅ E2E |
| AC-7 变量切换 panel 刷新 | UI 交互 + 后端 API 日志 | ⚠️ 需 UI |
| AC-8 provisioning 加载 | Grafana 启动日志 + `/api/search` | ✅ E2E |
| AC-9 7 Rows 视觉分组 | 截图比对 | ⚠️ 视觉 |
| AC-10 仅 1 个 dashboard.json | `ls infra/grafana/dashboards/` | ✅ |

### 4.2 测试覆盖盲区

| 盲区 | 缓解 |
|---|---|
| Panel target 内嵌变量未自动验证 | 在 AC-4 扩展: 验证 `payload.params` 中引用的 `$xxx` 变量必须存在于 `templating.list` |
| Grid 排版视觉无算法验证 | 静态校验: `sum(gridPos.w) <= 24` for each row |
| Panel 顺序不固定 | 静态校验: `panels[].id` 1-24 连续 |

### 4.3 测试基础设施

- 复用 v1.37 `tests/validate_grafana_assets.py` + 扩展为 `validate_dashboard_json.py`
- 新增 `tests/test_dashboard_template.py` (静态校验 5 测试)
- 复用 v1.37 `tests/e2e/test_grafana_e2e.py` (E2E 4 测试, 其中 1 已在 v1.37 通过, 1 新增)

### 4.4 可测试性结论

**可测试性**: 95% — 8 AC 可全自动, 2 AC 需 UI (降级为视觉/截图)。

---

## 5. 维度 4: 可观测性 (Observability)

### 5.1 仪表盘本身的可观测性 (✅ 满足)

| 维度 | 评估 |
|---|:---:|
| Dashboard header (version + tags) | ✅ v1.37 / v1.38 / bsysj tags |
| Refresh 状态 | ✅ `1m` 自动刷新 |
| Variables 当前值显示 | ✅ Grafana 模板自带下拉 |
| Time range 当前值显示 | ✅ Grafana 模板自带时间选择器 |
| Panel "No data" vs 错误 | ✅ Grafana 默认行为, 5xx → "No data" |

### 5.2 v1.38 引入的可观测资产

- `infra/grafana/dashboards/v1.37-alerts-overview.json` (24 panels)
- `infra/grafana/dashboards/screenshots/` (E2E 截图归档, 24 张)
- `tests/validate_dashboard_json.py` (静态校验, 可被 CI 调用)
- `tests/test_dashboard_template.py` (5 个静态测试)

### 5.3 可观测性结论

**可观测性**: 100% — 仪表盘元信息 + 截图 + 静态测试三重保障。

---

## 6. 4 维度综合评分

| 维度 | 评分 | 阻塞 |
|---|:---:|:---:|
| 完整性 | 90% | 8 项遗漏中 5 项可在 R1 修补 |
| 可行性 | 100% | 0 |
| 可测试性 | 95% | 0 |
| 可观测性 | 100% | 0 |
| **综合** | **96%** | **无阻塞, R1 可进入 Step 3 (Research)** |

---

## 7. R1 修补行动 (进入 R1 Step 3 前必做)

| 编号 | 修补内容 | 优先级 |
|:---:|:---|:---:|
| C-1 | 补 panel target payload 结构示例 | 高 |
| C-2 | 补 gridPos 分配表 (24 列网格) | 高 |
| C-4 | 补 DataSource UID 引用规范 | 中 |
| C-7 | 补颜色调色板规范 (Grafana standard) | 中 |
| C-8 | 补 panels[].id 编号 1-24 | 中 |
| C-3 | 补 NFR §4 time change 刷新策略 | 低 |
| C-6 | 补 panel title 命名规范 | 低 |
| AC-4 扩展 | 验证 panel 引用的 `$xxx` 变量必须在 `templating.list` | 中 |

---

> **R1 Step 2 完成**: 进入 R1 Step 3 (Research) - 调研 Grafana 11.6 schema 细节 + simpod-json-datasource payload 规范
