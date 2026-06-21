# v1.38 Grafana 仪表盘 JSON 模板 — 锁定文件 (Round 1 Step 5 Lock)

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R1 Lock)
> **日期**: 2026-06-03
> **状态**: 🔄 Lock (R1 Step 5 进行中)
> **基础**: R1 Step 1-4 (Draft + Critique + Research + Simulation) 全部通过

---

## 1. 锁定目的

冻结 R1 决策, 防止后续 R2/R3 误改基础设计。同时为 R2 提供清晰的输入与待办。

---

## 2. R1 决策 (LOCKED, 不可改)

### 2.1 核心范围

| 决策 | 锁定值 | 来源 |
|---|---|:---:|
| **核心目标** | 提供 1 个生产级 Grafana Dashboard JSON 模板, 含 24 panels | R1-Draft §1.2 |
| **架构基础** | 0 改动 v1.37 API + 0 改动后端代码 + 0 改动 provisioning | R1-Research §3 |
| **文件变更** | 1 个新文件 (`v1.37-alerts-overview.json` 替换 sample) + 1 个新测试文件 + 1 个静态校验脚本扩展 | R1-Research §2 |
| **后端调用** | 完全复用 v1.37 5 端点 (0 改动) | R1-Research §3.1 |

### 2.2 24 Panels 设计 (LOCKED)

| Row | 标题 | Panels | 范围 (y) |
|:---:|:---|:---:|:---:|
| 1 | 告警趋势 (Trend) | 4 | 0-7 |
| 2 | 响应时长 (Response Time) | 4 | 8-15 |
| 3 | 升级率 (Escalation) | 3 | 16-23 |
| 4 | 通道成功率 (Channel Stats) | 4 | 24-31 |
| 5 | 静默命中率 (Silence Hit Rate) | 3 | 32-39 |
| 6 | AM 同步 (AlertManager Sync) | 3 | 40-47 |
| 7 | 锁统计 (Lock Stats) | 3 | 48-55 |
| **合计** | — | **24** | — |

