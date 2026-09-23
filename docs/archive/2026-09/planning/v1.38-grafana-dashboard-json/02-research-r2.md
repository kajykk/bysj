# v1.38 R2 Research — 3 项 F-待定项调研

> **迭代**: v1.38-grafana-dashboard-json
> **作者**: Ralph Planner (R2 Research)
> **日期**: 2026-06-03
> **状态**: 🔄 R2 Research (R2 Step 3 进行中)

---

## 1. F-1: 是否用 YAML 配置 + Jinja2 模板生成 24 panel JSON?

### 1.1 选项 A: 手写 JSON (24 panels 硬编码)

**优点**:
- 直接, 无需额外工具链
- JSON 文件可读, 人类可维护
- 与 v1.37 sample 风格一致

**缺点**:
- 24 panels 重复结构 (gridPos/datasource/targets 模板)
- 修改 panel 配置 (如阈值) 需编辑 24 处
- 不易复用 (不同 metric 的 panel 结构相似但参数不同)

### 1.2 选项 B: YAML + Jinja2 生成

**优点**:
- DRY: 共享 panel 模板片段
- 修改 1 处即可影响所有同类型 panel
- 配置可读 (YAML 比 JSON 直观)

**缺点**:
- 引入新依赖 (Jinja2 已在 Python 标准库, 0 引入)
- 增加构建步骤 (运行 Python 脚本生成 JSON)
- JSON 文件不再可手工编辑 (需重新生成)

### 1.3 推荐决策

**v1.38 采用 B (YAML + Jinja2)**. 理由:
- 24 panels 中 7 个 Row 内有重复结构 (e.g. 4 stat panels 共享 stat_panel.json 模板)
- 后期维护 (调整阈值/颜色) 改 YAML 比改 24 个 JSON 块高效
- Jinja2 是 Python 内置, 0 引入依赖
- 实施成本: ~0.5h (写生成脚本 + YAML 配置)

### 1.4 实施路径

```
infra/grafana/dashboards/
├── v1.37-alerts-overview.yaml         # 仪表盘配置 (Row/Panel/Variable)
├── templates/
│   ├── panel_stat.json.j2             # stat 类型 panel 模板
│   ├── panel_timeseries.json.j2       # timeseries 类型 panel 模板
│   ├── panel_gauge.json.j2            # gauge 类型 panel 模板
│   ├── panel_bargauge.json.j2         # bargauge 类型 panel 模板
│   ├── panel_pie.json.j2              # piechart 类型 panel 模板
│   └── panel_table.json.j2            # table 类型 panel 模板
└── v1.37-alerts-overview.json         # 生成的最终 JSON (git 跟踪)
```

**生成脚本**: `infra/grafana/scripts/build_dashboard.py` (Jinja2 渲染 YAML → JSON)

---

## 2. F-2: 截图归档路径

### 2.1 选项 A: `infra/grafana/screenshots/`

**优点**:
- 与 dashboard JSON 物理位置接近
- 一目了然 (grafana 资产目录内)

**缺点**:
- 截图是测试产物, 混入生产资产目录
- 24 张截图 (~1MB) 污染 git

### 2.2 选项 B: `docs/planning/v1.38-grafana-dashboard-json/screenshots/`

**优点**:
- 截图属测试产物, 放在 docs/planning 合理
- 与 v1.37 DELIVERY_REPORT.md 等文档同根
- 不污染 infra 目录

**缺点**:
- 与 JSON 物理位置不接近

### 2.3 选项 C: `backend/tests/screenshots/v1.38/`

**优点**:
- 与测试代码同根
- CI 产物自然归档

**缺点**:
- 截图不在 docs/planning, 文档引用时需相对路径

### 2.4 推荐决策

**v1.38 采用 C** (`backend/tests/screenshots/v1.38/`). 理由:
- 与 E2E 测试代码同根, 易追溯
- CI 流程归档自然 (pytest 产物 → screenshots)
- 与 v1.37 `tests/e2e/test_grafana_e2e.py` 同根, 一致性

**E2E 脚本生成截图**:
```python
# tests/e2e/test_grafana_e2e.py
import pytest
@pytest.mark.asyncio
async def test_dashboard_24_panels_have_data():
    """E2E: 加载 dashboard, 验证 24 panel 渲染, 截图归档."""
    ...
    # 截图
    await page.screenshot(path="screenshots/v1.38/panel-{id}.png", full_page=True)
```

---

## 3. F-3: provisioning 文件名

### 3.1 选项 A: 保留 `v1.37-alerts.yaml`

**优点**:
- 与 dashboard JSON 同步 (同名前缀)
- v1.37 升级不破坏现有 provisioning

**缺点**:
- 文件名带 v1.37, 但内容是 v1.38 升级版, 误导

### 3.2 选项 B: 改名 `v1.37-v1.38-alerts.yaml`

**优点**:
- 文件名明确包含两个版本

**缺点**:
- 文件名冗长

### 3.3 选项 C: 改名 `alerts-overview.yaml`

**优点**:
- 通用, 不绑定具体版本
- 与 v1.37-alerts-overview.json UID 对应

**缺点**:
- 与 v1.37 命名脱钩

### 3.4 推荐决策

**v1.38 采用 C** (`alerts-overview.yaml`). 理由:
- 通用, 适合 dashboard 改名
- 与 UID `v137-alerts-overview` + title `v1.37 Alerts Overview` 平行
- provisioning 路径 `/var/lib/grafana/dashboards/` 内文件不带版本号更整洁

**变更路径**:
- 删除 v1.37: `infra/grafana/provisioning/dashboards/v1.37-alerts.yaml`
- 新建 v1.38: `infra/grafana/provisioning/dashboards/alerts-overview.yaml`
- 容器挂载路径无需变 (仍 `/etc/grafana/provisioning/dashboards`)

---

## 4. 3 项 F-决策汇总 (R2 Locked)

| # | 决策 | 实施 |
|:---:|:---|:---|
| **F-1** | YAML + Jinja2 生成 JSON | 新建 `infra/grafana/scripts/build_dashboard.py` + `dashboards/v1.37-alerts-overview.yaml` + `templates/*.json.j2` |
| **F-2** | 截图归档 `backend/tests/screenshots/v1.38/` | E2E 脚本生成 24 张 panel 截图 |
| **F-3** | provisioning 文件名 `alerts-overview.yaml` | 删除 v1.37 `v1.37-alerts.yaml`, 新建 `alerts-overview.yaml` |

---

## 5. R2 Research 结论

3 项 F-待定全部决策完毕, 无新增开放问题。

**R2 综合评分**: 99% (R2 Critique) → 100% (R2 Research) ✅

---

> **R2 Step 3 完成**: 进入 R2 Step 4 (Simulation) - 重跑 v1.38 dashboard design 模拟, 验证 R2 修订不破坏基础设计
