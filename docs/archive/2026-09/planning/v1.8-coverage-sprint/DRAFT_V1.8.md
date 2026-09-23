# v1.8 迭代草案：覆盖率冲刺与质量门禁落地

> **迭代名称**: v1.8-coverage-sprint-and-quality-gates  
> **迭代定位**: 覆盖率冲刺为主线，质量门禁落地为支撑  
> **基于**: v1.7-backend-contract-coverage-hardening 最终综合报告与系统现状  
> **草案日期**: 2026-04-29  
> **状态**: 📝 修正版草案 (Revised Draft)

---

## 1. 迭代背景

v1.7 已完成测试基础设施、OpenAPI 契约定义、前端 TypeScript 修复、构建验证和基础质量门禁配置，但最终验证暴露出一个核心事实：**后端实际覆盖率仅 32%，与 v1.7 目标 60% 仍有明显差距**。

v1.8 不应重复 v1.7 中“以测试数量估算覆盖率”的问题，而应以真实 coverage missing lines、Schemathesis 实跑结果、前端 coverage baseline 和 CI/质量门禁结果为依据，完成一次可验证、可阻断、可持续的质量提升。

---

## 2. v1.7 遗留问题

| 问题 | v1.7 实际状态 | 影响 | v1.8 处理策略 |
|------|---------------|------|----------------|
| 后端整体覆盖率 | 32% | 高 | P0，提升到 >= 60%，冲刺 >= 70% |
| services 模块覆盖率 | 12%-41% | 高 | P0，核心模块 >= 65%，冲刺 >= 75% |
| ML 模块覆盖率 | 0%-34% | 高 | P0，核心模块 >= 50%，冲刺 >= 65% |
| tasks 模块覆盖率 | 0% | 高 | P0，>= 40%，冲刺 >= 60% |
| pytest 执行稳定性 | 1159 测试可收集 | 高 | P0，主路径可执行且无阻塞失败 |
| 契约测试实际通过率 | 未实测，仅预估 80%+ | 中高 | P0/P1，必须实跑并记录，通过率冲刺 >= 90% |
| 前端 ESLint | 31 errors | 中 | P0，清理到 0 errors |
| 前端单元测试覆盖率 | 未统计 | 中 | P1，建立 coverage baseline，核心模块 >= 60% |
| 大 chunk / 性能 | 部分 chunk > 500kB | 中 | P2，记录基线并优化 Top 3 |
| 质量门禁 | 可执行但未完全阻断 | 高 | P0/P1，quick/standard gate 阻断，full gate 观察 |

---

## 3. 迭代目标

### 3.1 必达目标

| 指标 | v1.7 实际 | v1.8 必达目标 | 优先级 |
|------|----------|---------------|--------|
| 后端整体覆盖率 | 32% | >= 60% | P0 |
| services 核心模块覆盖率 | 12%-41% | >= 65% | P0 |
| ML 核心模块覆盖率 | 0%-34% | >= 50% | P0 |
| tasks 模块覆盖率 | 0% | >= 40% | P0 |
| pytest 主路径 | 1159 可收集 | 可执行且无阻塞失败 | P0 |
| 契约测试 | 未实测 | Schemathesis smoke/full 实跑并记录 | P0 |
| 前端 type-check | 0 errors | 持续 0 errors | P0 |
| 前端 ESLint | 31 errors | 0 errors | P0 |
| 前端 build | 43.14s 成功 | 持续成功 | P0 |
| 前端 coverage | 未统计 | 可生成报告，核心模块 >= 60% | P1 |
| 质量门禁 | 可执行 | quick/standard gate 阻断 | P0/P1 |

### 3.2 冲刺目标

| 指标 | v1.8 冲刺目标 |
|------|---------------|
| 后端整体覆盖率 | >= 70% |
| services 核心模块覆盖率 | >= 75% |
| ML 核心模块覆盖率 | >= 65% |
| tasks 模块覆盖率 | >= 60% |
| 契约测试通过率 | >= 90%-95% |
| 前端核心模块覆盖率 | >= 70% |
| Lighthouse Performance | >= 80 |
| 构建时间 | 不劣化超过 15% |

### 3.3 延后目标

以下目标不作为 v1.8 P0 必达，建议放入 v1.9 或后续质量冲刺：

- 后端整体覆盖率 >= 85%
- 前端整体覆盖率 >= 80%
- full gate 全量强制阻断
- 全量 E2E 稳定阻断

