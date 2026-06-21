# v1.8 需求文档：覆盖率冲刺与质量门禁落地

> **迭代名称**: v1.8-coverage-sprint-and-quality-gates  
> **文档类型**: Requirements  
> **版本**: Round 1 Draft  
> **日期**: 2026-04-29  
> **状态**: Draft

---

## 1. 迭代定位

v1.8 是一次 **覆盖率冲刺与质量门禁落地迭代**。本迭代延续 v1.7 的质量硬化成果，优先解决后端真实覆盖率仅 32% 的关键缺口，同时将测试、契约、前端规范和构建能力升级为可持续阻断的分层质量门禁。

v1.8 不以新增业务功能为主，而以以下能力为核心交付：

1. 真实质量基线可度量
2. 后端核心模块覆盖率显著提升
3. pytest 主路径稳定
4. 契约测试实际运行并记录
5. 前端 lint/type/build/test 质量链路稳定
6. quick/standard/full 质量门禁分层落地

---

## 2. 背景与问题

### 2.1 v1.7 已完成成果

- pytest 可收集 1159 个测试
- 前端 TypeScript 0 错误
- 前端生产构建成功，构建时间 43.14s
- ESLint/Prettier 已配置并可运行
- OpenAPI 401/403 等错误响应定义已补齐
- COMMON_ERROR_RESPONSES 模式已建立
- 分阶段 coverage 阈值策略已记录

### 2.2 v1.7 遗留问题

| 问题 | 当前状态 | 影响 |
|------|----------|------|
| 后端整体覆盖率 | 32% | 高 |
| services 模块覆盖率 | 12%-41% | 高 |
| ML 模块覆盖率 | 0%-34% | 高 |
| tasks 模块覆盖率 | 0% | 高 |
| 契约测试通过率 | 未实测 | 中高 |
| 前端 ESLint | 31 errors | 中 |
| 前端 coverage | 未统计 | 中 |
| 质量门禁 | 可执行但未完全阻断 | 高 |
| chunk 体积 | 部分 > 500kB | 中 |

---

## 3. 成功标准

### 3.1 P0 必须达成

| 编号 | 指标 | v1.7 实际 | v1.8 必达 |
|------|------|-----------|-----------|
| KPI-P0-001 | 后端整体覆盖率 | 32% | >= 60% |
| KPI-P0-002 | services 核心覆盖率 | 12%-41% | >= 65% |
| KPI-P0-003 | ML 核心覆盖率 | 0%-34% | >= 50% |
| KPI-P0-004 | tasks 覆盖率 | 0% | >= 40% |
| KPI-P0-005 | pytest 主路径 | 1159 可收集 | 可执行且无阻塞失败 |
| KPI-P0-006 | 契约测试 | 未实测 | smoke/full 实跑并记录 |
| KPI-P0-007 | 前端 type-check | 0 errors | 持续 0 errors |
| KPI-P0-008 | 前端 ESLint | 31 errors | 0 errors |
| KPI-P0-009 | 前端 build | 成功 | 持续成功 |
| KPI-P0-010 | quick gate | 可执行 | 强制阻断 |
| KPI-P0-011 | standard gate | 未完全阻断 | 核心指标阻断 |

### 3.2 P1 应该达成

| 编号 | 指标 | 目标 |
|------|------|------|
| KPI-P1-001 | Schemathesis 通过率 | >= 90% |
| KPI-P1-002 | 前端核心模块 coverage | >= 60% |
| KPI-P1-003 | coverage 报告 | 后端/前端可自动生成 |
| KPI-P1-004 | 前端组件/页面 smoke | 核心路径有测试覆盖 |

### 3.3 P2 可选达成

| 编号 | 指标 | 目标 |
|------|------|------|
| KPI-P2-001 | 后端整体覆盖率冲刺 | >= 70% |
| KPI-P2-002 | services 覆盖率冲刺 | >= 75% |
| KPI-P2-003 | ML 覆盖率冲刺 | >= 65% |
| KPI-P2-004 | tasks 覆盖率冲刺 | >= 60% |
| KPI-P2-005 | Lighthouse Performance | >= 80 |
| KPI-P2-006 | full gate | 观察运行 |

---

## 4. P0 需求

### REQ-P0-001: v1.8 真实质量基线

**描述**: 在迭代开始阶段建立可复现的真实基线，避免再次依赖估算指标。

**验收标准**:

- 后端 pytest collect-only 结果已记录
- 后端 coverage 结果已记录
- 低覆盖文件 Top 20 已记录
- Schemathesis smoke/full baseline 已记录
- 前端 type-check/lint/test/build 结果已记录
- 前端 coverage baseline 已记录
- bundle/chunk 基线已记录
- `BASELINE_V1.8.md` 已产出

### REQ-P0-002: 后端 services 覆盖率提升

**描述**: 以业务价值和 missing lines 为优先级，补齐 services 层核心逻辑测试。

**目标**:

- services 核心模块覆盖率 >= 65%
- 冲刺 >= 75%

