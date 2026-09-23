# v1.38 Grafana 仪表盘 JSON 模板 — 开发任务 (Implementation Tasks)

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R3 Lock)
> **日期**: 2026-06-03
> **状态**: 🔒 LOCKED (等待 Implementation 启动)
> **基础**: R1+R2 决策全部 LOCKED (21 项), 实施路径 9 任务 4.5h

> **⚠️ 执行铁律**: 必须严格按照本文档的物理顺序执行任务. **严禁跳跃**或乱序执行.

---

## 任务清单 (按物理顺序)

### T-GRAF-001: 编写仪表盘 YAML 配置 [x]

- **路径**: `infra/grafana/dashboards/v1.37-alerts-overview.yaml`
- **内容**: Row 1-7 的 panel 定义 (24 个), 包含 id/title/metric/type/gridPos/params/unit/thresholds
- **依赖**: 无
- **估时**: 1h
- **AC**: AC-1 (JSON 合法) + AC-2 (24 panels 分布 7 rows)

### T-GRAF-002: 编写 6 个 Jinja2 Panel 模板 [x]

- **路径**: `infra/grafana/dashboards/templates/`
  - `panel_stat.json.j2`
  - `panel_timeseries.json.j2`
  - `panel_gauge.json.j2`
  - `panel_bargauge.json.j2`
  - `panel_piechart.json.j2`
  - `panel_table.json.j2`
- **内容**: 6 种 panel 类型的 JSON 模板, 接收 panel 配置作为变量
- **依赖**: T-GRAF-001
- **估时**: 1h
- **AC**: 模板可被 Jinja2 渲染为合法 JSON

### T-GRAF-003: 编写生成脚本 [x]

- **路径**: `infra/grafana/scripts/build_dashboard.py`
- **功能**: 加载 YAML + 渲染 Jinja2 → 输出 `v1.37-alerts-overview.json`
- **依赖**: T-GRAF-001 + T-GRAF-002
- **估时**: 0.5h
- **AC**: `python build_dashboard.py` 成功生成 24 panel JSON, exit 0

### T-GRAF-004: 升级 sample → 正式 JSON [x]

- **路径**: 
  - 删除: `docs/planning/v1.37-grafana-dashboards/v1.37-alerts-overview.sample.json`
  - 新建: `infra/grafana/dashboards/v1.37-alerts-overview.json` (T-GRAF-003 生成)
- **UID**: `v137-alerts-overview` (保持)
- **Title**: `v1.37 Alerts Overview` (保持)
- **Tags**: `["v1.37", "v1.38", "alerts", "observability", "bysj"]`
- **依赖**: T-GRAF-003
- **估时**: 1min (脚本产出 + 文件移动)
- **AC**: AC-1 (JSON 合法) + AC-10 (仅 1 个 JSON)

### T-GRAF-005: 更新 provisioning 文件 [x]

- **路径**: 
  - 删除: `infra/grafana/provisioning/dashboards/v1.37-alerts.yaml`
  - 新建: `infra/grafana/provisioning/dashboards/alerts-overview.yaml`
- **内容**: 引用 `v1.37-alerts-overview.json`, 启用 update interval 30s
- **依赖**: T-GRAF-004
- **估时**: 10min
- **AC**: AC-8 (provisioning 自动加载)

### T-GRAF-006: 扩展静态校验脚本 [x]

- **路径**: `backend/tests/validate_dashboard_json.py` (从 v1.37 `validate_grafana_assets.py` 扩展)
- **功能**:
  - 验证 JSON 合法 (AC-1)
  - 验证 24 panels 分布 7 rows (AC-2)
  - 验证 panel.id 1-24 连续 (C-8)
  - 验证 target.metric ∈ v1.37 /metrics (AC-4)
  - 验证 panel 引用的 $xxx 变量在 templating.list 中 (AC-4 扩展)
  - 验证 P0 panel 含 thresholds (AC-5)
  - 验证 gridPos 无重叠无溢出 (C-2)
