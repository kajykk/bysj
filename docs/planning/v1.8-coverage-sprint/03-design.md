# v1.8 详细设计：覆盖率冲刺与质量门禁落地

> **迭代名称**: v1.8-coverage-sprint-and-quality-gates  
> **文档类型**: Design  
> **版本**: Round 1 Draft  
> **日期**: 2026-04-29  
> **状态**: Draft

---

## 1. 设计目标

本设计文档将 v1.8 需求转化为可执行方案，覆盖以下设计域：

1. 真实基线采集设计
2. 后端覆盖率提升设计
3. pytest 测试分层设计
4. 契约测试运行与修复设计
5. 前端质量与 coverage 设计
6. 质量门禁设计
7. 报告与交付设计

---

## 2. 真实基线采集设计

### 2.1 基线采集内容

v1.8 Phase 0 必须采集以下数据：

| 分类 | 数据 | 输出 |
|------|------|------|
| 后端测试 | pytest collect-only | 测试数量、收集错误 |
| 后端覆盖率 | pytest --cov | 总覆盖率、missing lines、HTML/XML |
| 低覆盖文件 | coverage report | Top 20 low coverage files |
| 契约测试 | Schemathesis smoke/full | 通过率、失败分类 |
| 前端静态检查 | type-check/lint | 错误数量 |
| 前端测试 | vitest / coverage | 测试数量、覆盖率 |
| 前端构建 | build | 构建时间、chunk 信息 |
| 性能 | bundle/chunk | chunk size、gzip/brotli 可选 |

### 2.2 基线文档结构

`BASELINE_V1.8.md` 建议包含：

1. 环境信息
2. 后端测试收集结果
3. 后端 coverage 结果
4. low coverage Top 20
5. 契约测试 baseline
6. 前端 type/lint/test/build baseline
7. bundle/chunk baseline
8. 风险与下一步策略

---

## 3. 后端覆盖率提升设计

### 3.1 覆盖率提升原则

- 以真实 missing lines 为依据
- 优先测试业务逻辑，不追求无意义覆盖
- 优先单元测试，其次 API/集成测试
- 对外部依赖使用 mock/fake/fixture
- 对不可测或无价值路径谨慎使用 `pragma: no cover`，必须说明原因

### 3.2 services 测试模式

推荐模式：

```text
Arrange:
  - 构造 fake db/session/user/input
  - mock 外部服务、时间、文件、网络

Act:
  - 调用 service 函数或类方法

Assert:
  - 返回值
  - 状态变化
  - 异常类型和错误信息
  - mock 调用次数和参数
```

覆盖场景：

- happy path
- validation error
- permission denied
- not found
- conflict / duplicate
- dependency failure
- empty data
- boundary values

### 3.3 services 优先级

| 优先级 | 模块 | 原因 |
|--------|------|------|
| S1 | auth/risk/warning/intervention | 核心业务与权限风险高 |
| S1 | model_predict/validation_engine | 预测和校验核心路径 |
| S2 | user_data/counselor/admin/content | 业务流覆盖面广 |
| S2 | pdf_report/excel_export | 文件导出路径易出错 |
| S3 | experiment_* | ML 实验链路复杂，分阶段覆盖 |

### 3.4 ML 测试模式

ML 测试设计：

- 使用最小可行样本，如 5-20 条数据
- 固定随机种子
- 使用 numpy/pandas 小数据结构
- mock 模型文件加载
- mock GPU/torch 可选依赖
- 对浮点结果使用近似断言
- 训练类长耗时测试标记为 `slow` 或 `requires_ml`

覆盖场景：

- 输入数据正常清洗
- 缺失值处理
- 异常类型处理
- 特征列生成
- 评估指标计算
- drift 检测边界
- fusion 权重组合
- 模型加载失败 fallback

### 3.5 tasks 测试模式

任务测试设计：

- 调度注册测试
- 任务参数序列化测试
- 成功执行路径
- 失败重试路径
- 异常记录路径
- 不连接真实 broker

---

## 4. pytest 分层设计

### 4.1 Marker 定义

建议在 `pytest.ini` 中维护：

- `unit`
- `integration`
- `contract`
- `performance`
- `degradation`
- `slow`
- `requires_ml`
- `requires_external`
- `requires_postgres`

### 4.2 Profile 设计

#### Quick Profile

用途：开发本地快速验证和 PR 第一层门禁。

包含：

- 快速 unit 测试
- 不含 slow、contract、performance、requires_external

#### Standard Profile

用途：主质量门禁。

包含：

- quick profile
- coverage fail-under
- API smoke
- OpenAPI export
- Schemathesis smoke

#### Full Profile

用途：交付前/夜间/手动运行。

包含：

- full pytest
- full Schemathesis
- integration/degradation/performance
- Playwright E2E
- Lighthouse

