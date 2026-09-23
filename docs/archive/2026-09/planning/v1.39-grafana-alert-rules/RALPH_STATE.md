# Ralph 项目状态 (Project State)

<!--
AI 指令:
1. 本文件是 Ralph 项目的**唯一事实来源 (Source of Truth)**, 任何状态变更必须同步更新此文件.
2. **生命周期**: 必须遵循 Planning (3 Rounds) -> Implementation -> Testing 的标准流程.
3. **顺序强制**: 在开发与测试阶段, 必须严格按照 `04-ralph-tasks.md` 和 `05-test-plan.md` 中的列表物理顺序执行, **严禁跳跃**或乱序执行.
4. **状态维护**: 每次 Skill 执行结束, 必须更新此文件中的进度条 (Progress) 和状态 (Status).
-->

> **当前上下文 (Current Context)**: ✅ **DELIVERED (核心完成)** / 15/17 PASS / 2 E2E 转 CI → **17/19 PASS (R3-PostDelivery 完成)**
> **迭代名称 (Iteration)**: v1.39-grafana-alert-rules
> **类型**: 可观测性 (DevOps / 配置)
> **基于**: v1.38-grafana-dashboard-json (TESTED & DELIVERED, 8/9 任务, 28/31 测试)
> **核心目标**: 在 v1.38 仪表盘基础上, 加 Grafana Alert Rules provisioning. 把"观测"升级为"响应". 6-8 条 P0/P1 告警规则 (通道成功率 / AM 同步 / 锁降级 / 升级率), 通过 webhook/email 通知.
> **预计工时**: 1-2 天 (P1, 中等规模)
> **实际工时**: 1 天 (14 任务 + 15 测试全部完成, 2 E2E 转 CI) + R3-PostDelivery 0.5 天 (T-AR-015~017, 3 任务, 4 测试)
> **启动时间**: 2026-06-03
> **R1 决策**: Q1=B(8条规则) / Q2=A(Webhook优先) / Q3=A(仅P2静音) / Q4=A(方案A Prometheus) / Q5=A(60s调度) / Q6=A(并存)
> **R1 评分**: 34/40 (基线)
> **R2 评分**: 38/40 (修订)
> **R3 评分**: 39/40 (终定, 2 项微调已应用)
> **R1 Research 关键发现**: simpod-json-datasource **不支持** alerting, 需扩展 Prometheus /metrics + 新增 Prometheus 数据源
> **R1 方案建议**: 方案 A (扩展 Prometheus /metrics + ObservabilityExporter 调度器)
> **R1-R3 状态**: ✅ 全部 LOCKED
> **Implementation**: ✅ 17/17 完成 (含 R3-PostDelivery 3 项)
> **Testing**: ✅ 17/19 PASS (本地 17 + CI 2, workflow 已创建)
> **Delivery**: ✅ DELIVERY_REPORT.md + NEXT_STEPS.md
> **下一步**: 用户验收, 部署到生产

---

## 1. 规划阶段 (Planning Phase)

> **目标**: 在编码前通过 3 轮迭代完善需求与架构.
> **特殊说明**: 本迭代为 DevOps 配置型 (非 Web 应用), 适配 3 轮规划框架.

| 轮次 (Round) | 步骤 1: 草稿 (Draft) | 步骤 2: 自查 (Critique) | 步骤 3: 调研 (Research) | 步骤 4: 推演 (Simulation) | 步骤 5: 锁定 (Lock) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Round 1** (基线) | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 |
| **Round 2** (修订) | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 |
| **Round 3** (终定) | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 | ✅ 完成 |

---

## 2. 开发阶段 (Implementation Phase)

> **目标**: 严格按顺序执行开发任务.
> **⚠️ 执行铁律**: 必须严格按照 `04-ralph-tasks.md` 中的列表顺序执行任务. **严禁跳跃**或乱序执行.

