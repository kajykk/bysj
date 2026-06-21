# v1.37 Grafana 仪表盘模板 — Round 1 锁定 (Lock)

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **状态**: 🟢 **Round 1 LOCKED** - 基线需求/调研/推演全部完成
> **下一步**: 进入 Round 2 修订 (针对 Research + Simulation 发现的 P0/P1 问题)

---

## 1. Round 1 交付物清单 (锁定)

| 文档 | 路径 | 状态 | 行数 |
|:---|:---|:---:|---:|
| **01-requirements.md** | `docs/planning/v1.37-grafana-dashboards/01-requirements.md` | ✅ | ~250 |
| **01a-critique-r1.md** | `docs/planning/v1.37-grafana-dashboards/01a-critique-r1.md` | ✅ | ~220 |
| **02-research-r1.md** | `docs/planning/v1.37-grafana-dashboards/02-research-r1.md` | ✅ | ~250 |
| **03-simulation-r1.md** | `docs/planning/v1.37-grafana-dashboards/03-simulation-r1.md` | ✅ | ~150 |
| **v1.37-alerts-overview.sample.json** | `docs/planning/v1.37-grafana-dashboards/v1.37-alerts-overview.sample.json` | ✅ | 24.8 KB |
| **03-simulation-r1.py** | `docs/planning/v1.37-grafana-dashboards/03-simulation-r1.py` | ✅ | 推演脚本 |

---

## 2. Round 1 关键发现总结

### 2.1 已确认 (P0 锁定)

1. **v1.36 后端可观测端点**: 7 个数据源端点 (trend/response-time/escalation/channel-stats/silence-hit-rate/am-sync/lock-stats)
2. **Grafana JSON Datasource 路径**: `simpod-json-datasource`, 需 4 个必需 RPC 端点
3. **架构选型**: 单统一仪表盘 + JSON + Provisioning + 仅可视化 + Service Account Token
4. **角色**: SRE (主), Dev (次), PM (只读)
5. **7 Rows × 24 panels 结构**: 锁定不变

### 2.2 R2 必须解决 (P0)

| # | 问题 | 解决方案 | 估时 |
|:---|:---|:---|:---:|
| P0-1 | v1.36 后端是 REST 资源风格, JSON Datasource 需要 RPC | v1.37 包含后端 minor patch: 增加 Grafana Adapter 路由 (`/grafana/query`, `/grafana/variable`, `/grafana/health`) | 2-3h |
| P0-2 | v1.36 后端鉴权仅接受 JWT, 不接受 Grafana SA Token | v1.37 包含 minor patch: 增加 `get_current_user_or_service_account()` 依赖 + `GRAFANA_SERVICE_TOKEN` env var | 30min |

### 2.3 R2 应该解决 (P1)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P1-1 | POST body 解析与 GET query string 转换 | v1.37 Grafana Adapter 内部规范化 |
| P1-2 | rule 变量 JSON path 验证 | 测试用 `/grafana/variable` 返回 `{text, value}` 列表 |
| P1-3 | instance_id 简化为 static 文本 | 单实例场景下直接固定显示 |
| P1-4 | 5min 缓存导致 panel stale | README 明确说明, 不在 panel 内标注 |

### 2.4 R3 决定 (P2)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P2-1 | time_range/severity 切换需手动 E2E | 交付后写操作手册 |
| P2-2 | Grafana 导入兼容性需 CLI 验证 | CI 步骤加 `docker run` + `curl /api/dashboards/import` |

---

## 3. Round 2 修订计划 (5 步)

| 步骤 | 任务 | 目标 |
|:---|:---|:---|
| R2S1 | 编写 `04-architecture-r2.md` v2 版本 | 包含 v1.36 后端 minor patch 设计 + Grafana Adapter 路由规范 |
| R2S2 | 自查 R2 Draft | 检查 patch 不破坏 v1.36 现有功能 |
| R2S3 | 调研 v1.36 后端 minor patch 兼容性 | 验证 patch 不影响 224/224 v1.36 测试 |
| R2S4 | 推演 Grafana Adapter 端点 | mock 实现 + 单元测试 |
| R2S5 | 锁定 R2 修订 | 生成 `04-architecture-r2.md` 终稿 |

---

## 4. Round 3 终定计划 (5 步)

| 步骤 | 任务 | 目标 |
|:---|:---|:---|
| R3S1 | 编写 `05-tasks-r3.md` 终稿 | 7-8 个原子任务 (T-GRAF-001 ~ 008) |
| R3S2 | 自查任务依赖 | 检查 8 任务的拓扑排序 |
| R3S3 | 调研实现细节 | 文档/Provisioning/Python 测试模板 |
| R3S4 | 推演任务时间 | 估时 + 优先级 P0/P1 |
| R3S5 | 锁定 R3 + 生成 `04-ralph-tasks.md` + `05-test-plan.md` | 进入 Implementation Phase |

---

## 5. 关键决策记录 (R1 Lock)

### 5.1 架构决策

- **决策 1**: 使用 1 个统一仪表盘 (而非 7 个独立)
  - 理由: SRE 5 秒判断, 切换仪表盘是反模式
  - 影响: panel 数量较多 (24), 单 panel 宽度有限
- **决策 2**: 不嵌入 Grafana Alerting 规则
  - 理由: 告警逻辑应在业务后端 (v1.36), 仪表盘仅可视化
  - 影响: 仪表盘依赖业务后端告警
- **决策 3**: 包含 v1.36 后端 minor patch
  - 理由: 解决 REST vs RPC 不兼容 + SA Token 鉴权
  - 影响: v1.37 工作量增加 ~3h, 但解决 P0 阻塞

### 5.2 范围决策

- **包含**: Grafana JSON + Provisioning YAML + README + Python 测试 + v1.36 minor patch
- **不包含**: Grafana Alerting 规则 / 多集群 / 多租户 / 实时流式更新

### 5.3 验收标准决策 (R1 Lock)

- 24 panels 全部加载成功 (AC-1~6, AC-17)
- v1.36 鉴权兼容 (AC-7, R2 解决)
- Provisioning 加载 (AC-8)
- 性能 < 3s (AC-9~11)
- 文档完整 (AC-12~15)

---

## 6. Round 1 完成度

| 维度 | 完成度 | 评价 |
|:---|:---:|:---|
| 需求完整性 | 100% | 7 Rows × 24 panels 全部定义 |
| 可行性 | 90% | 待 R2 解决 P0-1 + P0-2 |
| 可测试性 | 100% | 18 AC 全部可被自动化测试覆盖 |
| 可观测性 | 80% | 待 R2 决定 Token 过期可视化 |

---

## 7. 用户验收 (R1 Lock)

请确认以下 Round 1 锁定内容:

- ✅ **架构**: 1 仪表盘 + JSON/Provisioning + 仅可视化 + SA Token
- ✅ **范围**: 7 Rows × 24 panels + 后端 minor patch
- ✅ **R2 待办**: Grafana Adapter 路由 + SA 鉴权路径

如确认, 进入 Round 2; 如有修改意见, 请指出, 我将回到 R1 修订。

---

> **Round 1 Step 5 完成**: 等待用户确认后进入 Round 2
