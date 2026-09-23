# v1.8 测试计划：覆盖率冲刺与质量门禁落地

> **迭代名称**: v1.8-coverage-sprint-and-quality-gates  
> **文档类型**: Test Plan  
> **版本**: Round 1 Draft  
> **日期**: 2026-04-29  
> **状态**: Draft  
> **测试/验证点总数**: 86

---

## 1. 测试目标

v1.8 测试计划用于验证以下目标：

1. v1.8 真实质量基线已建立
2. 后端覆盖率达到必达目标
3. services/ML/tasks 核心模块覆盖率提升
4. pytest 主路径稳定
5. 契约测试实际运行并记录
6. 前端 type/lint/test/build 稳定
7. 前端核心模块 coverage 建立
8. quick/standard/full 质量门禁分层可执行
9. 性能与交付指标可追踪

---

## 2. 测试范围

### 2.1 范围内

- 后端 pytest 收集与执行
- 后端 coverage 总体与模块级验证
- services 单元测试
- ML/tasks 单元测试
- API 契约测试
- 前端 ESLint/type-check/Vitest/build
- 前端 coverage
- bundle/chunk 基线
- 质量门禁验证
- 最终交付文档一致性验证

### 2.2 范围外

- 后端整体覆盖率 85% 必达验证
- 前端整体 coverage 80% 必达验证
- full gate 全量强制阻断验证
- 全量 E2E 必须稳定阻断验证

---

## 3. Phase 0: 基线验证 (10 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-BASE-001 | pytest collect-only 可运行 | 输出测试数量，无阻塞收集错误 | P0 | [x] Done |
| TC-BASE-002 | 后端 coverage 可运行 | 生成 term-missing/html/xml | P0 | [x] Done |
| TC-BASE-003 | 后端总覆盖率可记录 | 记录真实百分比 | P0 | [x] Done |
| TC-BASE-004 | low coverage Top 20 可提取 | 形成优先级清单 | P0 | [x] Done |
| TC-BASE-005 | OpenAPI schema 可导出 | schema 文件生成 | P0 | [x] Done |
| TC-BASE-006 | Schemathesis smoke baseline 可运行 | 记录通过/失败 | P0 | [x] Blocked (环境限制) |
| TC-BASE-007 | Schemathesis full baseline 可运行或 blocked 可解释 | 记录结果或阻塞原因 | P0 | [x] Blocked (环境限制) |
| TC-BASE-008 | 前端 type/lint/test/build baseline 可运行 | 记录错误和测试结果 | P0 | [x] Blocked (环境限制) |
| TC-BASE-009 | 前端 coverage baseline 可生成 | 生成 coverage 报告或记录阻塞 | P1 | [x] Blocked (环境限制) |
| TC-BASE-010 | `BASELINE_V1.8.md` 内容完整 | 包含所有基线项 | P0 | [x] Done |

---

## 4. Phase 1: 测试稳定性验证 (8 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-STAB-001 | pytest marker 定义完整 | 不出现 unknown marker | P0 | [x] Done |
| TC-STAB-002 | slow 测试可排除 | quick profile 不运行 slow | P0 | [x] Done |
| TC-STAB-003 | contract 测试可单独运行 | contract profile 可执行 | P0 | [x] Done |
| TC-STAB-004 | requires_external 测试可隔离 | 默认测试不依赖外部服务 | P0 | [x] Done |
| TC-STAB-005 | quick profile 可执行 | 快速通过或失败可定位 | P0 | [x] Done |
| TC-STAB-006 | standard profile 可执行 | coverage/openapi/contract smoke 纳入 | P0 | [x] Done |
| TC-STAB-007 | full profile 可执行或 blocked 可记录 | full gate 有状态 | P1 | [x] Done |
| TC-STAB-008 | 主路径无收集阻塞 | pytest 主路径稳定 | P0 | [x] Done |

---

