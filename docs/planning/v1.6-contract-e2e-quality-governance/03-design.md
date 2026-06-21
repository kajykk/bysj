# v1.6 稳定性治理与质量闭环收口版 - 技术方案

> **迭代名称**: v1.6-contract-e2e-quality-governance
> **日期**: 2026-04-28
> **状态**: Round 1 Draft
> **对应需求**: 01-requirements.md
> **对应架构**: 02-architecture.md

---

## 1. 技术方案总览

本方案将 v1.6 的 7 个 Phase 转化为可落地的技术实现路径，明确每个 Phase 的关键技术决策、实现步骤和验证方法。

---

## 2. Phase 1: 稳定性基线收口

### 2.1 sklearn 版本治理方案

**问题**: 模型训练时使用 sklearn 1.3.2，但推理环境可能使用不同版本，导致反序列化 warning 或失败。

**方案**:
```python
# backend/app/core/config.py - 版本检查
import sklearn
from packaging import version

SKLEARN_MIN_VERSION = "1.3.0"
SKLEARN_MAX_VERSION = "1.4.0"

def check_sklearn_compatibility():
    current = version.parse(sklearn.__version__)
    min_v = version.parse(SKLEARN_MIN_VERSION)
    max_v = version.parse(SKLEARN_MAX_VERSION)
    
    if not (min_v <= current <= max_v):
        logger.warning(f"sklearn version {current} outside tested range [{min_v}, {max_v}]")
        # 触发兼容性检查，但不阻止加载
```

**实现步骤**:
1. 扫描所有 `.pkl` / `.joblib` 模型文件，记录训练时版本
2. 在模型加载时添加版本检查
3. 产出风险清单文档

### 2.2 datetime 替换方案

**问题**: `datetime.utcnow()` 在 Python 3.12+ 中被废弃。

**方案**:
```python
# 替换前
from datetime import datetime
timestamp = datetime.utcnow()

# 替换后
from datetime import datetime, timezone
timestamp = datetime.now(timezone.utc)
```

**实现步骤**:
1. 全局搜索 `utcnow()` 和 `utcfromtimestamp()`
2. 批量替换为 timezone-aware 写法
3. 验证所有测试通过

### 2.3 全空特征处理方案

**问题**: sklearn SimpleImputer 对全空列发出 warning。

**方案**:
```python
# 在预处理阶段检测并处理全空列
def handle_all_nan_columns(df):
    all_nan_cols = df.columns[df.isna().all()].tolist()
    if all_nan_cols:
        logger.info(f"Dropping all-NaN columns: {all_nan_cols}")
        df = df.drop(columns=all_nan_cols)
    return df, all_nan_cols
```

### 2.4 Fallback 分级机制

**方案**:
```python
# backend/app/ml/fallback_hierarchy.py
class FallbackHierarchy:
    LAYERS = [
        ("L1_PRIMARY", "主模型", primary_model),
        ("L2_FUSION", "融合模型", fusion_model),
        ("L3_RULE_BASED", "规则回退", rule_based_model),
        ("L4_HEURISTIC", "启发式兜底", heuristic_model),
    ]
    
    def predict_with_fallback(self, features):
        for layer_name, layer_desc, model in self.LAYERS:
            try:
                result = model.predict(features)
                self._log_success(layer_name, layer_desc)
                return result
            except Exception as e:
                self._log_failure(layer_name, layer_desc, e)
                continue
        
        raise FallbackExhaustedError("All fallback layers failed")
    
    def _log_success(self, layer, desc):
        logger.info(f"[FALLBACK] {layer} ({desc}) succeeded")
    
    def _log_failure(self, layer, desc, error):
        logger.warning(f"[FALLBACK] {layer} ({desc}) failed: {error}")
```

---

## 3. Phase 2: 契约测试

### 3.1 schemathesis 集成方案

**目录结构**:
```
backend/tests/contract/
├── __init__.py
├── conftest.py              # 契约测试配置
├── test_api_contract.py     # API 契约测试
└── test_model_contract.py   # 模型契约测试
```

