# v2-launch-and-coverage 架构文档

> **迭代名称**: v2-launch-and-coverage
> **上一迭代**: v1.15-launch-readiness
> **目标**: 上线就绪 + 测试覆盖率 80% 的架构设计
> **创建日期**: 2026-05-01

---

## 1. 总体架构

### 1.1 架构目标

**双轨并行**：
1. **上线就绪轨道**: 验证核心功能、部署流程、健康检查
2. **覆盖率提升轨道**: 完善测试体系、达到 80% 覆盖率

### 1.2 架构原则

- **先验证后测试**: 先确保功能可用，再完善测试覆盖
- **CI 优先**: 所有验证必须通过 CI，不依赖本地环境
- **渐进覆盖**: 先 P0 核心功能，再 P1 支撑功能
- **自动化门禁**: CI 自动阻止覆盖率下降的代码合并

---

## 2. 验证架构

### 2.1 上线验证流程

```
代码提交 -> GitHub Actions -> 并行验证
  ├── 前端构建验证
  │     ├── npm ci
  │     ├── npm run build
  │     └── 构建产物检查
  ├── 后端启动验证
  │     ├── pip install
  │     ├── uvicorn 启动
  │     └── /health 检查
  └── 核心 API 验证
        ├── 登录/注册
        ├── 风险评估
        └── 预警查看
```

### 2.2 验证检查点

| 检查点 | 验证方式 | 通过标准 |
|---|---|---|
| 前端构建 | CI 构建步骤 | 0 错误，dist/ 生成 |
| 后端启动 | CI 启动步骤 | 0 错误，端口监听 |
| 健康检查 | HTTP 请求 | 200 + {"status": "ok"} |
| 核心 API | 自动化测试 | 100% 通过 |
| 数据库 | 连接测试 | 读写正常 |
| 模型 | 预测测试 | 返回正确结果 |

---

## 3. 测试架构

### 3.1 测试金字塔

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

### 3.2 测试分层

| 层级 | 范围 | 工具 | 目标覆盖率 | 执行环境 |
|---|---|---|---|---|
| 单元测试 | 函数/方法/组件 | pytest / Vitest | 80% | CI |
| 集成测试 | API/模块交互 | pytest + TestClient | 80% | CI |
| E2E 测试 | 用户流程 | Playwright | 核心流程 | CI |

### 3.3 后端测试架构

#### 3.3.1 测试目录结构

```
backend/tests/
├── conftest.py              # 全局 fixtures
├── base.py                  # 测试基类
├── factories.py             # 数据工厂
├── unit/                    # 单元测试
│   ├── api/
│   │   ├── test_auth.py
│   │   ├── test_user_risk.py
│   │   ├── test_counselor.py
│   │   └── test_admin.py
│   ├── services/
│   │   ├── test_auth_service.py
│   │   ├── test_risk_service.py
│   │   └── test_model_service.py
│   ├── repositories/
│   │   ├── test_user_repo.py
│   │   └── test_assessment_repo.py
│   └── core/
│       ├── test_config.py
│       ├── test_security.py
│       └── test_model_engine.py
├── integration/             # 集成测试
│   ├── test_auth_flow.py
│   ├── test_risk_flow.py
│   ├── test_model_flow.py
│   └── test_errors.py
└── e2e/                     # E2E 测试
    └── ...
```

#### 3.3.2 测试基类

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
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

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
    
    @pytest.fixture
    def auth_client(self, client):
        """已认证的客户端"""
        # 注册并登录
        client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "test123",
            "name": "Test User"
        })
        response = client.post("/api/v1/auth/login", data={
            "username": "test@example.com",
            "password": "test123"
        })
        token = response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        return client
```

### 3.4 前端测试架构

#### 3.4.1 测试目录结构

```
frontend/src/__tests__/
├── setup.ts                 # 测试配置
├── unit/
│   ├── components/
│   │   ├── LoginForm.test.ts
│   │   ├── RiskAssessment.test.ts
│   │   └── WarningList.test.ts
│   ├── composables/
│   │   ├── useAuth.test.ts
│   │   └── useApi.test.ts
│   └── utils/
│       ├── httpError.test.ts
│       └── validators.test.ts
├── integration/
│   ├── api.test.ts
│   └── router.test.ts
└── e2e/
    ├── auth.spec.ts
    ├── risk.spec.ts
    └── admin.spec.ts
```

#### 3.4.2 Vitest 配置

```typescript
// frontend/vitest.config.ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    coverage: {
      provider: 'c8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/__tests__/',
        '*.config.*',
      ],
      thresholds: {
        lines: 80,
        functions: 85,
        branches: 75,
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  }
})
```

---

## 4. CI/CD 架构

### 4.1 GitHub Actions 工作流

```yaml
# .github/workflows/v2-ci.yml
name: v2 CI - Launch & Coverage

on:
  push:
    branches: [ main, v2-launch-and-coverage ]
  pull_request:
    branches: [ main ]