## 5. Phase 2: services 覆盖率验证 (16 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-SVC-001 | auth_service happy path | 返回正确结果 | P0 | [x] Done |
| TC-SVC-002 | auth_service error/permission path | 抛出或返回预期错误 | P0 | [x] Done |
| TC-SVC-003 | risk_service 风险计算路径 | 风险结果正确 | P0 | [x] Done |
| TC-SVC-004 | risk_service 边界与异常路径 | 边界值和异常可处理 | P0 | [x] Done |
| TC-SVC-005 | warning_service 创建/查询路径 | 预警逻辑正确 | P0 | [x] Done |
| TC-SVC-006 | warning_service 异常路径 | 异常可控 | P0 | [x] Done |
| TC-SVC-007 | intervention_service 状态流转 | 状态变更正确 | P0 | [x] Done |
| TC-SVC-008 | intervention_service 权限/冲突路径 | 错误处理正确 | P0 | [x] Done |
| TC-SVC-009 | user_data_service 数据读写 | 数据返回和变更正确 | P0 | [x] Done |
| TC-SVC-010 | model_predict_service 预测路径 | 预测结果结构正确 | P0 | [x] Done |
| TC-SVC-011 | model_predict_service fallback/error | fallback 与异常正确 | P0 | [x] Done |
| TC-SVC-012 | validation_engine 规则校验 | 校验结果正确 | P0 | [x] Done |
| TC-SVC-013 | admin/counselor/content services smoke | 核心路径可用 | P1 | [x] Done |
| TC-SVC-014 | export services smoke | 文件导出 mock 路径可用 | P1 | [x] Done |
| TC-SVC-015 | experiment services smoke | 实验核心路径可用 | P1 | [x] Done |
| TC-SVC-016 | services 覆盖率达标 | >= 65% | P0 | [x] Done |

---

## 6. Phase 3: ML/tasks 覆盖率验证 (13 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-ML-001 | data_cleaner 缺失值处理 | 输出符合预期 | P0 | [x] Done |
| TC-ML-002 | data_cleaner 异常类型处理 | 错误可控 | P0 | [x] Done |
| TC-ML-003 | data_loader 小样本加载 | 数据可加载 | P0 | [x] Done |
| TC-ML-004 | data_loader 文件异常 | 异常处理正确 | P0 | [x] Done |
| TC-ML-005 | feature_engineering 特征生成 | 特征列正确 | P0 | [x] Done |
| TC-ML-006 | evaluation 指标计算 | 指标近似正确 | P0 | [x] Done |
| TC-ML-007 | statistical_tests 统计断言 | 结果稳定 | P0 | [x] Done |
| TC-ML-008 | model_loader 加载成功 | 返回模型对象或 mock | P0 | [x] Done |
| TC-ML-009 | model_loader 加载失败 fallback | fallback 正确 | P0 | [x] Done |
| TC-ML-010 | drift_detector 边界检测 | drift 结果正确 | P0 | [-] Blocked |
| TC-ML-011 | fusion_engine 缺失模态 | 融合结果稳定 | P0 | [-] Blocked |
| TC-TASK-001 | scheduler 注册/调度 | 注册和调度逻辑正确 | P0 | [x] Done |
| TC-ML-012 | ML/tasks 覆盖率达标 | ML >= 50%, tasks >= 40% | P0 | [x] Done |

---

## 7. Phase 4: 契约测试验证 (9 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-CONTRACT-001 | OpenAPI schema 导出 | 成功生成 schema | P0 | [x] Done |
| TC-CONTRACT-002 | ErrorResponse schema 存在 | 错误响应结构统一 | P0 | [x] Done |
| TC-CONTRACT-003 | protected endpoints 401/403 定义 | 定义完整 | P0 | [x] Done |
| TC-CONTRACT-004 | Schemathesis smoke 运行 | 可运行并记录 | P0 | [x] Blocked |
| TC-CONTRACT-005 | Schemathesis full 运行 | 可运行或 blocked 可解释 | P0 | [x] Blocked |
| TC-CONTRACT-006 | 契约失败分类 | 分类完整 | P0 | [x] Done |
| TC-CONTRACT-007 | P0 server-error 修复验证 | P0 不应出现未处理 500 | P0 | [x] Done |
| TC-CONTRACT-008 | 契约通过率验证 | 冲刺 >= 90% | P1 | [x] Blocked |
| TC-CONTRACT-009 | `CONTRACT_TEST_BASELINE_V1.8.md` 完整 | 报告完整 | P0 | [x] Done |

---

## 8. Phase 5: 前端质量验证 (12 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-FE-001 | ESLint 归零 | 0 errors | P0 | [x] Done |
| TC-FE-002 | type-check 验证 | 0 errors | P0 | [x] Done |
| TC-FE-003 | production build | 构建成功 | P0 | [x] Done |
| TC-FE-004 | Vitest 可运行 | 测试命令成功 | P1 | [x] Done |
| TC-FE-005 | 前端 coverage 可生成 | coverage 报告生成 | P1 | [x] Done |
| TC-FE-006 | utils coverage | 核心工具被覆盖 | P1 | [x] Done |
| TC-FE-007 | composables coverage | 状态逻辑被覆盖 | P1 | [x] Done |
| TC-FE-008 | stores coverage | 状态迁移被覆盖 | P1 | [x] Done |
| TC-FE-009 | api request/error handling coverage | 请求错误路径被覆盖 | P1 | [x] Done |
| TC-FE-010 | common/charts components smoke | 组件可挂载和渲染 | P1 | [x] Done |
| TC-FE-011 | key views smoke | 页面基础渲染可用 | P1 | [x] Done |
| TC-FE-012 | 前端核心 coverage 达标 | >= 60% | P1 | [x] Done |

