# v1.37 Round 3 Step 4 推演 (Simulation) — 任务时间

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 推演 16 任务实际执行时间, 验证 ~10h 估时合理

---

## 1. 任务时间表 (按依赖顺序)

| # | 任务 | 估时 | 累计 | 备注 |
|:---|:---|:---:|---:|:---|
| 1 | T-GRAF-001 require_sa_or_admin | 30min | 0.5h | 2 文件小改 |
| 2 | T-GRAF-002 GET /grafana/ + /health | 15min | 0.75h | 2 个简单路由 |
| 3 | T-GRAF-003 POST /grafana/metrics | 30min | 1.25h | 7 metric 静态列表 |
| 4 | T-GRAF-004 POST /grafana/variable | 1h | 2.25h | 4 type handler |
| 5 | T-GRAF-005 POST /grafana/query | 1h | 3.25h | 7 metric 调度 |
| 6 | T-GRAF-006 7 dataframe 适配器 | 2h | 5.25h | 略大, 7 个独立函数 |
| 7 | T-GRAF-007 注册路由 | 5min | 5.33h | 1 行 |
| 8 | T-GRAF-008 test_grafana_adapter | 1.5h | 6.83h | 15 tests |
| 9 | T-GRAF-009 test_grafana_auth | 30min | 7.33h | 3 tests |
| 10 | T-GRAF-010 test_v136_regression | 30min | 7.83h | 8 smoke tests |
| 11 | T-GRAF-011 provisioning YAML | 30min | 8.33h | 2 YAML |
| 12 | T-GRAF-012 docker-compose | 15min | 8.58h | service 块 |
| 13 | T-GRAF-013 .env.example | 10min | 8.75h | 4 行 |
| 14 | T-GRAF-014 README | 1h | 9.75h | 10 章节 |
| 15 | T-GRAF-015 v1.36 回归 227 测试 | 1min | 9.78h | CI 必跑 |
| 16 | T-GRAF-016 Grafana 端到端 | 30min | 10.28h | CI 专项 |

**总估时**: ~10.3h

## 2. 风险预留

| 风险 | 缓冲 | 总时长 |
|:---|:---:|---:|
| 调试 + 修复 | +20% | ~12.4h |
| 文档迭代 | +10% | ~13.6h |
| 集成问题 | +10% | ~15h |
| **保守估计** | — | **~15h** (~2 工作日) |

## 3. 里程碑划分

| 里程碑 | 任务 | 时长 | 检查点 |
|:---|:---|:---:|:---|
| **M1: 后端核心** | T-001~007 | ~5.5h | 5 路由 + 7 适配器 + 注册 |
| **M2: 单元测试** | T-008~010 | ~2.5h | 26 测试通过 |
| **M3: 部署资产** | T-011~014 | ~2h | YAML/compose/.env/README |
| **M4: 验证** | T-015~016 | ~30min | v1.36 227 通过 + Grafana 端到端 |
| **总计** | — | **~10.5h** | — |

## 4. 实际执行顺序建议

1. **Day 1 上午 (4h)**: T-001~006 (后端核心)
2. **Day 1 下午 (2h)**: T-007~010 (测试)
3. **Day 1 晚上 (1.5h)**: T-011~014 (部署)
4. **Day 2 上午 (0.5h)**: T-015 (v1.36 回归)
5. **Day 2 下午 (1h)**: T-016 (Grafana 端到端, P2 可选)

## 5. 关键瓶颈

| 瓶颈 | 任务 | 缓解 |
|:---|:---|:---|
| 7 个 dataframe 适配器 | T-GRAF-006 | 拆分为 7 个独立函数, 每个独立测试 |
| 15 个 adapter 测试 | T-GRAF-008 | 写测试 fixture 工厂复用 |
| README 200+ 行 | T-GRAF-014 | 分章节写, 每章节单独 review |

## 6. R3 决策 (R3S4 锁定)

| 决策 | 选定 |
|:---|:---:|
| 总工时估时 | ~10.3h (保守 ~15h) |
| 里程碑数 | 4 (M1~M4) |
| 实际执行跨度 | ~2 工作日 |
| 是否需要拆分任务 | 暂不, 实施时按需拆 |
| 是否需要补强估时 | 否, 现有估时含 20% 缓冲 |

---

> **R3 Step 4 完成**: 进入 R3 Step 5 (Lock) - 锁定 R3, 进入 Implementation Phase