---

## 4. 需求草案

### 4.1 P0 需求

#### REQ-P0-001: 建立 v1.8 真实质量基线

- 运行后端 pytest 收集与 coverage
- 导出 low coverage Top 文件
- 运行 Schemathesis smoke/full baseline
- 运行前端 type-check/lint/test/build
- 运行前端 coverage baseline
- 记录 bundle/chunk 基线
- 产出 `BASELINE_V1.8.md`

#### REQ-P0-002: 后端 services 覆盖率冲刺

目标：services 核心模块覆盖率 >= 65%，冲刺 >= 75%。

重点范围以当前项目真实文件为准，包括但不限于：

- `app/services/auth_service.py`
- `app/services/risk_service.py`
- `app/services/warning_service.py`
- `app/services/intervention_service.py`
- `app/services/user_data_service.py`
- `app/services/model_predict_service.py`
- `app/services/validation_engine.py`
- `app/services/counselor_service.py`
- `app/services/admin_service.py`
- `app/services/content_service.py`
- `app/services/pdf_report_service.py`
- `app/services/excel_export_service.py`
- `app/services/experiment_service.py`
- `app/services/experiment_evaluator.py`
- `app/services/experiment_metrics.py`
- `app/services/experiment_trainer.py`

#### REQ-P0-003: 后端 ML/tasks 覆盖率冲刺

目标：ML 核心模块覆盖率 >= 50%，tasks 模块覆盖率 >= 40%。

重点范围包括：

- `app/ml/data_cleaner.py`
- `app/ml/data_loader.py`
- `app/ml/feature_engineering.py`
- `app/ml/evaluation.py`
- `app/ml/statistical_tests.py`
- `app/ml/model_loader.py`
- `app/ml/drift_detector.py`
- `app/ml/fusion_engine.py`
- `app/ml/trainer.py`
- `app/tasks/scheduler.py`

#### REQ-P0-004: pytest 主路径稳定与测试分层

- 明确 quick/standard/full 三类测试 profile
- 使用 marker 隔离 slow、integration、contract、performance、requires_ml、requires_external 测试
- 默认 quick/standard 测试集必须可阻断

#### REQ-P0-005: 契约测试实跑

- OpenAPI schema 可导出
- Schemathesis smoke/full 可运行
- 契约结果必须记录到基线文档
- 对 schema mismatch、401/403/422/500 响应不一致进行分类修复

#### REQ-P0-006: 前端基础质量归零

- `npm run type-check` 持续 0 errors
- `npm run lint` 从 31 errors 清理到 0 errors
- `npm run build` 持续成功

#### REQ-P0-007: quick/standard 质量门禁落地

- quick gate 必须阻断
- standard gate 必须阻断核心质量指标
- full gate 先观察运行，不作为 v1.8 必须阻断

### 4.2 P1 需求

#### REQ-P1-001: 前端 coverage baseline 与核心模块覆盖

- Vitest coverage 可生成
- 核心 utils/composables/stores/api request 覆盖率 >= 60%
- 组件 smoke 测试补充
- 页面 smoke 测试补充

#### REQ-P1-002: 契约测试通过率提升

- Schemathesis 通过率 >= 90%
- 冲刺 >= 95%
- 合理配置自定义策略或 skip 规则

#### REQ-P1-003: coverage 报告自动化

- 后端 coverage XML/HTML 稳定生成
- 前端 coverage JSON/HTML 稳定生成
- 汇总到 v1.8 最终质量报告

### 4.3 P2 需求

#### REQ-P2-001: 性能与 bundle 基线

- 记录 chunk/gzip/brotli 基线
- 优化 Top 3 大 chunk
- 可选 Lighthouse baseline，Performance 冲刺 >= 80

#### REQ-P2-002: E2E 环境稳定化

- 明确后端启动策略、mock API 策略或 docker compose 策略
- Playwright full gate 观察运行

#### REQ-P2-003: 低优先级技术债清理

- Sass Legacy API warning
- 循环 chunk warning
- 非关键慢测试优化

---

## 5. 阶段规划