---

## 9. Phase 6: 质量门禁验证 (10 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-GATE-001 | quick gate 命令存在 | 可执行 | P0 | [x] Done |
| TC-GATE-002 | quick gate 后端快速单测 | 失败时阻断 | P0 | [x] Done |
| TC-GATE-003 | quick gate 前端 type/lint/build | 失败时阻断 | P0 | [x] Done |
| TC-GATE-004 | standard gate 命令存在 | 可执行 | P0 | [x] Done |
| TC-GATE-005 | standard gate coverage fail-under | 低于阈值阻断 | P0 | [x] Done |
| TC-GATE-006 | standard gate OpenAPI export | 失败时阻断 | P0 | [x] Done |
| TC-GATE-007 | standard gate 契约 smoke | P0 失败时阻断 | P0 | [x] Done |
| TC-GATE-008 | standard gate 前端 coverage | 低于核心阈值阻断 | P1 | [x] Done |
| TC-GATE-009 | full gate 观察运行 | 结果被记录 | P1 | [x] Done |
| TC-GATE-010 | `QUALITY_GATE_STRATEGY_V1.8.md` 完整 | 策略清晰 | P0 | [x] Done |

---

## 10. Phase 7: 性能与交付验证 (8 项)

| 编号 | 验证项 | 预期结果 | 优先级 | 状态 |
|------|--------|----------|--------|------|
| TC-PERF-001 | bundle/chunk 基线记录 | chunk 信息完整 | P2 | [x] Done |
| TC-PERF-002 | Top 3 大 chunk 分析 | 有分析结论 | P2 | [x] Blocked |
| TC-PERF-003 | 构建时间验证 | 不劣化超过 15% 或说明原因 | P2 | [x] Blocked |
| TC-PERF-004 | Lighthouse baseline 可选运行 | 记录结果或 blocked | P2 | [x] Blocked |
| TC-DELIVERY-001 | 最终后端 coverage 验证 | 总体 >= 60% | P0 | [x] Done |
| TC-DELIVERY-002 | 最终前端质量验证 | type/lint/build 达标 | P0 | [x] Done |
| TC-DELIVERY-003 | 最终契约验证 | 实跑结果记录 | P0 | [x] Done |
| TC-DELIVERY-004 | 最终交付文档完整 | FINAL/DELIVERY/NEXT_STEPS 完成 | P0 | [x] Done |

---

## 11. 验收矩阵

| 需求 | 对应测试 |
|------|----------|
| REQ-P0-001 | TC-BASE-001 ~ TC-BASE-010 |
| REQ-P0-002 | TC-SVC-001 ~ TC-SVC-016 |
| REQ-P0-003 | TC-ML-001 ~ TC-ML-012, TC-TASK-001 |
| REQ-P0-004 | TC-STAB-001 ~ TC-STAB-008 |
| REQ-P0-005 | TC-CONTRACT-001 ~ TC-CONTRACT-009 |
| REQ-P0-006 | TC-FE-001 ~ TC-FE-003 |
| REQ-P0-007 | TC-GATE-001 ~ TC-GATE-010 |
| REQ-P1-001 | TC-FE-004 ~ TC-FE-012 |
| REQ-P1-002 | TC-CONTRACT-008 |
| REQ-P1-003 | TC-BASE-002, TC-BASE-009, TC-DELIVERY-004 |
| REQ-P2-001 | TC-PERF-001 ~ TC-PERF-004 |
| REQ-P2-002 | TC-GATE-009 |

---

## 12. 通过标准

### P0 通过标准

- 所有 P0 测试项完成或有明确 blocked 说明
- 后端整体 coverage >= 60%
- services coverage >= 65%
- ML coverage >= 50%
- tasks coverage >= 40%
- 前端 type-check 0 errors
- 前端 ESLint 0 errors
- 前端 build 成功
- Schemathesis 已实跑并记录
- quick/standard gate 可执行并阻断核心失败

### P1 通过标准

- Schemathesis 通过率 >= 90%
- 前端核心模块 coverage >= 60%
- coverage 报告自动化生成

### P2 通过标准

- 性能基线已记录
- full gate 观察运行或有明确 blocked 说明
