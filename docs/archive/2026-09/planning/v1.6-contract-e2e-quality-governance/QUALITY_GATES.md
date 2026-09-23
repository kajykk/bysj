# 质量门禁规则

## 1. PR 合并前必须满足的测试条件

### 1.1 单元测试 (Unit Tests)
- **条件**: 所有单元测试必须通过
- **命令**: `python -m pytest tests/ -m unit -x`
- **失败处理**: 阻塞合并，必须修复

### 1.2 集成测试 (Integration Tests)
- **条件**: 所有集成测试必须通过
- **命令**: `python -m pytest tests/ -m integration -x`
- **失败处理**: 阻塞合并，必须修复

### 1.3 契约测试 (Contract Tests)
- **条件**: 所有契约测试必须通过
- **命令**: `python -m pytest tests/ -m contract -x`
- **失败处理**: 阻塞合并，必须修复

### 1.4 退化测试 (Degradation Tests)
- **条件**: 所有退化测试必须通过
- **命令**: `python -m pytest tests/ -m degradation -x`
- **失败处理**: 阻塞合并，必须修复

### 1.5 前端单元测试
- **条件**: 所有前端单元测试必须通过
- **命令**: `npm run test:unit`
- **失败处理**: 阻塞合并，必须修复

## 2. 覆盖率不能下降规则

### 2.1 后端覆盖率
- **目标**: >= 85%
- **当前基线**: 待测量
- **规则**:
  - PR 不能降低整体覆盖率
  - 新增代码覆盖率 >= 80%
  - 关键路径覆盖率 >= 90%

### 2.2 前端覆盖率
- **目标**: >= 80%
- **当前基线**: 待测量
- **规则**:
  - PR 不能降低整体覆盖率
  - 新增代码覆盖率 >= 75%
  - 关键组件覆盖率 >= 85%

### 2.3 覆盖率报告
- **工具**: pytest-cov (后端), vitest coverage (前端)
- **输出**: HTML + XML (Codecov)
- **检查**: CI 中自动比较基线

## 3. 契约/E2E 必须通过规则

### 3.1 契约测试
- **频率**: 每次 PR
- **范围**: 所有 API 端点
- **工具**: schemathesis + hypothesis
- **失败处理**: 阻塞合并

### 3.2 E2E 测试
- **频率**: 每次 PR (关键路径)
- **范围**: 核心用户流程
- **工具**: Playwright
- **失败处理**: 阻塞合并

### 3.3 性能测试
- **频率**: 每日
- **范围**: API 延迟、页面加载
- **工具**: pytest-benchmark, Lighthouse
- **失败处理**: 告警，不阻塞合并

## 4. 代码质量规则

### 4.1 Lint
- **后端**: ruff, black
- **前端**: eslint, prettier
- **规则**: 0 errors, warnings 不增加

### 4.2 类型检查
- **后端**: mypy (严格模式)
- **前端**: TypeScript (strict 模式)
- **规则**: 0 errors

### 4.3 安全扫描
- **工具**: bandit (后端), npm audit (前端)
- **规则**: 无高危漏洞

## 5. 文档规则

### 5.1 API 文档
- **工具**: OpenAPI/Swagger
- **规则**: 变更必须同步更新文档

### 5.2 测试文档
- **规则**: 新增测试必须包含测试 ID 和说明

## 6. CI/CD 配置

### 6.1 GitHub Actions Workflow
```yaml
name: Quality Gates

on:
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Unit Tests
        run: python -m pytest tests/ -m unit -x --cov=app --cov-fail-under=85

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Integration Tests
        run: python -m pytest tests/ -m integration -x

  contract-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Contract Tests
        run: python -m pytest tests/ -m contract -x

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Frontend Tests
        run: cd frontend && npm run test:unit

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E Tests
        run: cd frontend && npx playwright test --grep "@critical"
```

### 6.2 合并条件
```yaml
branch_protection:
  required_status_checks:
    - unit-tests
    - integration-tests
    - contract-tests
    - frontend-tests
    - e2e-tests
  required_pull_request_reviews:
    required_approving_review_count: 1
```

## 7. 豁免规则

### 7.1 紧急情况
- **条件**: 生产环境严重 bug 修复
- **流程**:
  1. 创建 hotfix 分支
  2. 最小化变更
  3. 事后补充测试
  4. 记录豁免原因

### 7.2 文档变更
- **条件**: 纯文档变更（无代码改动）
- **豁免**: 可跳过测试

## 8. 监控与告警

### 8.1 覆盖率趋势
- **工具**: Codecov
- **告警**: 覆盖率下降 > 1%

### 8.2 测试稳定性
- **监控**:  flaky 测试检测
- **告警**: 同一测试连续失败 3 次

### 8.3 构建时间
- **阈值**: 总构建时间 < 30 分钟
- **告警**: 构建时间增加 > 20%
