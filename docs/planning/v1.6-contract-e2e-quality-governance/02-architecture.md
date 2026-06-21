# v1.6 稳定性治理与质量闭环收口版 - 架构设计

> **迭代名称**: v1.6-contract-e2e-quality-governance
> **日期**: 2026-04-28
> **状态**: Round 1 Draft (基于 v1.6-final-integrated-tasks.md)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        质量治理全景图                                 │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Phase 7: 技术债收口                        │   │
│  │  Warning清理 | 类型安全 | 经验沉淀 | 文档收口                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Phase 6: 前端体验闭环                      │   │
│  │  大列表加载 | PDF/Excel稳定性 | 图表规范 | 移动端适配           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Phase 5: 质量工具链                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │   │
│  │  │Lighthouse│  │  Sentry  │  │ Codecov  │  │  CI/CD   │   │   │
│  │  │   CI     │  │ 监控     │  │ 覆盖率   │  │ 质量门禁 │   │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Phase 4: 覆盖率基线                        │   │
│  │  后端>=85% | 前端>=80% | 测试分层 | 质量门禁规则               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Phase 2: 契约测试    │    Phase 3: E2E测试                  │   │
│  │  ┌────────────────┐  │  ┌────────────────────────────────┐  │   │
│  │  │ schemathesis   │  │  │ Playwright                     │  │   │
│  │  │ hypothesis     │  │  │  - LoginPage                   │  │   │
│  │  │ OpenAPI Spec   │  │  │  - RiskAssessmentPage          │  │   │
│  │  └────────────────┘  │  │  - MonitoringDashboardPage     │  │   │
│  │                      │  │  - ReportCenterPage            │  │   │
│  │                      │  └────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Phase 1: 稳定性基线                        │   │
│  │  版本治理 | 边界处理 | Fallback分级 | 退化验证 | Warning清理    │   │
│  └─────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                        v1.5 已交付基础                              │
│  验证闭环 | 灰度发布 | 监控告警 | 前端性能 | 回退机制 | 虚拟列表      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase 1: 稳定性治理架构

### 2.1 版本与依赖治理

```
┌─────────────────────────────────────────┐
│         Dependency Governance           │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    │
│  │  Risk Scan  │ -> │  Version    │    │
│  │  (脚本)     │    │  Lock       │    │
│  │             │    │  (固定版本)  │    │
│  └─────────────┘    └──────┬──────┘    │
│                             │           │
│  ┌──────────────────────────▼──────┐   │
│  │      Compatibility Layer        │   │
│  │  - sklearn version adapter      │   │
│  │  - datetime timezone-aware      │   │
│  │  - PyTorch optional import      │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 2.2 Fallback 分级机制

```
┌─────────────────────────────────────────┐
│         Fallback Hierarchy              │
├─────────────────────────────────────────┤
│                                         │
│  Layer 1: Primary Model                 │
│  ├── 成功 -> 返回预测结果                │
│  └── 失败 -> 进入 Layer 2               │
│                                         │
│  Layer 2: Fusion Model                  │
│  ├── 成功 -> 返回融合预测                │
│  └── 失败 -> 进入 Layer 3               │
│                                         │
│  Layer 3: Rule-Based Fallback           │
│  ├── 成功 -> 返回规则评分                │
│  └── 失败 -> 进入 Layer 4               │
│                                         │
│  Layer 4: Heuristic Fallback            │
│  └── 始终可用 -> 返回启发式评分          │
│                                         │
│  [每层统一输出结构化日志]                 │
│                                         │
└─────────────────────────────────────────┘
```

### 2.3 错误语义统一

```python
# 统一错误响应结构
{
  "error": {
    "code": "MODEL_LOAD_FAILED",
    "message": "主模型加载失败，已回退到启发式规则",
    "layer": "L1_PRIMARY_MODEL",
    "fallback_to": "L4_HEURISTIC",
    "timestamp": "2026-04-28T10:00:00+00:00",
    "request_id": "uuid"
  }
}
```

---

## 3. Phase 2: 契约测试架构

### 3.1 组件设计

```
┌─────────────────────────────────────────┐
│         Contract Test Suite             │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    │
│  │ API Contract│    │ Model       │    │
│  │ Tests       │    │ Contract    │    │
│  │             │    │ Tests       │    │
│  │ - auth      │    │             │    │
│  │ - user      │    │ - tabular   │    │
│  │ - model     │    │ - text      │    │
│  │ - monitoring│    │ - physio    │    │
│  │ - canary    │    │ - fusion    │    │
│  │ - validation│    │             │    │
│  │ - reports   │    │             │    │
│  └──────┬──────┘    └──────┬──────┘    │
│         │                  │           │
│  ┌──────▼──────────────────▼──────┐   │
│  │     schemathesis / hypothesis  │   │
│  │     (property-based testing)   │   │
│  └──────────────┬─────────────────┘   │
│                 │                     │
│  ┌──────────────▼─────────────────┐   │
│  │      FastAPI OpenAPI Spec      │   │
│  │      (auto-generated)          │   │
│  └────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 3.2 技术选型

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 契约测试框架 | schemathesis | >=3.0 | OpenAPI 契约测试 |
| 属性测试 | hypothesis | >=6.0 | 生成边界测试数据 |
| OpenAPI 生成 | fastapi | >=0.110 | 自动生成 OpenAPI spec |

