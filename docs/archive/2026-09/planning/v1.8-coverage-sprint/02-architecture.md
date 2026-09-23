# v1.8 架构文档：覆盖率冲刺与质量门禁落地

> **迭代名称**: v1.8-coverage-sprint-and-quality-gates  
> **文档类型**: Architecture  
> **版本**: Round 1 Draft  
> **日期**: 2026-04-29  
> **状态**: Draft

---

## 1. 架构目标

v1.8 架构目标是建立一套能够持续支撑覆盖率提升、契约测试实跑、前端质量验证和质量门禁阻断的工程体系。

核心架构原则：

1. **真实基线优先**：所有指标以工具实际输出为准
2. **测试分层执行**：quick/standard/full 分层，避免慢测试阻塞主路径
3. **覆盖率按价值提升**：优先覆盖业务逻辑和高风险模块
4. **外部依赖隔离**：测试不依赖真实第三方服务或长耗时模型
5. **门禁渐进阻断**：quick/standard 阻断，full 观察
6. **文档与状态同步**：每个阶段产出对应报告或状态更新

---

## 2. 总体架构

```text
v1.8 Quality Architecture

                 ┌──────────────────────────┐
                 │      BASELINE_V1.8       │
                 │  coverage / contract /   │
                 │ frontend / bundle state  │
                 └────────────┬─────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
┌─────────▼─────────┐ ┌───────▼────────┐ ┌────────▼─────────┐
│ Backend Coverage  │ │ Contract Tests │ │ Frontend Quality │
│ services/ml/tasks │ │ Schemathesis   │ │ lint/test/build  │
└─────────┬─────────┘ └───────┬────────┘ └────────┬─────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                   ┌──────────▼──────────┐
                   │ Quality Gate Layers │
                   │ quick/standard/full │
                   └─────────────────────┘
```

---

## 3. 后端测试架构

### 3.1 当前结构

当前后端测试已包含多类测试：

- `tests/api/`
- `tests/services/`
- `tests/contract/`
- `tests/integration/`
- `tests/performance/`
- `tests/degradation/`
- 根级 ML/core 测试文件

v1.8 不进行大规模目录重构，避免引入额外风险。优先通过 marker、profile 和新增测试命名规范治理。

### 3.2 推荐分层

```text
Backend Test Profiles

quick:
  - unit services/core
  - fast ml pure functions
  - no external dependency
  - no slow model training

standard:
  - quick
  - coverage threshold
  - api smoke
  - OpenAPI export
  - Schemathesis smoke

full:
  - standard
  - full Schemathesis
  - integration
  - degradation
  - performance
  - slow/requires_ml tests
```

### 3.3 Marker 体系

建议明确以下 markers：

- `unit`: 快速单元测试
- `integration`: 集成测试
- `contract`: 契约测试
- `performance`: 性能测试
- `degradation`: 降级/容错测试
- `slow`: 慢测试
- `requires_ml`: 需要较重 ML 依赖或模型资源
- `requires_external`: 需要外部服务
- `requires_postgres`: 需要真实 Postgres

---

## 4. 覆盖率提升架构

### 4.1 真实 coverage 驱动

v1.8 不按测试数量估算覆盖率，改为以下闭环：

```text
pytest --cov
  -> coverage term-missing/xml/html
  -> low coverage Top N
  -> 按业务价值和风险排序
  -> 补单元测试优先
  -> mock/fake 外部依赖
  -> 重新运行 coverage
  -> 更新阈值和报告
```

### 4.2 覆盖率目标分层

| 层级 | 模块 | 必达目标 | 冲刺目标 |
|------|------|----------|----------|
| 全局 | backend app | >= 60% | >= 70% |
| 服务层 | services core | >= 65% | >= 75% |
| ML 层 | ml core | >= 50% | >= 65% |
| 任务层 | tasks | >= 40% | >= 60% |

### 4.3 services 覆盖架构

服务层测试优先使用：

- mock repository / session
- fake 当前用户
- fake 数据对象
- 固定输入输出断言
- error path 与 permission path 断言

不优先通过 API 测试间接覆盖 service，避免定位困难和测试脆弱。

### 4.4 ML 覆盖架构

ML 测试遵循：

- 小样本数据
- 固定随机种子
- 避免真实大模型训练
- mock 模型加载和文件系统
- 数值断言使用容差
- 慢测试必须 marker 隔离

