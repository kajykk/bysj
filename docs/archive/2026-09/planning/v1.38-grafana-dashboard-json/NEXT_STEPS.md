# v1.38 Grafana 仪表盘 JSON 模板 — 下一步建议 (Next Steps)

> **迭代**: v1.38-grafana-dashboard-json
> **完成时间**: 2026-06-03
> **状态**: 实施完成 (8/9, 1 Blocked)

---

## 1. 立即行动 (P0)

### 1.1 CI 验证 Blocked E2E 测试

**任务**: 在 CI/Docker 环境运行 `tests/e2e/test_grafana_e2e.py::test_dashboard_24_panels_screenshots`

**预计**: CI 工作流 5-10 分钟

**验收**:
- 24 panels 全部加载
- 24 张截图归档 `backend/tests/screenshots/v1.38/panel-{id}.png`
- 每 panel 都有数据 (或 "No data" 而非报错)

### 1.2 启动 v1.39 Grafana Alert Rules (推荐)

**主题**: 在 v1.38 仪表盘基础上, 加告警规则 provisioning
**范围**:
- 6-8 条告警规则 (P0/P1)
- 阈值: 通道成功率 < 90%, AM 同步 < 85%, 锁降级 > 5% 等
- 通知: webhook + email
**价值**: 把"观测"升级为"响应"
**估时**: 1-2 天

---

## 2. 短期优化 (P1)

### 2.1 仪表盘主题适配 (Dark/Light)

v1.38 仪表盘当前使用 Grafana 默认主题. 可在 panel `options` 中显式指定, 提升可读性.

**任务**: 在 `templates/panel_*.json.j2` 添加 `options.theme: "dark"` 或 "light"

### 2.2 移动端断点优化

24 panels 在移动端 (width < 768px) 拥挤. 可设置 panel 在窄屏下自动 gridPos.w = 24 (单列).

**任务**: 添加 `panel.repeat` 或 Grafana panel repeat variables 机制.

### 2.3 仪表盘导出 (PDF/PNG)

提供一键导出仪表盘 PDF/PNG, 用于周报附件.

**任务**: 集成 Grafana `/api/reports` (企业版) 或自建 Playwright 截图脚本.

---

## 3. 中期演进 (P2)

### 3.1 v1.40 数据归档 (TimescaleDB / ClickHouse)

**背景**: v1.36 7 metric 数据当前存 Redis (5min TTL). 长期趋势查询 (30 天) 不可行.
**方案**: 集成 TimescaleDB (PG extension) 或 ClickHouse, 提供 1 年趋势查询.
**价值**: 季度/年度告警可观测性.
**估时**: 3-5 天.

### 3.2 v1.41 多租户 / Per-Instance 仪表盘

**背景**: 当前仪表盘是单租户视图. 多集群部署时, 每个集群需独立仪表盘.
**方案**: 添加 `$instance` 变量, 渲染时按 instance 切片.
**价值**: 规模化部署 (10+ 集群).
**估时**: 2-3 天.

### 3.3 v1.42 告警自愈 (Auto-Remediation)

**背景**: 锁降级时手动重启后端服务, 可改为自动.
**方案**: 集成 ArgoCD/Flux, 触发自动 rollback.
**价值**: MTTR (Mean Time To Recovery) 降低 50%.
**估时**: 5-7 天.

---

## 4. 长期规划 (P3)

### 4.1 v2.0 微前端化 (Grafana Plugins)

将 v1.38 仪表盘拆为 3 个独立 Grafana App Plugin:
- `bysj-alerts-trend` (Row 1-2)
- `bysj-channels` (Row 4)
- `bysj-system` (Row 6-7)

### 4.2 v2.1 AI 异常检测

集成 Prophet / LSTM, 自动学习 metric 基线, 异常告警 (而非固定阈值).

---

## 5. 已知遗留 (跨迭代)

| # | 遗留 | 来源 | 优先级 |
|:---:|:---|:---|:---:|
| 1 | v1.37 `test_dashboard_24_panels_have_data` CI 验证 | T-GRAF-008 (Blocked) | P0 |
| 2 | v1.14 全量回归测试在 Windows 不稳定 | 历史 | P1 (需 Linux/CI) |
| 3 | v1.36 性能基线 (panel < 500ms) 端到端验证 | v1.36 (未实测) | P2 |

---

## 6. 文档维护

| 文档 | 路径 | 维护频率 |
|:---|:---|:---:|
| DELIVERY_REPORT.md | `docs/planning/v1.38-grafana-dashboard-json/` | 实施后 |
| NEXT_STEPS.md | `docs/planning/v1.38-grafana-dashboard-json/` | 每迭代 |
| README §9.2.1 | `infra/grafana/README.md` | 添加/修改 panel 后 |
| v1.37 E2E | `backend/tests/e2e/test_grafana_e2e.py` | CI 失败时 |

---

## 7. 资源索引 (v1.38 输出)

| 类别 | 路径 | 行数/大小 |
|---|---|---:|
| 规划文档 | `docs/planning/v1.38-grafana-dashboard-json/*.md` | ~2,000 行 |
| 仪表盘配置 | `infra/grafana/dashboards/v1.37-alerts-overview.yaml` | 9.4 KB |
| Jinja2 模板 | `infra/grafana/dashboards/templates/*.json.j2` | ~8 KB |
| 生成脚本 | `infra/grafana/scripts/build_dashboard.py` | 4.7 KB |
| 最终 JSON | `infra/grafana/dashboards/v1.37-alerts-overview.json` | 32.6 KB |
| Provisioning | `infra/grafana/provisioning/dashboards/alerts-overview.yaml` | 0.7 KB |
| 静态校验 | `backend/tests/validate_dashboard_json.py` | 7.5 KB |
| 单元测试 | `backend/tests/test_dashboard_template.py` | 5.2 KB |
| E2E (CI) | `backend/tests/e2e/test_grafana_e2e.py` | 扩展 1 测试 |
| 模拟脚本 | `backend/tests/simulations/v1_38_dashboard_design.py` | 180 行 |

---

> **v1.38 已完成实施 (8/9) + Planning (3 Rounds, 100%)**. 建议下一步: 启动 v1.39 Grafana Alert Rules 迭代.