### 3.3 测试数据策略

```python
# 使用 hypothesis 生成边界测试数据
from hypothesis import given, strategies as st

@st.composite
def valid_tabular_features(draw):
    return {
        "sleep_hours": draw(st.floats(min_value=0, max_value=24)),
        "heart_rate": draw(st.integers(min_value=40, max_value=200)),
        "steps": draw(st.integers(min_value=0, max_value=50000)),
    }
```

---

## 4. Phase 3: E2E 测试架构

### 4.1 组件设计

```
┌─────────────────────────────────────────┐
│           E2E Test Suite                │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    │
│  │ Page Objects│    │ Test Cases  │    │
│  │             │    │             │    │
│  │ - LoginPage │    │ - auth      │    │
│  │ - HomePage  │    │ - risk      │    │
│  │ - RiskPage  │    │ - monitoring│    │
│  │ - MonitorPg │    │ - canary    │    │
│  │ - ReportPage│    │ - reports   │    │
│  └──────┬──────┘    └──────┬──────┘    │
│         │                  │           │
│  ┌──────▼──────────────────▼──────┐   │
│  │         Playwright             │    │
│  │    (Chromium/Firefox/WebKit)   │    │
│  └──────────────┬─────────────────┘    │
│                 │                      │
│  ┌──────────────▼─────────────────┐    │
│  │      Test Environment          │    │
│  │  - Backend (test database)     │    │
│  │  - Frontend (dev server)       │    │
│  │  - Docker Compose (optional)   │    │
│  └────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 4.2 技术选型

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| E2E 框架 | Playwright | >=1.40 | 端到端测试 |
| 测试运行器 | @playwright/test | >=1.40 | 官方测试运行器 |
| 断言库 | expect (built-in) | - | Playwright 内置断言 |

### 4.3 Page Object Model

```typescript
// tests/e2e/pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/login');
  }

  async login(username: string, password: string) {
    await this.page.fill('[data-testid="username"]', username);
    await this.page.fill('[data-testid="password"]', password);
    await this.page.click('[data-testid="login-button"]');
  }

  async getErrorMessage() {
    return this.page.textContent('[data-testid="error-message"]');
  }
}
```

---

## 5. Phase 4: 覆盖率架构

### 5.1 后端覆盖率

```
┌─────────────────────────────────────────┐
│         Backend Coverage                │
├─────────────────────────────────────────┤
│  pytest --cov=app --cov-report=html     │
│  pytest --cov=app --cov-report=xml      │
├─────────────────────────────────────────┤
│  目标模块:                                │
│  - app/services/* (业务逻辑)              │
│  - app/api/v1/* (API 路由)               │
│  - app/core/* (核心模块)                 │
│  - app/ml/* (机器学习)                   │
│  - app/models/* (数据模型)               │
└─────────────────────────────────────────┘
```

### 5.2 前端覆盖率

```
┌─────────────────────────────────────────┐
│         Frontend Coverage               │
├─────────────────────────────────────────┤
│  vitest --coverage                      │
├─────────────────────────────────────────┤
│  目标模块:                                │
│  - src/components/* (组件)               │
│  - src/composables/* (组合式函数)         │
│  - src/views/* (页面)                    │
│  - src/utils/* (工具函数)                │
│  - src/stores/* (状态管理)               │
└─────────────────────────────────────────┘
```

---

## 6. Phase 5: CI/CD 集成架构

### 6.1 GitHub Actions 流水线

```yaml
# .github/workflows/quality-gate.yml
name: Quality Gate

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  contract-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run database migrations
        run: |
          cd backend
          alembic upgrade head
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb
      - name: Run Contract Tests
        run: |
          cd backend
          pytest tests/contract/ -v
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb

  e2e-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Start backend (test mode)
        run: |
          cd backend
          pip install -r requirements.txt
          uvicorn app.main:app --host 0.0.0.0 --port 8000 &
        env:
          ENV: test
      - name: Start frontend
        run: |
          cd frontend
          npm ci
          npm run dev &
      - name: Wait for services
        run: npx wait-on http://localhost:8000/health http://localhost:5173
      - name: Run E2E Tests
        run: |
          cd frontend
          npx playwright test

  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Backend Coverage
        run: |
          cd backend
          pytest --cov=app --cov-report=xml
      - name: Upload to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: ./backend/coverage.xml
          fail_ci_if_error: false

  lighthouse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Start frontend
        run: |
          cd frontend
          npm ci
          npm run build
          npx serve dist &
      - name: Wait for frontend
        run: npx wait-on http://localhost:3000
      - name: Lighthouse CI
        run: |
          npm install -g @lhci/cli
          lhci autorun
```

### 6.2 质量门禁

| 检查项 | 阈值 | 失败策略 |
|--------|------|---------|
| 契约测试 | 100% 通过 | 阻止合并 |
| E2E 测试 | 100% 通过 | 阻止合并 |
| 后端覆盖率 | >= 85% | 警告 |
| 前端覆盖率 | >= 80% | 警告 |
| Lighthouse | Performance >= 80 | 警告 |

---

## 7. Phase 6: 前端体验闭环架构

### 7.1 大列表加载优化

```
┌─────────────────────────────────────────┐
│         Large List Loading              │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    │
│  │  Skeleton   │ -> │  Virtual    │    │
│  │  Screen     │    │  List       │    │
│  │  (首屏骨架)  │    │  (虚拟滚动)  │    │
│  └─────────────┘    └──────┬──────┘    │
│                             │           │
│  ┌──────────────────────────▼──────┐   │
│  │      Lazy Data Fetching         │   │
│  │  - Pagination                   │   │
│  │  - Infinite Scroll              │   │
│  │  - Data Prefetching             │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 7.2 报告导出稳定性

```
┌─────────────────────────────────────────┐
│         Report Export Flow              │
├─────────────────────────────────────────┤
│  Request -> Validate -> Generate ->     │
│  ┌─────────┐  ┌─────────┐  ┌────────┐ │
│  │ Input   │  │ Field   │  │ Export │ │
│  │ Check   │  │ Consistency│  │ Format │ │
│  │ (空数据) │  │ (缺字段) │  │ (PDF/  │ │
│  │         │  │         │  │ Excel) │ │
│  └─────────┘  └─────────┘  └────────┘ │
│         │          │          │        │
│         ▼          ▼          ▼        │
│  ┌─────────────────────────────────┐   │
│  │      Error Response (统一格式)   │   │
│  │  {                              │   │
│  │    "error": {                   │   │
│  │      "code": "...",             │   │
│  │      "message": "...",          │   │
│  │      "details": {...}           │   │
│  │    }                            │   │
│  │  }                              │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## 8. Phase 7: 技术债收口架构

### 8.1 Warning 治理流程

```
┌─────────────────────────────────────────┐
│         Warning Governance              │
├─────────────────────────────────────────┤
│  1. Scan: 运行全量测试，收集 warning      │
│  2. Classify: 分类 warning 类型           │
│  3. Prioritize: 按影响排序               │
│  4. Fix: 修复或明确接管                   │
│  5. Verify: 验证 warning 减少             │
│  6. Document: 记录处理经验                │
└─────────────────────────────────────────┘
```

### 8.2 类型安全提升

| 文件类型 | 当前 any 数量 | 目标 |
|---------|--------------|------|
| 测试文件 | ~50 | <= 20 |
| API 类型 | ~10 | 0 |
| 组件 props | ~15 | <= 5 |

---

## 9. 目录结构

```
backend/
├── tests/
│   ├── contract/              # 契约测试
│   │   ├── test_api_contract.py
│   │   └── test_model_contract.py
│   ├── e2e/                   # E2E 测试 (可选)
│   └── stability/             # 稳定性回归测试
│       ├── test_version_governance.py
│       ├── test_boundary_handling.py
│       └── test_fallback_hierarchy.py
├── .github/
│   └── workflows/
│       ├── contract-test.yml
│       ├── e2e-test.yml
│       ├── coverage.yml
│       └── lighthouse.yml
└── pyproject.toml             # 覆盖率配置

frontend/
├── tests/
│   └── e2e/                   # E2E 测试
│       ├── pages/             # Page Objects
│       ├── specs/             # 测试用例
│       └── fixtures/          # 测试数据
├── .github/
│   └── workflows/
│       └── quality-gate.yml
├── playwright.config.ts       # Playwright 配置
└── lighthouserc.js            # Lighthouse CI 配置
```

---

> **下一步**: 进入 Round 1 Step 2 (Critique) 深度自查