### 4.5 tasks 覆盖架构

任务测试遵循：

- 任务注册可断言
- 调度逻辑可断言
- 异常路径可断言
- 不依赖真实 broker
- Celery 或 scheduler 外部行为使用 fake/mock

---

## 5. 契约测试架构

### 5.1 OpenAPI schema 管理

v1.8 延续 v1.7 的 COMMON_ERROR_RESPONSES 模式，确保：

- 401/403/422/500 响应结构一致
- ErrorResponse schema 可复用
- schema 可导出并用于契约测试

### 5.2 Schemathesis 分层

```text
Contract Testing

smoke:
  - 核心 API
  - 低样本数
  - quick/standard gate 阻断

full:
  - 全 API
  - 更高样本数
  - full gate 观察
```

### 5.3 失败分类

契约失败必须按以下类型归类：

- schema mismatch
- auth/permission mismatch
- validation mismatch
- server error 500
- flaky/environment issue
- unsupported generated input

---

## 6. 前端质量架构

### 6.1 当前基础

v1.7 已确认：

- TypeScript 0 errors
- build 成功
- ESLint 可运行，但仍有 31 errors
- Vitest 配置文件存在
- Playwright 配置存在

### 6.2 前端测试分层

```text
Frontend Quality Layers

static:
  - type-check
  - lint
  - formatting if needed

unit:
  - utils
  - composables
  - stores
  - api request/error handling

component smoke:
  - common components
  - charts components
  - key views

build/performance:
  - production build
  - bundle/chunk baseline
  - optional Lighthouse
```

### 6.3 Coverage 范围

v1.8 不要求前端整体覆盖率 80%，而要求：

- coverage 工具链可运行
- 核心模块 coverage >= 60%
- 全局 coverage 仅记录基线

核心模块包括：

- `src/utils/*`
- `src/composables/*`
- `src/stores/*`
- `src/api/request.ts`
- `src/api/*`
- `src/components/common/*`
- `src/components/charts/*`

---

## 7. 质量门禁架构

### 7.1 门禁分层

| Gate | 内容 | 策略 |
|------|------|------|
| Quick Gate | 后端快速单测、前端 type-check、lint、build | 强制阻断 |
| Standard Gate | backend coverage、OpenAPI export、契约 smoke、前端 coverage | 强制阻断 |
| Full Gate | 全量 pytest、全量 Schemathesis、Playwright、Lighthouse、慢 ML 测试 | 观察运行 |

### 7.2 推荐执行流

```text
Developer / CI
  -> Quick Gate
      -> fail: 立即修复
      -> pass
  -> Standard Gate
      -> fail: 阻断合并/交付
      -> pass
  -> Full Gate
      -> fail: 记录风险和 issue
      -> pass: 作为交付加分项
```

### 7.3 阈值策略

后端 coverage fail-under 建议按阶段提升：

| 阶段 | fail-under |
|------|------------|
| Phase 0 | 不阻断，仅记录 |
| Phase 2 后 | 50% |
| Phase 3 后 | 55% |
| Phase 6 后 | 60% |

---

## 8. 报告与文档架构

v1.8 核心规划文档：

- `01-requirements.md`
- `02-architecture.md`
- `03-design.md`
- `04-ralph-tasks.md`
- `05-test-plan.md`

实施报告：

- `BASELINE_V1.8.md`
- `COVERAGE_STRATEGY_V1.8.md`
- `CONTRACT_TEST_BASELINE_V1.8.md`
- `FRONTEND_QUALITY_BASELINE_V1.8.md`
- `QUALITY_GATE_STRATEGY_V1.8.md`
- `FINAL_REPORT_V1.8.md`
- `DELIVERY_REPORT.md`
- `NEXT_STEPS.md`

---

## 9. 架构风险

| 风险 | 影响 | 架构缓解 |
|------|------|----------|
| 覆盖率增长慢 | 高 | missing lines 驱动，优先高价值模块 |
| ML 测试拖慢 CI | 高 | marker 隔离，小样本，mock 重依赖 |
| 契约测试不稳定 | 中高 | smoke 阻断，full 观察 |
| 前端 coverage 目标不稳 | 中 | 核心模块指标优先，全局仅记录 |
| 门禁过严影响开发 | 中 | quick/standard/full 渐进阻断 |
| 大规模目录重构带来风险 | 中 | v1.8 不强制重构历史测试目录 |
