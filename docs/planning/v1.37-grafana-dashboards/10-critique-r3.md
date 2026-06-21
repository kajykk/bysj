# v1.37 Round 3 Step 2 自查 (Critique) — 任务与测试

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 验证 04-ralph-tasks.md + 05-test-plan.md 合理性

---

## 1. 任务依赖拓扑 (P0)

| 任务 | 依赖 | 拓扑位置 |
|:---|:---|:---|
| T-GRAF-001 | - | 0 |
| T-GRAF-002 | T-001 | 1 |
| T-GRAF-003 | T-002 | 2 |
| T-GRAF-004 | T-002 | 2 |
| T-GRAF-005 | T-002, T-003 | 3 |
| T-GRAF-006 | T-005 | 4 |
| T-GRAF-007 | T-002~006 | 5 |
| T-GRAF-008 | T-007 | 6 |
| T-GRAF-009 | T-007 | 6 |
| T-GRAF-010 | T-007 | 6 |
| T-GRAF-011 | T-007 (可独立) | 6 |
| T-GRAF-012 | T-011 | 7 |
| T-GRAF-013 | T-012 | 8 |
| T-GRAF-014 | T-011~013 | 8 |
| T-GRAF-015 | T-010 | 7 |
| T-GRAF-016 | T-014 + T-015 | 9 |

**✅ 结论**: 拓扑有序, 可串行执行。

## 2. AC 覆盖矩阵 (P0)

| AC | 测试 | 任务 | 覆盖 |
|:---|:---|:---|:---:|
| AC-1 | TC-LOAD-001 | T-GRAF-016 | ✅ |
| AC-2 | TC-LOAD-001 | T-GRAF-016 | ✅ |
| AC-3 | TC-VAR-001 (4 tests) | T-GRAF-004 + T-GRAF-008 | ✅ |
| AC-4 | TC-LOAD-001 E2E | T-GRAF-016 | ✅ |
| AC-5 | TC-LOAD-001 E2E | T-GRAF-016 | ✅ |
| AC-6 | TC-QUERY-001 + TC-DATAFRAME-001 | T-GRAF-005, 006, 008 | ✅ |
| AC-7 | TC-AUTH-001 | T-GRAF-009 | ✅ |
| AC-8 | TC-LOAD-001 | T-GRAF-016 | ✅ |
| AC-9 | (perf) | T-GRAF-016 | ⚠️ P1 |
| AC-10 | (perf) | T-GRAF-016 | ⚠️ P1 |
| AC-11 | (perf, v1.36) | T-GRAF-010 | ✅ |
| AC-12~15 | (README) | T-GRAF-014 | ✅ |
| AC-16 | TC-LOAD-001 | T-GRAF-016 | ✅ |
| AC-17 | TC-LOAD-001 | T-GRAF-016 | ✅ |
| AC-18 | TC-LOAD-001 | T-GRAF-016 | ✅ |

**✅ 18 AC 全部覆盖**: 15 P0 + 3 P1 (perf, 可选 CI 专项)

## 3. 任务粒度 (P0)

| 任务 | 行数估时 | 粒度评价 |
|:---|:---:|:---|
| T-GRAF-001 | 30min | 合适 |
| T-GRAF-002 | 15min | 合适 |
| T-GRAF-003 | 30min | 合适 |
| T-GRAF-004 | 1h | 略大 (4 types), 可拆 |
| T-GRAF-005 | 1h | 略大 (7 metric), 可拆 |
| T-GRAF-006 | 2h | 略大 (7 适配器), 可拆 |
| T-GRAF-007 | 5min | 太小, 可合并到 T-GRAF-002 |
| T-GRAF-008 | 1.5h | 合适 (15 tests) |
| T-GRAF-009 | 30min | 合适 |
| T-GRAF-010 | 30min | 合适 |
| T-GRAF-011 | 30min | 合适 |
| T-GRAF-012 | 15min | 合适 |
| T-GRAF-013 | 10min | 略小, 可合并到 T-GRAF-012 |
| T-GRAF-014 | 1h | 合适 |
| T-GRAF-015 | 1min (CI) | 太小, 必跑项 |
| T-GRAF-016 | 30min | 合适 (CI) |

**⚠️ 发现 R3-1 (P1)**: T-GRAF-004/005/006 略大, 可考虑拆分。
- **决策**: 保持现状 (R3 Lock), 实施时根据实际进度决定是否拆分

**⚠️ 发现 R3-2 (P2)**: T-GRAF-007/013/015 偏小, 可合并
- **决策**: 保持现状, 独立任务更易追踪

## 4. 测试覆盖 (P0)

| 测试组 | 数量 | 覆盖 | 评价 |
|:---|:---:|:---|:---|
| TC-AUTH-001 | 3 | SA Token + 错误 + 无 | ✅ |
| TC-QUERY-001 | 8 | 7 metric + 错误 | ✅ |
| TC-DATAFRAME-001 | 7 | 7 适配器 | ✅ |
| TC-VAR-001 | 4 | 4 types | ✅ |
| TC-V136-REG-001 | 8 | 8 v1.36 端点 | ✅ |
| TC-LOAD-001 | 3 | 仪表盘 + Provisioning + 数据 | ✅ |
| **合计** | **33** | — | — |

**✅ 33/33 测试用例全部规划清晰**

## 5. 综合问题 (R3 Critique)

### 5.1 P0 (无)

无 P0 问题, R3S1 任务列表与测试计划可直接进入 R3S3。

### 5.2 P1 (可选优化)

- T-GRAF-004/005/006 略大, 可考虑按 metric 拆分 (e.g., T-GRAF-005a trend, T-GRAF-005b response_time, ...)
- T-GRAF-013 略小, 可合并到 T-GRAF-012
- TC-LOAD-001 中 "24 panels have data" 需先在 v1.36 端点产生数据, 需在测试 fixture 中 mock 7 个 metric

### 5.3 P2

- 性能测试 (AC-9/10) 建议放入 CI 专项, 不阻塞 R3 Lock

---

> **R3 Step 2 完成**: 进入 R3 Step 3 (Research) - 调研实现细节