**范围**:

- `auth_service.py`
- `risk_service.py`
- `warning_service.py`
- `intervention_service.py`
- `user_data_service.py`
- `model_predict_service.py`
- `validation_engine.py`
- `counselor_service.py`
- `admin_service.py`
- `content_service.py`
- `pdf_report_service.py`
- `excel_export_service.py`
- `experiment_service.py`
- `experiment_evaluator.py`
- `experiment_metrics.py`
- `experiment_trainer.py`

**验收标准**:

- 覆盖 happy path、error path、boundary path
- 外部依赖使用 mock/fake/fixture 隔离
- 不依赖真实第三方服务
- coverage 报告证明目标达成

### REQ-P0-003: 后端 ML/tasks 覆盖率提升

**描述**: 为 ML 与后台任务核心模块补充快速、稳定、可复现的测试。

**目标**:

- ML 核心模块覆盖率 >= 50%
- tasks 模块覆盖率 >= 40%

**范围**:

- `data_cleaner.py`
- `data_loader.py`
- `feature_engineering.py`
- `evaluation.py`
- `statistical_tests.py`
- `model_loader.py`
- `drift_detector.py`
- `fusion_engine.py`
- `trainer.py`
- `scheduler.py`

**验收标准**:

- 使用小样本数据
- 固定随机种子
- mock 重模型、外部文件和长耗时流程
- 慢测试必须使用 marker 隔离

### REQ-P0-004: pytest 主路径稳定与测试分层

**描述**: 建立 quick/standard/full 测试 profile，确保默认门禁测试稳定。

**验收标准**:

- `unit`、`integration`、`contract`、`performance`、`degradation`、`slow`、`requires_ml`、`requires_external` marker 明确
- quick profile 可在本地和 CI 快速执行
- standard profile 包含 coverage 与契约 smoke
- full profile 包含慢测试、全量契约、E2E、性能测试
- 主路径无收集阻塞和环境阻塞

### REQ-P0-005: 契约测试实际运行

**描述**: 将 v1.7 的契约测试通过率从预估转为实测。

**验收标准**:

- OpenAPI schema 可导出
- Schemathesis smoke 可运行
- Schemathesis full 可运行或明确记录 blocked 原因
- 失败项按 schema/auth/validation/server-error 分类
- `CONTRACT_TEST_BASELINE_V1.8.md` 已产出

### REQ-P0-006: 前端基础质量归零

**描述**: 消除 v1.7 遗留 ESLint 错误，保持 type-check/build 稳定。

**验收标准**:

- type-check 0 errors
- ESLint 0 errors
- build 成功
- 关键修复不通过注释规避有效代码

### REQ-P0-007: quick/standard 质量门禁落地

**描述**: 将 v1.7 的可执行门禁升级为 v1.8 的分层阻断门禁。

**验收标准**:

- quick gate 阻断 type/lint/build/快速单测失败
- standard gate 阻断 coverage/OpenAPI/契约 smoke 失败
- full gate 观察运行，记录但不强制阻断
- `QUALITY_GATE_STRATEGY_V1.8.md` 已产出

---

## 5. P1 需求

### REQ-P1-001: 前端 coverage baseline 与核心模块覆盖

**目标**:

- Vitest coverage 可生成
- 核心模块 coverage >= 60%

**范围**:

- `src/utils/*`
- `src/composables/*`
- `src/stores/*`
- `src/api/request.ts`
- `src/api/*`
- `src/components/common/*`
- `src/components/charts/*`

### REQ-P1-002: 契约测试通过率提升

**目标**:

- Schemathesis 通过率 >= 90%
- 冲刺 >= 95%

### REQ-P1-003: coverage 报告自动化

**目标**:

- 后端 coverage XML/HTML 可生成
- 前端 coverage JSON/HTML 可生成
- 最终报告汇总后端与前端质量指标

---

## 6. P2 需求

### REQ-P2-001: 性能与 bundle 基线

- 记录 chunk/gzip/brotli 基线
- 优化 Top 3 大 chunk
- 可选 Lighthouse baseline

### REQ-P2-002: E2E 环境稳定化

- 明确后端服务启动策略
- 明确 mock API 或 docker compose 策略
- Playwright full gate 观察运行

### REQ-P2-003: 低优先级技术债清理

- Sass Legacy API warning
- 循环 chunk warning
- 非关键慢测试优化

---

## 7. 非目标

v1.8 不承诺以下目标作为 P0 必达：

- 后端整体覆盖率 >= 85%
- 前端整体覆盖率 >= 80%
- full gate 全量强制阻断
- 全量 E2E 稳定阻断
- 大规模业务功能新增

---

## 8. 约束

- 所有覆盖率指标必须基于真实 coverage 输出
- 不允许用无意义测试或过度 `pragma: no cover` 伪造覆盖率
- ML 测试必须控制耗时和随机性
- 外部依赖必须使用 mock/fake/fixture 隔离
- 文档状态必须与实际执行结果同步