---

## 5. 契约测试设计

### 5.1 OpenAPI 导出

设计要求：

- schema 导出命令可重复执行
- 导出结果作为契约测试输入
- ErrorResponse/COMMON_ERROR_RESPONSES 保持统一

### 5.2 Schemathesis smoke

smoke 测试用于 standard gate 阻断：

- 限定核心 API
- 限定样本数
- 重点发现 500 和 schema mismatch
- 运行时间可控

### 5.3 Schemathesis full

full 测试用于观察：

- 覆盖全部 OpenAPI endpoints
- 更高样本数
- 允许记录失败但不阻断 v1.8 主路径，除非已进入交付阶段且失败属于 P0 接口

### 5.4 失败处理策略

| 失败类型 | 处理 |
|----------|------|
| schema mismatch | 修 schema 或响应模型 |
| auth mismatch | 修 OpenAPI responses 或测试认证策略 |
| validation mismatch | 修 422 定义或请求校验 |
| server error 500 | 优先修代码 |
| unsupported generated input | 自定义 strategy 或合理 skip |
| flaky | 隔离并记录 |

---

## 6. 前端质量设计

### 6.1 ESLint 归零设计

处理策略：

1. 删除真正未使用变量
2. 对必须保留的参数使用命名约定或局部禁用
3. 避免整文件关闭规则
4. 修复后保持 type-check/build 通过

### 6.2 Vitest coverage 设计

v1.8 目标不是全局 80%，而是：

- coverage 可运行
- 核心模块 >= 60%
- 全局指标记录到 baseline

优先测试：

- utils 纯函数
- composables 状态逻辑
- stores 状态迁移
- api request/error handling
- common components smoke
- chart components smoke

### 6.3 组件 smoke 设计

组件 smoke 测试关注：

- 可以挂载
- 关键 props 渲染
- 空状态/错误状态
- 用户交互触发 emit 或回调
- 不关注视觉像素级断言

### 6.4 页面 smoke 设计

页面 smoke 测试关注：

- 路由页面可挂载
- loading/empty/error 状态可渲染
- mock API 数据可展示
- 关键按钮/操作存在

---

## 7. 质量门禁设计

### 7.1 Quick Gate

阻断条件：

- 后端快速单测失败
- 前端 type-check 失败
- 前端 lint 失败
- 前端 build 失败

### 7.2 Standard Gate

阻断条件：

- 后端 coverage < 60%（Phase 6 后启用）
- services coverage < 65%（若工具支持模块级统计）
- OpenAPI schema 导出失败
- Schemathesis smoke 失败且属于 P0 接口/server-error
- 前端核心 coverage < 60%（Phase 5 后启用）

### 7.3 Full Gate

观察内容：

- full pytest
- full Schemathesis
- Playwright E2E
- Lighthouse
- slow/requires_ml tests

输出：

- 不阻断主路径
- 进入风险清单
- 交付报告必须说明状态

---

## 8. 报告设计

### 8.1 阶段报告

| 阶段 | 报告 |
|------|------|
| Phase 0 | `BASELINE_V1.8.md` |
| Phase 2/3 | `COVERAGE_STRATEGY_V1.8.md` 或 coverage 更新记录 |
| Phase 4 | `CONTRACT_TEST_BASELINE_V1.8.md` |
| Phase 5 | `FRONTEND_QUALITY_BASELINE_V1.8.md` |
| Phase 6 | `QUALITY_GATE_STRATEGY_V1.8.md` |
| Phase 7 | `FINAL_REPORT_V1.8.md`, `DELIVERY_REPORT.md`, `NEXT_STEPS.md` |

### 8.2 最终报告指标

最终报告必须包含：

- 后端总覆盖率
- services/ML/tasks 覆盖率
- pytest 执行状态
- Schemathesis 通过率
- 前端 type/lint/test/build 状态
- 前端 coverage 状态
- 门禁状态
- 性能/chunk 状态
- 未完成风险

---

## 9. 设计取舍

### 9.1 为什么不把 85% 作为 P0

从 32% 到 85% 需要新增覆盖约 4494 行代码，且低覆盖区域包含 ML、服务、后台任务等复杂模块。v1.8 将 60% 作为必达目标，70% 作为冲刺目标，更符合真实工程风险。

### 9.2 为什么 full gate 不强制阻断

full gate 包含全量契约、E2E、Lighthouse 和慢 ML 测试，存在环境和耗时不确定性。v1.8 先观察运行，避免门禁过早阻断主线开发。

### 9.3 为什么前端只要求核心模块 60%

前端全局 coverage 未建立 baseline，直接要求 80% 会重复估算偏差。v1.8 先让 coverage 工具链稳定，并覆盖最有价值的核心模块。