每 panel 详细设计见 [01-requirements.md §3.2](file:///e:/code/bysj/docs/planning/v1.38-grafana-dashboard-json/01-requirements.md)

### 2.3 6 个 Dashboard 变量 (LOCKED)

| # | 变量 | 类型 | 数据源 |
|:---:|:---|:---:|:---|
| 1 | `time_range` | time | (Grafana 内置) |
| 2 | `severity` | custom | (static) |
| 3 | `rule` | query | /grafana/variable type=rule |
| 4 | `matcher` | query | /grafana/variable type=matcher |
| 5 | `operation` | custom | (static) |
| 6 | `channel` | custom | (static) |

### 2.4 技术决策 (LOCKED, D1-D5)

| # | 决策 | 来源 |
|:---:|:---|:---|
| **D-1** | DataSource 引用用 **UID 方式** (`${DS_OBSERVABILITY_API}`) | R1-Research §2.4 |
| **D-2** | 时间范围用 **URL query param** 传递 (依赖 simpod-json-datasource 默认) | R1-Research §3.3 |
| **D-3** | 颜色用 **Grafana standard 调色板** (palette-classic + 阈值 green/yellow/red) | R1-Research §4 |
| **D-4** | **panel.id 显式编号 1-24** (避免顺序错乱) | R1-Critique C-8 |
| **D-5** | 静态校验脚本调用 v1.37 /metrics 端点 (AC-4) | R1-Research §5 |

### 2.5 验收标准 (LOCKED, AC-1 ~ AC-10)

| AC | 描述 | 验证方法 |
|:---|:---|:---|
| AC-1 | `v1.37-alerts-overview.json` 合法 JSON | `json.load()` |
| AC-2 | 24 panels, 7 rows | `len == 24` + row 分布 |
| AC-3 | 6 变量可下拉 | UI + variable query |
| AC-4 | target.metric ∈ v1.37 /metrics | 静态校验 |
| AC-5 | P0 panel 含 thresholds | 静态校验 |
| AC-6 | UI 加载 < 5s 有数据 | E2E |
| AC-7 | 变量切换 panel 刷新 | E2E 交互 |
| AC-8 | provisioning 自动加载 | E2E |
| AC-9 | 7 Rows 视觉分组 | UI 截图 |
| AC-10 | 仅 1 个 dashboard.json (sample 已被替换) | 文件存在性 |

---

## 3. R1 评分 (综合 97%)

| 维度 | 评分 | 来源 |
|---|:---:|:---|
| 完整性 | 95% | R1-Critique §6 |
| 可行性 | 100% | R1-Research §3 |
| 可测试性 | 95% | R1-Critique §4 |
| 可观测性 | 100% | R1-Critique §5 |
| **综合** | **97%** | — |

**结论**: ✅ R1 PASS, 可进入 R2

---

## 4. R2 待办 (基于 R1 遗留)

### 4.1 决策 (用户参与, 3 项)

| # | Open Question | 推荐选项 |
|:---:|:---|:---|
| Q1 | sample.json (7 panels) 处理 | **A: 升级 sample → 正式 24 panels** (避免双文件) |
| Q2 | variable $matcher 引用方式 | **B: 仅作展示, 后端不解析** (避免 v1.38 改动 v1.37 API) |
| Q3 | dashboard tags | **A: tags = ["v1.37", "v1.38", ...]** (标识迭代历史) |

### 4.2 修补 (8 项 R1 Critique 遗留)

| # | 内容 | 优先级 |
|:---:|:---|:---:|
| C-1 | panel target payload 结构示例 | 高 |
| C-2 | gridPos 分配表 | 高 (R1 Simulation 已验证) |
| C-3 | NFR §4 time change 刷新策略 | 低 |
| C-4 | DataSource UID 引用规范 | 中 (R1 D-1 已决策) |
| C-6 | panel title 命名规范 | 低 |
| C-7 | 颜色调色板规范 | 中 (R1 D-3 已决策) |
| C-8 | panel.id 编号 1-24 | 中 (R1 D-4 + Simulation 已验证) |
| AC-4 扩展 | 验证 $xxx 引用一致性 | 中 |

### 4.3 验证 (2 项 R1 Research 遗留)

| 编号 | 验证内容 |
|:---:|:---|
| D-2 | simpod-json-datasource 是否把 `$__from`/`$__to` 转为 URL query param (E2E) |
| D-5 | 静态校验脚本与 v1.37 /metrics 端点集成 (Pytest fixture) |

---

## 5. R1 输出清单 (已交付)

| 文档 | 路径 | 行数 | 状态 |
|:---|:---|:---:|:---:|
| 需求初稿 | [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.38-grafana-dashboard-json/01-requirements.md) | ~280 | ✅ |
| 自查报告 | [01a-critique-r1.md](file:///e:/code/bysj/docs/planning/v1.38-grafana-dashboard-json/01a-critique-r1.md) | ~200 | ✅ |
| 调研报告 | [02-research-r1.md](file:///e:/code/bysj/docs/planning/v1.38-grafana-dashboard-json/02-research-r1.md) | ~270 | ✅ |
| 推演报告 | [03-simulation-r1.md](file:///e:/code/bysj/docs/planning/v1.38-grafana-dashboard-json/03-simulation-r1.md) | ~180 | ✅ |
| 锁定文件 | [04-lock-r1.md](file:///e:/code/bysj/docs/planning/v1.38-grafana-dashboard-json/04-lock-r1.md) | (本文件) | ✅ |
| 模拟脚本 | [v1_38_dashboard_design.py](file:///e:/code/bysj/backend/tests/simulations/v1_38_dashboard_design.py) | ~180 | ✅ |

---

## 6. R1 铁律合规检查

| 铁律 | 状态 | 证据 |
|---|:---:|---|
| Draft (Step 1) 真实完成 | ✅ | 280 行 8 节需求文档 |
| Critique (Step 2) 4 维度全覆盖 | ✅ | 完整性/可行性/可测试性/可观测性 |
| Research (Step 3) 5 调研有据 | ✅ | Grafana 官方 + simpod-json-datasource 文档 + v1.37 /metrics |
| Simulation (Step 4) 可执行 | ✅ | 6 项校验全部 PASS |
| Lock (Step 5) 含决策冻结 | ✅ | D1-D5 + 24 panel 详细 + 6 变量 + 10 AC 全部 LOCKED |
| 严格顺序 | ✅ | 1→2→3→4→5, 无跳步 |
| RALPH_STATE.md 同步 | ✅ | 每次 Step 完成后立即更新 |

---

> **R1 Step 5 完成**: Round 1 (基线) 全部 5 步完成. 进入 Round 2 (修订) 需用户决策 Q1/Q2/Q3 后启动.