**OpenAPI Spec 生成策略**:
```python
# backend/scripts/export_openapi.py
"""导出 FastAPI OpenAPI spec 供契约测试使用"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

openapi_schema = app.openapi()
output_path = Path("backend/tests/contract/openapi.json")
output_path.write_text(json.dumps(openapi_schema, indent=2, ensure_ascii=False))
print(f"OpenAPI spec exported to {output_path}")
```

> **策略说明**:
> - OpenAPI spec 由 FastAPI 自动生成，通过 `export_openapi.py` 脚本导出
> - 每次 API 路由变更后，必须重新运行导出脚本
> - 导出的 `openapi.json` 纳入版本控制，作为契约测试的基准
> - CI 中在运行契约测试前自动执行导出，确保 spec 与代码同步

**API 契约测试示例**:
```python
# backend/tests/contract/test_api_contract.py
import schemathesis
from hypothesis import settings

schema = schemathesis.from_path("openapi.json")

@schema.parametrize()
@settings(max_examples=50)
def test_api_contract(case):
    """验证所有 API 端点符合 OpenAPI 规范"""
    response = case.call()
    case.validate_response(response)
```

**模型契约测试示例**:
```python
# backend/tests/contract/test_model_contract.py
from hypothesis import given, strategies as st

@st.composite
def tabular_features(draw):
    return {
        "sleep_hours": draw(st.floats(0, 24)),
        "heart_rate": draw(st.integers(40, 200)),
        "steps": draw(st.integers(0, 50000)),
    }

@given(tabular_features())
def test_tabular_model_contract(features):
    """验证表格预测模型输入输出契约"""
    result = model.predict(features)
    assert "risk_score" in result
    assert "risk_level" in result
    assert 0 <= result["risk_score"] <= 100
```

---

## 4. Phase 3: E2E 测试

### 4.1 Playwright 配置方案

**文件**: `frontend/playwright.config.ts`

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
```

### 4.2 Page Object 实现

```typescript
// frontend/tests/e2e/pages/LoginPage.ts
import { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;
  readonly errorMessage: Locator;

  constructor(readonly page: Page) {
    this.usernameInput = page.locator('[data-testid="username"]');
    this.passwordInput = page.locator('[data-testid="password"]');
    this.loginButton = page.locator('[data-testid="login-button"]');
    this.errorMessage = page.locator('[data-testid="error-message"]');
  }

  async goto() {
    await this.page.goto('/login');
  }

  async login(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }

  async getErrorMessage(): Promise<string | null> {
    return this.errorMessage.textContent();
  }
}
```

---

## 5. Phase 4: 覆盖率提升

### 5.1 后端覆盖率配置

**文件**: `backend/pytest.ini`

```ini
[pytest]
testpaths = tests
addopts = 
    --cov=app
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-report=xml:coverage.xml
    --cov-fail-under=85
```

### 5.2 前端覆盖率配置

**文件**: `frontend/vitest.config.ts`

```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
      exclude: [
        'node_modules/',
        'tests/',
        '**/*.d.ts',
      ],
    },
  },
});
```

---

## 6. Phase 5: 质量工具链

### 6.1 GitHub Actions 配置

**文件**: `.github/workflows/quality-gate.yml`

```yaml
name: Quality Gate

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  contract-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: |
          cd backend
          pip install -r requirements.txt
          pytest tests/contract/ -v

  e2e-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: |
          cd frontend
          npm ci
          npx playwright install
          npx playwright test

  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: |
          cd backend
          pip install -r requirements.txt
          pytest --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          files: ./backend/coverage.xml

  lighthouse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: |
          npm install -g @lhci/cli
          lhci autorun
```

### 6.2 Sentry 集成

**后端**:
```python
# backend/app/core/sentry.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

def init_sentry(dsn: str, environment: str):
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )
```

**前端**:
```typescript
// frontend/src/main.ts
import * as Sentry from '@sentry/vue';

Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  integrations: [
    Sentry.browserTracingIntegration(),
    Sentry.replayIntegration(),
  ],
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0.1,
});
```

**Secrets 管理方案**:
```bash
# .env.template (纳入版本控制)
SENTRY_DSN=your-sentry-dsn-here
CODECOV_TOKEN=your-codecov-token-here

