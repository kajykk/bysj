# v1.37-grafana-dashboards: 下一步建议 (NEXT_STEPS)

> **状态**: v1.37 已 DELIVERED. 本文档指导后续工作.
> **生成时间**: 2026-06-03

---

## 1. 立即行动 (Immediate Actions)

### 1.1 部署到测试环境

- [ ] 在 staging 环境拉取最新代码
- [ ] 按 `DELIVERY_REPORT.md` §4 创建 Grafana SA Token
- [ ] 启动 `docker compose up -d grafana`
- [ ] 浏览器访问 http://localhost:3000 验证

### 1.2 跑通 CI E2E 测试

- [ ] 在 CI 环境 (GitHub Actions / Jenkins) 配置:
  ```yaml
  - name: Grafana E2E Test
    run: |
      docker compose up -d backend grafana
      sleep 30
      pytest backend/tests/e2e/test_grafana_e2e.py -v
  ```
- [ ] 验证 5 个 e2e 测试全部通过

### 1.3 验证 v1.36 完整回归

- [ ] 在 CI 环境运行完整 224 测试:
  ```bash
  cd backend
  pytest tests/ --no-cov -q
  ```
- [ ] 预期: 224/224 + 26/26 (v1.37 新增) = 250/250 通过

---

## 2. v1.38 候选主题 (Recommended Next Iteration)

### 2.1 仪表盘 JSON 模板 (推荐, 高价值)

**背景**: v1.37 提供了 API + provisioning, 但仪表盘 JSON 模板待补. 用户需手动创建 24 panels.

**目标**: 提供即用型仪表盘 JSON, 24 panels 完整覆盖 7 metrics.

**任务预估**:
- 创建 `infra/grafana/dashboards/v1.37-alerts-overview.json` (24 panels)
- 每个 panel 配置: targets (引用 /grafana/query) + variables (rule/matcher/channel)
- 测试: 加载 + 24 panel 都有数据 + 截图

**价值**: 真正 "开箱即用", 用户部署即可看到完整 dashboard.

### 2.2 告警规则 (Alert Rules, 中价值)

**背景**: Grafana 支持在 panel 上配置 alert 规则. v1.37 提供了数据, 但未提供告警规则模板.

**目标**: 在 provisioning 中加入 alert rules, 异常时通过 Webhook 通知.

### 2.3 移动端适配 (Mobile Layout, 中价值)

**背景**: 24 panels 桌面端可读, 移动端需要折叠布局.

**目标**: 仪表盘支持 `mobile: { breakpoint: 768 }` 配置, 小屏自动切换 stat 类型.

### 2.4 数据归档 (Data Archiving, 低价值/高成本)

**背景**: 当前仪表盘只显示最近 24h 数据. 历史趋势需要归档.

**目标**: 引入 TimescaleDB / ClickHouse 存储 90 天历史.

---

## 3. 风险与缓解 (Risks & Mitigations)

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| Grafana 容器内存占用高 | 中 | docker-compose 已设 `memory: 512M`, 可监控 |
| SA Token 泄露 | 中 | 定期轮换 (90 天) + 不入 git + CI 注入 |
| 后端 Grafana 端点被滥用 | 低 | 鉴权 (SA + Admin) + 时间范围限制 |
| 仪表盘 JSON 与新 metric 不同步 | 中 | v1.38 添加 CI 校验, dashboard.json 引用的 metric 必须在 metrics endpoint 中存在 |
| Windows 端测试不稳定 | 中 | 完整测试必须在 CI 跑 (Ralph Rule 12) |

---

## 4. 长期路线图 (Long-term Roadmap)

- **v1.38**: 仪表盘 JSON 模板 + Alert Rules
- **v1.39**: 多租户支持 (per-tenant dashboards)
- **v1.40**: 数据归档 (90 天历史)
- **v1.41**: ML 异常检测 (基于历史趋势的智能阈值)
- **v1.42**: 移动 App (Grafana Mobile)
- **v1.50**: 完整可观测性平台 (Logs + Metrics + Traces 统一)

---

## 5. 经验总结 (Learnings)

### 5.1 Ralph Rule 7 (健康) 验证

✅ **架构设计**: 双路径鉴权 (SA + Admin) 优雅, 兼容 v1.36 + 新 Grafana
✅ **增量修改**: 0 破坏性变更, 仅新增 4 文件 + 3 文件修改
✅ **测试覆盖**: 单元 + 集成 + E2E 三层防护
✅ **文档先行**: 5 个规划文档 (R1-R3) + 1 个 README, 知识可传承

### 5.2 待改进

⚠️ **CI 优先**: 完整测试在 Windows 不可行, 应一开始就建立 CI 流水线
⚠️ **仪表盘 JSON 模板**: 应在 v1.37 一起提供, 而不是 v1.38 补
⚠️ **e2e 测试覆盖**: 当前只有 Grafana e2e, 关键业务流 (e.g. 告警→通知) 仍需补充

### 5.3 v1.37 状态指标

- 16 / 16 任务完成 (100%)
- 29 / 29 本机测试通过
- 0 破坏性变更
- 4 新文件 + 3 修改文件 (代码)
- 6 新文件 (provisioning + docs)
- ~ 1000 行新增代码 (含测试和文档)

---

## 6. 行动号召 (Call to Action)

**建议优先执行**:
1. 立即行动 §1.1 部署到测试环境
2. 立即行动 §1.2 配置 CI E2E 测试
3. 立即行动 §1.3 完整回归验证
4. 启动 v1.38 (仪表盘 JSON 模板)