- **状态**: ✅ **完成 (Complete)**
- **进度**: 14 / 14 任务完成
- **引用**: `docs/planning/v1.39-grafana-alert-rules/04-ralph-tasks.md`

---

## 3. 测试阶段 (Testing Phase)

> **目标**: 使用测试计划验证功能.
> **⚠️ 执行铁律**: 必须严格按照 `05-test-plan.md` 中的列表顺序执行测试. **严禁跳跃**或乱序执行.

- **状态**: ✅ **完成 (Complete, 本地 15/17)**
- **进度**: 15 / 17 测试通过 (本地)
- **CI 专项**: 2 / 17 (E2E, Windows Blocked, 转 CI)
- **引用**: `docs/planning/v1.39-grafana-alert-rules/05-test-plan.md`

---

## 4. 项目交付 (Project Delivery) — 最终状态

- **状态**: ✅ **DELIVERED (核心完成)**
- **交付物**: [DELIVERY_REPORT.md](file:///e:/code/bysj/docs/planning/v1.39-grafana-alert-rules/DELIVERY_REPORT.md)
- **下一步**: [NEXT_STEPS.md](file:///e:/code/bysj/docs/planning/v1.39-grafana-alert-rules/NEXT_STEPS.md)

### 交付摘要
- 11 个文件 (4 后端 + 5 Grafana YAML + 3 测试) ~1130 行
- 8 metric + 10 规则 + 3 渠道 + 3 路由 + 1 静音
- 15/17 测试本地 PASS, 2 E2E 转 CI
- 0 回归 (v1.37 16/16, v1.38 7/7 PASS)
- 评分 39/40 (R3 LOCKED)

---

## 4. 项目交付 (Project Delivery)

- **最终审查**: [ ]
- **用户验收**: [ ]

---

## 5. 上一迭代交接

**v1.38-grafana-dashboard-json 交付状态** (2026-06-03):
- ✅ 8/9 任务完成 (1 Blocked CI 专项)
- ✅ 28/31 测试通过 (P0 100%, P2 0% Blocked)
- ✅ 24 panel 仪表盘: `infra/grafana/dashboards/v1.37-alerts-overview.json` (32.6 KB)
- ✅ 6 变量: time_range / severity / rule / matcher / operation / channel
- ✅ provisioning: `infra/grafana/provisioning/dashboards/alerts-overview.yaml`
- ✅ 构建脚本: `infra/grafana/scripts/build_dashboard.py` (YAML + Jinja2)
- ✅ 11 静态校验 + 7 Pytest 单元测试 + 1 E2E (待 CI)
- ✅ v1.37 0 回归 (25/25 PASS)

**v1.39 继承资源**:
- 24 panel 仪表盘 (v1.38 已交付, 0 改动)
- 7 v1.36 metric 数据源 (v1.37 已稳定)
- v1.37 5 Grafana 适配器端点 (0 改动)
- v1.37 /metrics 端点 (0 改动, 复用)
- Grafana 11.6 + simpod-json-datasource 容器 (v1.37 docker-compose 保留)
- provisioning 路径 `/etc/grafana/provisioning/alerting` (新)

**v1.38 已知限制 (驱动 v1.39 启动)**:
1. **v1.38 仅"观测", 无"响应"** - 通道成功率下降时, 需 SRE 主动打开仪表盘才能发现问题
2. **SLO 违规无主动通知** - P0 告警升级 / 锁降级 / AM 同步失败等场景, 缺乏自动通知
3. **NRT (Notification Routing) 缺失** - 告警应路由到 SRE 团队 / On-call 工程师, 而非散在仪表盘
4. **告警抑制规则缺失** - 高频告警可能引发告警风暴, 需配置 group/interval/silences

**v1.39 候选主题 (来源: v1.38 NEXT_STEPS.md §1.2)**:
| 主题 | 等级 | 范围 |
|---|---|---|
| Grafana Alert Rules | 高 | provisioning/alerting/*.yaml + 6-8 条阈值规则 + Notification channel |
| Dashboard 主题 (Dark/Light) | 中 | templates 修改 + 调色板 |
| 移动端断点 | 中 | panel gridPos 调整 |
| PDF/PNG 导出 | 低 | 集成 Grafana reports API |
| **用户决策** | **v1.39 = Grafana Alert Rules** | |

---

## 6. v1.39 候选告警规则 (来源: NEXT_STEPS.md §1.2)

| # | 规则名 | 触发条件 | 严重度 | 通知 |
|:---:|:---|:---|:---:|:---|
| R1 | ChannelSuccessRateLow | 整体通道成功率 < 90% (5m) | P1 | Webhook + Email |
| R2 | ChannelSuccessRateCritical | 整体通道成功率 < 80% (5m) | P0 | Webhook + Email + Slack |
| R3 | AMSyncSuccessRateLow | AM 同步成功率 < 85% (10m) | P1 | Webhook |
| R4 | AMSyncCriticalFailure | AM 同步成功率 < 70% (5m) | P0 | Webhook + Email |
| R5 | LockAcquireRateLow | 锁获取率 < 90% (5m) | P1 | Webhook |
| R6 | LockFallbackHigh | 锁降级率 > 5% (5m) | P1 | Webhook |
| R7 | LockErrorHigh | 锁错误率 > 0% (5m) | P0 | Webhook + Email |
| R8 | EscalationRateHigh | 升级率 > 30% (1h) | P1 | Email |
| R9 | ResponseTimeP99High | p99 响应时长 > 500ms (5m) | P1 | Webhook |
| R10 | AlertVolumeSpike | 告警总量 > 500/h | P2 | Email (daily) |

**目标**: 6-8 条 P0/P1 (R1-R8), 1 条 P2 批量通知 (R10)

---

> **最后更新**: 2026-06-04
> **状态**: ✅ v1.39 核心完成 + R3-PostDelivery 完成 + 部署验证完成 (commit 683b028 已 push origin/main)
> **交付物**: [DELIVERY_REPORT.md](file:///e:/code/bysj/docs/planning/v1.39-grafana-alert-rules/DELIVERY_REPORT.md) + [NEXT_STEPS.md](file:///e:/code/bysj/docs/planning/v1.39-grafana-alert-rules/NEXT_STEPS.md)
> **R3-PostDelivery (2026-06-04)**:
> - T-AR-015: `.env.example` 追加 4 个告警 env var (`GRAFANA_WEBHOOK_URL` / `GRAFANA_SRE_EMAIL` / `GRAFANA_SLACK_URL` / `GRAFANA_SLACK_CHANNEL`)
> - T-AR-016: `.github/workflows/v1.39-alerting-e2e.yml` (12 步骤, 覆盖 TC-AT-012/016/017)
> - T-AR-017: Exporter 启动日志代码审查 PASS (`ObservabilityExporter started` + `DB ready on attempt` + `DB not ready` warning 全部存在)
> **部署验证 (2026-06-04)**:
> - ✅ `.env` 创建 (占位符: `GRAFANA_WEBHOOK_URL=https://httpbin.org/post` + `GRAFANA_SRE_EMAIL=sre-alerts@example.invalid`, Slack 留空)
> - ✅ Git commit `683b028` 包含 30 个 v1.39 相关文件 (排除 PPT/论文/docker-compose 等无关文件)
> - ✅ Git push origin/main 成功 → CI workflow `v1.39-alerting-e2e` 待 trigger
> - ✅ 本地 uvicorn 启动后 `/api/v1/metrics` 暴露 8/8 observability_ 指标 (含 TYPE gauge/counter)
> - ⚠️ INFO 级别 "ObservabilityExporter started" 日志在默认 WARNING 级别下不显示, 但指标初始化与 60s 循环均正常 (FM-1 fallback 警告每 60s 出现)