# GitHub Actions Secrets (不纳入版本控制)
# Settings -> Secrets and variables -> Actions
# - SENTRY_DSN
# - CODECOV_TOKEN
```

> **安全规范**:
> - 所有外部服务 DSN/Token 通过环境变量注入
> - 提供 `.env.template` 模板文件，不包含真实值
> - CI/CD 中通过 GitHub Secrets 注入敏感信息
> - 禁止在代码中硬编码任何 DSN 或 Token

---

## 7. Phase 6: 前端体验优化

### 7.1 大列表加载优化

**方案**: 结合 v1.5 的 VirtualList，添加数据预取和骨架屏优化。

```vue
<!-- MonitoringDashboard.vue -->
<template>
  <div>
    <SkeletonScreen v-if="loading" :rows="10" />
    <VirtualList
      v-else
      :items="alerts"
      :item-height="50"
      :buffer="5"
    >
      <template #item="{ item }">
        <AlertCard :alert="item" />
      </template>
    </VirtualList>
  </div>
</template>
```

### 7.2 报告导出稳定性

**方案**: 添加导出前校验和错误处理。

```typescript
// frontend/src/services/reportService.ts
async function exportPdf(userId: number, startDate: string, endDate: string) {
  // 前置校验
  if (!userId || !startDate || !endDate) {
    throw new ExportError('MISSING_PARAMS', '缺少必要参数');
  }
  
  try {
    const response = await api.post('/reports/user-risk/pdf', {
      user_id: userId,
      start_date: startDate,
      end_date: endDate,
    });
    
    if (response.data?.error) {
      throw new ExportError(response.data.error.code, response.data.error.message);
    }
    
    return response.data;
  } catch (error) {
    logger.error('[Export PDF]', error);
    throw error;
  }
}
```

---

## 8. Phase 7: 技术债收口

### 8.1 Warning 治理清单

| Warning 类型 | 来源 | 修复方案 | 验证方法 |
|-------------|------|---------|---------|
| sklearn 版本不一致 | 模型加载 | 版本检查 + 兼容性层 | 运行模型加载测试 |
| utcnow() deprecation | datetime | 替换为 timezone-aware | grep + 测试 |
| 全空特征 warning | SimpleImputer | 预处理检测全空列 | 运行预处理测试 |
| PyTorch 兼容性 | 可选依赖 | 惰性导入 + 版本锁定 | 无 PyTorch 环境测试 |

### 8.2 类型安全提升路径

1. **测试文件**: 逐步替换 `any` 为具体类型
2. **API 响应**: 定义完整的响应类型接口
3. **组件 props**: 使用 `PropType` 和泛型约束

---

## 9. 关键决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 契约测试框架 | schemathesis / Dredd | schemathesis | Python 生态，与 FastAPI 集成好 |
| E2E 框架 | Playwright / Cypress / Selenium | Playwright | 多浏览器支持，自动等待，Trace 功能 |
| 覆盖率工具 | pytest-cov / coverage.py | pytest-cov | 与 pytest 集成，配置简单 |
| CI 平台 | GitHub Actions / GitLab CI | GitHub Actions | 项目已使用，生态成熟 |
| 错误监控 | Sentry / Rollbar / Bugsnag | Sentry | 前后端统一，性能监控完善 |

---

## 10. 验证清单

### Phase 1 验证
- [ ] sklearn 版本风险清单产出
- [ ] `grep -r "utcnow()" backend/app/` 无匹配
- [ ] 全量测试 warning 数量 <= 基线 * 0.5
- [ ] fallback 分级测试 100% 通过

### Phase 2 验证
- [ ] `pytest tests/contract/` 100% 通过
- [ ] OpenAPI spec 包含所有路由

### Phase 3 验证
- [ ] `npx playwright test` 100% 通过
- [ ] 核心流程全部覆盖

### Phase 4 验证
- [ ] 后端覆盖率 >= 85%
- [ ] 前端覆盖率 >= 80%

### Phase 5 验证
- [ ] CI 流水线全部绿色
- [ ] Sentry 收到测试异常
- [ ] Codecov 显示覆盖率趋势

### Phase 6 验证
- [ ] Lighthouse Performance >= 80
- [ ] 移动端关键页面可用

### Phase 7 验证
- [ ] Warning 总数减少 50%+
- [ ] 技术债清单和经验文档产出

---

> **下一步**: 进入 Round 1 Step 2 (Critique) 深度自查
