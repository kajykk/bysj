# v1.16-coverage-80 架构文档

> **迭代名称**: v1.16-coverage-80
> **上一迭代**: v1.15-launch-readiness
> **目标**: 测试覆盖率提升至 80% 的架构设计
> **创建日期**: 2026-05-01

---

## 1. 测试架构总览

### 1.1 测试金字塔

```
        /\
       /  \     E2E Tests (P1)
      /----\    (Playwright)
     /      \
    /--------\  Integration Tests (P0)
   /          \ (pytest + TestClient)
  /------------\ Unit Tests (P0)
 /              \(pytest + unittest.mock)
/----------------\
```

### 1.2 测试分层

| 层级 | 范围 | 工具 | 目标覆盖率 | 执行时间 |
|---|---|---|---|---|
| 单元测试 | 函数/方法 | pytest, unittest.mock | 80% | < 5 min |
| 集成测试 | API/模块 | pytest, TestClient | 80% | < 10 min |
| E2E 测试 | 用户流程 | Playwright | 核心流程 | < 15 min |

---

## 2. 后端测试架构

### 2.1 单元测试架构

#### 2.1.1 测试目录结构

```
backend/tests/
├── unit/                          # 单元测试
│   ├── __init__.py
│   ├── conftest.py               # 共享 fixtures
│   ├── api/                      # API 层测试
│   │   ├── __init__.py
│   │   ├── test_auth.py
│   │   ├── test_user_risk.py
│   │   ├── test_counselor.py
│   │   └── test_admin.py
│   ├── services/                 # Service 层测试
│   │   ├── __init__.py
│   │   ├── test_auth_service.py
│   │   ├── test_risk_service.py
│   │   └── test_model_service.py
│   ├── repositories/             # Repository 层测试
│   │   ├── __init__.py
│   │   ├── test_user_repo.py
│   │   └── test_assessment_repo.py
│   └── core/                     # 核心模块测试
│       ├── __init__.py
│       ├── test_config.py
│       ├── test_security.py
│       └── test_model_engine.py
├── integration/                   # 集成测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth_flow.py
│   ├── test_risk_flow.py
│   └── test_model_flow.py
├── e2e/                          # E2E 测试
│   └── ... (see frontend)
└── fixtures/                     # 测试数据
    ├── __init__.py
    ├── users.py
    ├── assessments.py
    └── models.py
```

#### 2.1.2 测试基类

```python
# backend/tests/base.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

# 测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class BaseTestCase:
    """测试基类"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self):
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)
    
    @pytest.fixture
    def client(self):
        def override_get_db():
            try:
                db = TestingSessionLocal()
                yield db
            finally:
                db.close()
        
        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        del app.dependency_overrides[get_db]
```

### 2.2 集成测试架构

#### 2.2.1 API 集成测试

```python
# backend/tests/integration/test_auth_flow.py
class TestAuthFlow:
    """认证流程集成测试"""
    
    def test_register_login_access(self, client):
        """测试注册-登录-访问完整流程"""
        # 1. 注册
        response = client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "test123",
            "name": "Test User"
        })
        assert response.status_code == 201
        
        # 2. 登录
        response = client.post("/api/v1/auth/login", data={
            "username": "test@example.com",
            "password": "test123"
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # 3. 访问受保护资源
        response = client.get("/api/v1/user/profile", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
```

### 2.3 测试数据管理

#### 2.3.1 工厂模式

```python
# backend/tests/factories.py
import factory
from app.models.user import User
from app.models.assessment import Assessment

class UserFactory(factory.Factory):
    class Meta:
        model = User
    
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Faker("name")
    role = "user"
    is_active = True

class AssessmentFactory(factory.Factory):
    class Meta:
        model = Assessment
    
    user_id = factory.SubFactory(UserFactory)
    risk_level = "medium"
    score = 75.0
```

---

## 3. 前端测试架构

### 3.1 单元测试架构

#### 3.1.1 测试目录结构

```
frontend/src/__tests__/
├── unit/
│   ├── components/               # 组件测试
│   │   ├── LoginForm.test.ts
│   │   ├── RiskAssessment.test.ts
│   │   └── WarningList.test.ts
│   ├── composables/              # 组合式函数测试
│   │   ├── useAuth.test.ts
│   │   └── useApi.test.ts
│   └── utils/                    # 工具函数测试
│       ├── httpError.test.ts
│       └── validators.test.ts
├── integration/                  # 集成测试
│   ├── api.test.ts
│   └── router.test.ts
└── e2e/                          # E2E 测试
    ├── auth.spec.ts
    ├── risk.spec.ts
    └── admin.spec.ts
```