jobs:
  # 1. 前端构建验证
  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Build for production
        working-directory: frontend
        run: npm run build
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist/

  # 2. 后端启动验证
  backend-startup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        working-directory: backend
        run: pip install -r requirements.txt
      - name: Start backend
        working-directory: backend
        run: |
          uvicorn app.main:app --host 0.0.0.0 --port 8000 &
          sleep 10
          curl -f http://localhost:8000/health || exit 1

  # 3. 后端单元测试 + 覆盖率
  backend-unit-tests:
    runs-on: ubuntu-latest
    needs: [backend-startup]
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
        run: |
          pytest tests/unit/ \
            --cov=app \
            --cov-report=xml \
            --cov-report=html \
            --cov-fail-under=80
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: backend/coverage.xml
          flags: backend-unit

  # 4. 后端集成测试 + 覆盖率
  backend-integration-tests:
    runs-on: ubuntu-latest
    needs: [backend-startup]
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
        run: |
          pytest tests/integration/ \
            --cov=app \
            --cov-report=xml \
            --cov-fail-under=80

  # 5. 前端单元测试 + 覆盖率
  frontend-unit-tests:
    runs-on: ubuntu-latest
    needs: [frontend-build]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
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

  # 6. E2E 测试
  e2e-tests:
    runs-on: ubuntu-latest
    needs: [frontend-build, backend-startup]
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

  # 7. 质量门禁总结
  quality-gate:
    runs-on: ubuntu-latest
    needs: [
      frontend-build,
      backend-startup,
      backend-unit-tests,
      backend-integration-tests,
      frontend-unit-tests,
      e2e-tests
    ]
    if: always()
    steps:
      - name: Check all jobs passed
        run: |
          echo "## v2 Quality Gate Summary" >> $GITHUB_STEP_SUMMARY
          echo "- Frontend Build: ${{ needs.frontend-build.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Backend Startup: ${{ needs.backend-startup.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Backend Unit Tests: ${{ needs.backend-unit-tests.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Backend Integration Tests: ${{ needs.backend-integration-tests.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- Frontend Unit Tests: ${{ needs.frontend-unit-tests.result }}" >> $GITHUB_STEP_SUMMARY
          echo "- E2E Tests: ${{ needs.e2e-tests.result }}" >> $GITHUB_STEP_SUMMARY
          
          if [ "${{ needs.frontend-build.result }}" != "success" ] || \
             [ "${{ needs.backend-startup.result }}" != "success" ] || \
             [ "${{ needs.backend-unit-tests.result }}" != "success" ] || \
             [ "${{ needs.backend-integration-tests.result }}" != "success" ] || \
             [ "${{ needs.frontend-unit-tests.result }}" != "success" ]; then
            echo "❌ Quality gate failed" >> $GITHUB_STEP_SUMMARY
            exit 1
          fi
          echo "✅ All quality gates passed" >> $GITHUB_STEP_SUMMARY
```

### 4.2 覆盖率门禁配置

```yaml
# codecov.yml
coverage:
  status:
    project:
      default:
        target: 80%
        threshold: 2%
    patch:
      default:
        target: 80%
        threshold: 2%

comment:
  layout: "reach, diff, flags, files"
  behavior: default
  require_changes: false
```

---

## 5. 部署架构

### 5.1 部署流程

```
开发 -> PR -> CI 验证 -> 合并 -> 自动部署
  │      │       │         │         │
  │      │       │         │         └── Docker 构建
  │      │       │         │             └── 推送镜像
  │      │       │         │                 └── 部署到服务器
  │      │       │         │
  │      │       │         └── 代码合并到 main
  │      │       │
  │      │       └── 所有检查通过
  │      │           ├── 前端构建成功
  │      │           ├── 后端启动成功
  │      │           ├── 单元测试通过 (>= 80%)
  │      │           ├── 集成测试通过 (>= 80%)
  │      │           └── E2E 测试通过
  │      │
  │      └── 代码审查
  │
  └── 本地开发
```

### 5.2 部署检查清单

| 检查项 | 验证方式 | 通过标准 |
|---|---|---|
| 前端构建 | CI | 构建成功 |
| 后端启动 | CI | 启动成功 |
| 健康检查 | CI | /health 返回 ok |
| 单元测试 | CI | 覆盖率 >= 80% |
| 集成测试 | CI | 覆盖率 >= 80% |
| E2E 测试 | CI | 全部通过 |
| 代码审查 | GitHub | 至少 1 人批准 |

---

## 6. 回滚方案

### 6.1 自动回滚触发条件

- 部署后健康检查失败
- 部署后核心 API 测试失败
- 部署后错误率 > 1%

### 6.2 回滚步骤

1. 停止当前服务
2. 切换到上一个稳定版本
3. 验证回滚后服务正常
4. 通知相关人员

---

> **文档版本**: v1.0
> **最后更新**: 2026-05-01
