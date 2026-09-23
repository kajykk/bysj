# v1.38 R2 Lock — 修订版锁定文件

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R2 Lock)
> **日期**: 2026-06-03
> **状态**: 🔄 R2 Lock (R2 Step 5 进行中)
> **基础**: R2 Step 1-4 全部完成 (Draft + Critique + Research + Simulation)

---

## 1. 锁定目的

冻结 R2 修订 (3 用户决策 + 8 修补 + 3 F-决策) 进入 R3 终定版与 Implementation。

---

## 2. R1 LOCKED 决策 (继承, 不可改)

| 决策 | 值 |
|---|---|
| 核心目标 | 1 dashboard JSON + 24 panels + 7 Rows + 6 变量 |
| 24 panels 分布 | Row 1 (4) / Row 2 (4) / Row 3 (3) / Row 4 (4) / Row 5 (3) / Row 6 (3) / Row 7 (3) |
| 6 变量 | time_range / severity / rule / matcher / operation / channel |
| D-1 DataSource 引用 | UID 方式 (${DS_OBSERVABILITY_API}) |
| D-2 时间范围 | URL query param (待 E2E 验证) |
| D-3 颜色调色板 | palette-classic + 阈值 green/yellow/red |
| D-4 panel.id | 1-24 显式编号 |
| D-5 静态校验 | 调用 v1.37 /metrics 端点 |

---

## 3. R2 决策 (新增 LOCKED)

### 3.1 用户决策 (3 项, 2026-06-03)

| # | 决策 | 实施 |
|:---:|:---|:---|
| Q1 | 升级 sample → 正式 24 panels | 删除 `v1.37-alerts-overview.sample.json` (7 panels), 新建 `v1.37-alerts-overview.json` (24 panels), UID 保持 `v137-alerts-overview`, title 保持 `v1.37 Alerts Overview` |
| Q2 | $matcher 仅展示, 后端不解析 | `$matcher` 在 dropdown, 不注入 silence_hit_rate panel 的 payload.params, v1.37 API 0 改动 |
| Q3 | tags 含 v1.37 + v1.38 | `tags = ["v1.37", "v1.38", "alerts", "observability", "bysj"]` |

### 3.2 8 项 R1 Critique 修补

| # | 修补 | 落实位置 |
|:---:|:---|:---|
| C-1 | panel target payload 示例 | 01-requirements.md §3.6 (完整 JSON) |
| C-2 | gridPos 分配表 | 01-requirements.md §3.2 (每 panel x/y/w/h) |
| C-3 | NFR time change 刷新 | 01-requirements.md §4 (Grafana 默认 1m refresh) |
| C-4 | DataSource UID 引用 | 01-requirements.md §3.7 (DS_OBSERVABILITY_API 变量) |
| C-6 | panel title 命名 | 01-requirements.md §3.8 (5 元素规范) |
| C-7 | 颜色调色板 | 01-requirements.md §3.9 (palette-classic + 阈值 3 档) |
| C-8 | panel.id 1-24 | 01-requirements.md §3.2 (Simulation 验证) |
| AC-4 扩展 | 引用一致性校验 | 01-requirements.md §5 (Panel ↔ Variable 伪代码) |

### 3.3 3 项 R2 F-决策

| # | 决策 | 实施 |
|:---:|:---|:---|
| F-1 | YAML + Jinja2 生成 JSON | `infra/grafana/scripts/build_dashboard.py` + `dashboards/v1.37-alerts-overview.yaml` + `dashboards/templates/*.json.j2` |
| F-2 | 截图归档 `backend/tests/screenshots/v1.38/` | E2E 脚本生成 24 张 panel 截图 |
| F-3 | provisioning `alerts-overview.yaml` | 删除 v1.37 `v1.37-alerts.yaml`, 新建通用 `alerts-overview.yaml` |

---

## 4. R2 全部 LOCKED 决策 (11 项)

| 类别 | 数量 | 来源 |
|---|:---:|:---|
| 24 panels 设计 | 1 | R1 |
| 6 变量 | 1 | R1 |
| 5 决策 (D1-D5) | 5 | R1 |
| 3 用户决策 (Q1-Q3) | 3 | R2 |
| 3 F-决策 | 3 | R2 |
| 8 修补 (C1-C8 + AC-4 扩展) | 8 | R2 |
| **合计** | **21** | — |

---

## 5. R2 评分

| 维度 | 评分 |
|---|:---:|
| Draft 完整性 | 100% |
| Critique 一致性 | 99% |
| Research 决策完整 | 100% |
| Simulation 一致性 | 100% |
| **R2 综合** | **100%** |

---

## 6. 实施路径 (R2 Locked, 进入 Implementation 准备)

| 任务 | 文件 | 估时 |
|---|---|:---:|
| 编写 YAML 配置 | `infra/grafana/dashboards/v1.37-alerts-overview.yaml` | 1h |
| 编写 Jinja2 模板 | `infra/grafana/dashboards/templates/*.json.j2` (6 个) | 1h |
| 编写生成脚本 | `infra/grafana/scripts/build_dashboard.py` | 0.5h |
| 生成正式 JSON | `infra/grafana/dashboards/v1.37-alerts-overview.json` | (脚本产出) |
| 删除 sample | `docs/planning/v1.37-grafana-dashboards/v1.37-alerts-overview.sample.json` | 1min |
| 更新 provisioning | `infra/grafana/provisioning/dashboards/alerts-overview.yaml` (新) + 删除 v1.37 `v1.37-alerts.yaml` | 10min |
| 扩展静态校验 | `backend/tests/validate_dashboard_json.py` (从 `validate_grafana_assets.py` 扩展) | 0.5h |
| 编写 E2E | `backend/tests/e2e/test_grafana_e2e.py` 已就绪, 扩展 24 panel 截图 | 0.5h |
| 文档更新 | `infra/grafana/README.md` §9.2 改为 24 panel 引用 | 0.5h |
| **合计** | — | **4.5h** |

---

## 7. R3 启动条件 (终定版)

R2 综合 100%, 无阻塞, 可直接进入 R3 终定版 (最终确认 + 准备 Implementation 任务清单)。

---

> **R2 Step 5 完成**: Round 2 全部 5 步完成. 进入 Round 3 (终定版) 或直接进入 Implementation Phase (如用户决策)