#### 3.1.2 组件测试示例

```typescript
// frontend/src/__tests__/unit/components/LoginForm.test.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import LoginForm from '@/components/LoginForm.vue'

describe('LoginForm', () => {
  it('should validate email format', async () => {
    const wrapper = mount(LoginForm)
    const emailInput = wrapper.find('input[type="email"]')
    
    await emailInput.setValue('invalid-email')
    await emailInput.trigger('blur')
    
    expect(wrapper.find('.error-message').text()).toContain('Invalid email')
  })
  
  it('should emit submit event with form data', async () => {
    const wrapper = mount(LoginForm)
    
    await wrapper.find('input[type="email"]').setValue('test@example.com')
    await wrapper.find('input[type="password"]').setValue('password123')
    await wrapper.find('form').trigger('submit')
    
    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')[0]).toEqual([{
      email: 'test@example.com',
      password: 'password123'
    }])
  })
})
```

### 3.2 E2E 测试架构

#### 3.2.1 Playwright 配置

```typescript
// frontend/playwright.config.ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './src/__tests__/e2e',
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
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
})
```

---

## 4. CI/CD 集成架构

### 4.1 GitHub Actions 工作流

```yaml
# .github/workflows/v1.16-coverage.yml
name: v1.16 Coverage Check

on:
  push:
    branches: [ main, v1.16-coverage-80 ]
  pull_request:
    branches: [ main ]

jobs:
  backend-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        working-directory: backend
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio factory-boy
      - name: Run unit tests with coverage
        working-directory: backend
        run: pytest tests/unit/ --cov=app --cov-report=xml --cov-report=html
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: backend/coverage.xml
          flags: backend-unit

  backend-integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        working-directory: backend
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      - name: Run integration tests
        working-directory: backend
        run: pytest tests/integration/ --cov=app --cov-report=xml

  frontend-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Run unit tests with coverage
        working-directory: frontend
        run: npm run test:unit -- --coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: frontend/coverage/lcov.info
          flags: frontend-unit

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Install Playwright
        working-directory: frontend
        run: npx playwright install --with-deps
      - name: Run E2E tests
        working-directory: frontend
        run: npx playwright test
```

### 4.2 覆盖率报告集成

| 工具 | 用途 | 配置 |
|---|---|---|
| pytest-cov | 后端覆盖率 | `pytest --cov=app --cov-report=xml` |
| c8 | 前端覆盖率 | `vitest --coverage` |
| Codecov | 覆盖率上传 | GitHub Action |
| GitHub Checks | PR 覆盖率检查 | 自动集成 |

---

## 5. 测试数据策略

### 5.1 数据库策略

| 环境 | 数据库 | 数据策略 |
|---|---|---|
| 单元测试 | SQLite (内存) | 每个测试独立创建/销毁 |
| 集成测试 | SQLite (文件) | 测试套件级别创建/销毁 |
| E2E 测试 | 开发数据库 | 使用种子数据 |

### 5.2 Mock 策略

| 依赖 | Mock 工具 | 使用场景 |
|---|---|---|
| 外部 API | responses / aioresponses | 集成测试 |
| 数据库 | unittest.mock | 单元测试 |
| 邮件服务 | unittest.mock | 单元测试 |
| 文件系统 | pyfakefs | 单元测试 |
| 时间 | freezegun | 单元测试 |

---

## 6. 性能与可维护性

### 6.1 测试性能优化

- **并行执行**: pytest-xdist 并行运行测试
- **数据库事务**: 每个测试后回滚事务
- **Fixture 缓存**: 共享昂贵的 fixture
- **选择性测试**: 只运行变更相关的测试

### 6.2 测试可维护性

- **命名规范**: `test_<module>_<scenario>_<expected_result>`
- **Given-When-Then**: 清晰的测试结构
- **工厂模式**: 统一的测试数据创建
- **Page Object**: E2E 测试的页面对象模式

---

> **文档版本**: v1.0
> **最后更新**: 2026-05-01