| Phase | 名称 | 目标 | 优先级 |
|-------|------|------|--------|
| Phase 0 | 真实基线确认 | 建立 v1.8 可验证起点 | P0 |
| Phase 1 | 测试集稳定与分层 | quick/standard/full profile 成型 | P0 |
| Phase 2 | services 覆盖率冲刺 | services >= 65% | P0 |
| Phase 3 | ML/tasks 覆盖率冲刺 | ML >= 50%，tasks >= 40% | P0 |
| Phase 4 | 契约测试实跑与修复 | Schemathesis 实跑并冲刺 >= 90% | P0/P1 |
| Phase 5 | 前端质量基线 | ESLint 0 errors，核心 coverage >= 60% | P0/P1 |
| Phase 6 | 质量门禁落地 | quick/standard 阻断，full 观察 | P0/P1 |
| Phase 7 | 性能与交付 | 性能基线、最终报告、交付文档 | P2 |

---

## 6. 质量门禁策略

| 门禁 | 内容 | v1.8 策略 |
|------|------|-----------|
| Quick Gate | 后端快速单测、前端 type-check、lint、build | 强制阻断 |
| Standard Gate | 后端 coverage、services coverage、OpenAPI export、契约 smoke、前端 coverage | 强制阻断 |
| Full Gate | 全量 pytest、全量 Schemathesis、Playwright E2E、Lighthouse、慢 ML 测试 | 观察运行 |

---

## 7. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 覆盖率目标再次估算偏差 | 高 | Phase 0 使用真实 coverage missing lines 驱动 |
| ML 测试耗时或依赖重 | 高 | 小样本、固定随机种子、mock 模型、slow marker |
| 外部依赖难以隔离 | 中高 | fake/mock/fixture 优先，不依赖真实外部服务 |
| 契约测试出现大量失败 | 中高 | 先 smoke 后 full，先修 P0 接口 |
| 前端全局 coverage 目标过高 | 中 | v1.8 只要求核心模块 >= 60%，全局仅记录 |
| 质量门禁过早阻断开发 | 中 | quick/standard/full 分层推进 |
| 文档状态与实际不一致 | 中 | 每个 Phase 结束更新状态和报告 |

---

## 8. 任务规模估算

| 阶段 | 任务数估计 |
|------|-----------|
| Phase 0: 真实基线确认 | 8-10 |
| Phase 1: 测试集稳定与分层 | 6-8 |
| Phase 2: services 覆盖率冲刺 | 12-16 |
| Phase 3: ML/tasks 覆盖率冲刺 | 10-12 |
| Phase 4: 契约测试实跑与修复 | 6-8 |
| Phase 5: 前端质量基线 | 8-10 |
| Phase 6: 质量门禁落地 | 6-8 |
| Phase 7: 性能与交付 | 5-7 |
| **总计** | **约 60 个任务** |

预计周期：**5-6 周**。

---

## 9. 验收标准

### 9.1 P0 必须达成

- [ ] v1.8 真实基线文档完成
- [ ] pytest 主路径可执行且无阻塞失败
- [ ] 后端整体覆盖率 >= 60%
- [ ] services 核心模块覆盖率 >= 65%
- [ ] ML 核心模块覆盖率 >= 50%
- [ ] tasks 模块覆盖率 >= 40%
- [ ] Schemathesis smoke/full 实跑并记录
- [ ] 前端 type-check 0 errors
- [ ] 前端 ESLint 0 errors
- [ ] 前端 build 成功
- [ ] quick gate 阻断
- [ ] standard gate 阻断核心指标

### 9.2 P1 应该达成

- [ ] Schemathesis 通过率 >= 90%
- [ ] 前端核心模块 coverage >= 60%
- [ ] coverage 报告自动化生成
- [ ] 组件/页面 smoke 测试补充

### 9.3 P2 可选达成

- [ ] Lighthouse Performance >= 80
- [ ] Top 3 大 chunk 优化完成
- [ ] full gate 观察运行
- [ ] E2E 环境稳定化方案完成

---

## 10. 正式 Planning 输出

审核通过后，v1.8 应生成并锁定以下核心文档：

1. `01-requirements.md`
2. `02-architecture.md`
3. `03-design.md`
4. `04-ralph-tasks.md`
5. `05-test-plan.md`

并在实施过程中逐步产出：

- `BASELINE_V1.8.md`
- `COVERAGE_STRATEGY_V1.8.md`
- `CONTRACT_TEST_BASELINE_V1.8.md`
- `FRONTEND_QUALITY_BASELINE_V1.8.md`
- `QUALITY_GATE_STRATEGY_V1.8.md`
- `FINAL_REPORT_V1.8.md`
- `DELIVERY_REPORT.md`
- `NEXT_STEPS.md`