- **依赖**: T-GRAF-004
- **估时**: 0.5h
- **AC**: AC-1, AC-2, AC-4, AC-5

### T-GRAF-007: 编写 Pytest 单元测试 [x]

- **路径**: `backend/tests/test_dashboard_template.py` (新建)
- **内容**: 7 个测试 (1 个 meta + 6 个功能)
  - `test_yaml_config_loads`: YAML 合法
  - `test_jinja2_templates_render`: 6 个模板可渲染
  - `test_generated_json_has_24_panels`: 生成后 24 panels
  - `test_panel_metrics_exist_in_v137`: 7 metric 全部存在
  - `test_panel_variable_references`: 引用一致性
  - `test_panel_id_continuity`: id 1-24 连续
  - `test_panel_gridpos_no_overlap`: 无重叠
- **依赖**: T-GRAF-006
- **估时**: 0.5h
- **AC**: 全部测试 PASS

### T-GRAF-008: 扩展 E2E 测试 (24 panel 截图) [-] (Blocked by: 需真实 Grafana 容器 + 后端运行, Windows 环境不可用. 按 Ralph Rule 12 标 Blocked, 代码已就绪待 CI 运行)

- **路径**: `backend/tests/e2e/test_grafana_e2e.py::test_dashboard_24_panels_have_data`
- **内容**:
  - 启动 Docker Grafana 容器 (复用 v1.37 脚本)
  - 加载 `v1.37-alerts-overview.json`
  - 等待 24 panels 全部渲染
  - 截图归档 `backend/tests/screenshots/v1.38/panel-{id}.png` (24 张)
  - 验证每个 panel 都有数据 (或显示 "No data" 而非报错)
- **依赖**: T-GRAF-005
- **估时**: 0.5h
- **AC**: AC-6 (UI 加载 < 5s 有数据) + AC-7 (变量切换 panel 刷新)
- **状态**: **P2, CI 专项, Windows 本地 Blocked** (按 Ralph Rule 12)

### T-GRAF-009: 更新 README + 文档 [x]

- **路径**: 
  - `infra/grafana/README.md` §9.2 改为 24 panel 引用
  - `docs/planning/v1.38-grafana-dashboard-json/DELIVERY_REPORT.md` (新建)
  - `docs/planning/v1.38-grafana-dashboard-json/NEXT_STEPS.md` (新建)
- **内容**: 24 panel 使用说明 + 变量切换 + 截图引用
- **依赖**: T-GRAF-008
- **估时**: 0.5h
- **AC**: README 包含 24 panel 完整引用 + 截图链接

---

## 任务统计

| 类别 | 数量 |
|:---:|:---:|
| 总任务 | 9 |
| P0 任务 | 8 (T-GRAF-001 ~ T-GRAF-007 + T-GRAF-009) |
| P2 任务 | 1 (T-GRAF-008, CI 专项) |
| 总估时 | 4.5h (1 个工作日) |
| 0 改动文件 | v1.37 5 端点 + provisioning + docker-compose + 鉴权 |

## 实施依赖图

```
T-GRAF-001 (YAML 配置)
   ↓
T-GRAF-002 (Jinja2 模板) ← T-GRAF-001
   ↓
T-GRAF-003 (生成脚本) ← T-GRAF-001 + T-GRAF-002
   ↓
T-GRAF-004 (正式 JSON) ← T-GRAF-003
   ↓
T-GRAF-005 (provisioning) ← T-GRAF-004
T-GRAF-006 (静态校验) ← T-GRAF-004
   ↓
T-GRAF-007 (Pytest) ← T-GRAF-006
T-GRAF-008 (E2E P2) ← T-GRAF-005
   ↓
T-GRAF-009 (README) ← T-GRAF-008
```

---

> **实施阶段就绪**: 9 任务 4.5h 全部就绪. 可启动 Implementation Phase.
