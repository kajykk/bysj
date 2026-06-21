# v1.7 迭代技术设计

> **迭代名称**: v1.7-backend-contract-coverage-hardening
> **上一迭代**: v1.6-contract-e2e-quality-governance
> **日期**: 2026-04-29

---

## 一、测试设计

### 1.1 单元测试设计模式

#### 模式 1: Arrange-Act-Assert (AAA)

```python
def test_user_login_success(client, db):
    # Arrange
    user_data = {"email": "test@example.com", "password": "password123"}
    create_user(db, **user_data)
    
    # Act
    response = client.post("/api/v1/auth/login", data=user_data)
    
    # Assert
    assert response.status_code == 200
    assert "access_token" in response.json()
```

#### 模式 2: Given-When-Then (GWT)

```python
def test_prediction_with_invalid_data_returns_error():
    # Given: 无效的输入数据
    invalid_data = {"sleep_hours": -1, "exercise_minutes": 9999}
    
    # When: 调用预测接口
    response = client.post("/api/v1/predict/structured", json=invalid_data)
    
    # Then: 返回验证错误
    assert response.status_code == 422
    assert "detail" in response.json()
```

#### 模式 3: Parametrized Tests

```python
import pytest

@pytest.mark.parametrize("input_data,expected_status", [
    ({"sleep_hours": 7}, 200),
    ({"sleep_hours": -1}, 422),
    ({}, 422),
    ({"sleep_hours": 25}, 422),
])
def test_prediction_validation(input_data, expected_status, client):
    response = client.post("/api/v1/predict/structured", json=input_data)
    assert response.status_code == expected_status
```

### 1.2 Mock 设计

#### 数据库 Mock

```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base

@pytest.fixture(scope="function")
def db():
    # 创建内存数据库
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
```

#### 模型 Mock

```python
# conftest.py
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_model():
    model = Mock()
    model.predict.return_value = {"risk_score": 0.75, "risk_level": "high"}
    return model

@pytest.fixture
def mock_model_manager(mock_model):
    with patch("app.ml.model_manager.ModelManager") as manager:
        manager.return_value.load_model.return_value = mock_model
        yield manager
```

#### Redis Mock

```python
# conftest.py
import pytest
from fakeredis import FakeRedis

@pytest.fixture
def mock_redis():
    redis = FakeRedis()
    yield redis
    redis.flushall()
```

### 1.3 测试数据工厂

> **注意**: `factory_boy` 当前未安装，v1.7 使用简单 fixture 工厂替代。

```python
# tests/conftest.py 或测试文件内
import pytest
from app.models.user import User

@pytest.fixture
def user_factory(db):
    def _create(email="test@example.com", username="testuser", is_active=True, is_admin=False):
        user = User(email=email, username=username, is_active=is_active, is_admin=is_admin)
        db.add(user)
        db.commit()
        return user
    return _create

@pytest.fixture
def admin_user(user_factory):
    return user_factory(email="admin@example.com", username="admin", is_admin=True)
```

### 1.4 测试设计原则

1. 使用 Arrange-Act-Assert 模式组织测试
2. 使用 parametrized tests 覆盖边界条件
3. 避免依赖真实模型文件和真实外部服务
4. 数据库测试使用 fixture 隔离
5. 预测相关测试重点覆盖 fallback 行为
6. **禁止**为单纯提高覆盖率编写无断言测试

---

## 二、OpenAPI 与错误响应设计

### 2.1 统一错误响应结构

建议统一错误响应包含以下字段：

| 字段 | 类型 | 说明 | 现状 |
|------|------|------|------|
| code | string | 错误码 | ✅ 已存在 |
| message | string | 错误信息 | ✅ 已存在 |
| status_code | integer | HTTP 状态码 | ✅ 已存在（现状） |
| layer | string/null | api/service/model | ✅ 已存在 |
| fallback_to | string/null | L1/L2/L3/L4 或 null | ✅ 已存在 |
| timestamp | string | UTC ISO 时间 | ✅ 已存在 |
| request_id | string | 请求追踪 ID | ✅ 已存在 |
| details | object | 详细错误信息 | ✅ 已存在（现状） |

**现状结构**（与 `app/core/openapi_responses.py` 一致）：

```json
{
  "error": {
    "code": "AUTH_001",
    "message": "认证失败",
    "status_code": 401,
    "layer": "api",
    "fallback_to": null,
    "timestamp": "2026-04-29T12:00:00Z",
    "request_id": "req-123456",
    "details": {}
  }
}
```

> **注意**: 现状包含 `status_code` 和 `details` 字段，规划文档需与此保持一致。

### 2.2 响应模型

建议定义：

1. `ErrorResponse`
2. `UnauthorizedResponse`
3. `ForbiddenResponse`
4. `ValidationErrorResponse`
5. `NotFoundResponse`
6. `InternalErrorResponse`

### 2.3 错误处理中间件

```python
# app/middleware/error_handler.py
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uuid
from datetime import datetime, timezone

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            request_id = str(uuid.uuid4())
            
            error_response = {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "layer": "api",
                    "fallback_to": "L4",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request_id
                }
            }
            
            return JSONResponse(
                status_code=500,
                content=error_response
            )
```

### 2.4 responses 补齐范围

| 接口类型 | 必须声明状态码 |
|---|---|
| 登录/认证接口 | 400、401、422、500 |
| 当前用户接口 | 401、403、422、500 |
| 管理端接口 | 401、403、404、422、500 |
| 预测接口 | 400、401、422、500 |
| 报告接口 | 400、401、403、404、422、500 |
| 文件/导出接口 | 400、401、403、404、500 |

---

## 三、Schemathesis 契约测试修复设计

v1.7 对 v1.6 的 70 个契约失败项进行分类治理。

### 3.1 失败分类

| 分类 | 处理方式 |
|------|---------|
| 401/403 未声明 | 补齐 FastAPI responses |
| 422 参数约束不完整 | 补充 Pydantic Field 约束 |
| 返回结构不一致 | 统一 response_model 或错误模型 |
| 状态码不一致 | 对齐实现与文档 |
| 真实 API 缺陷 | 修复实现或记录技术债 |
| 测试配置问题 | 调整 Schemathesis 配置 |

### 3.2 修复流程

1. 导出现有 OpenAPI schema
2. 执行 Schemathesis
3. 生成失败清单
4. 按类型分类
5. **优先修复 401/403**
6. 修复 422 与错误响应结构
7. 重新导出 schema
8. 重新运行契约测试
9. 输出 `CONTRACT_TEST_REPORT_V1.7.md`

---

## 四、前端 ESLint / Prettier 设计

### 4.1 ESLint 策略

首轮规则以**可运行**为主：

**启用：**
1. Vue 3 推荐规则
2. TypeScript 推荐规则
3. Composition API 基础规则
4. no-unused-vars
5. import/order
6. 测试文件适度放宽

**暂不强制：**
1. 全量禁止 any (设为 warn)
2. 函数复杂度强限制
3. 一次性修复所有 warning
4. 一次性格式化全项目

### 4.2 Prettier 策略

统一：
1. 缩进
2. 行宽
3. 引号风格
4. 尾逗号
5. 分号策略
6. 换行风格

忽略：
1. `dist`
2. `node_modules`
3. coverage 产物
4. 自动生成文件
5. 大型静态资源

### 4.3 脚本配置

```json
// package.json
{
  "scripts": {
    "lint": "eslint . --ext .vue,.ts,.tsx",
    "lint:fix": "eslint . --ext .vue,.ts,.tsx --fix",
    "format": "prettier --write \"src/**/*.{vue,ts,tsx,js,json}\"",
    "format:check": "prettier --check \"src/**/*.{vue,ts,tsx,js,json}\""
  }
}
```

---

## 五、前端 Chunk 优化设计

### 5.1 先分析再优化

先产出：

1. top 10 最大 chunk
2. top 10 最大依赖
3. 首屏依赖清单
4. 可懒加载页面清单
5. 可独立拆包模块清单

### 5.2 优化优先级

| 优先级 | 优化对象 | 策略 |
|--------|---------|------|
| P1 | 图表页面 | 路由懒加载、组件异步加载 |
| P1 | Dashboard 图表组件 | defineAsyncComponent |
| P1 | PDF/Excel 导出 | 非首屏动态 import |
| P2 | vendor chunk | manualChunks 细分 |
| P2 | Sass warning | 溯源并升级或记录 |

### 5.3 验证要求

每次优化后必须验证：

1. `npm run type-check`
2. `npm run build`
3. 核心页面 E2E smoke
4. bundle 体积变化
5. 构建 warning 变化

---

## 六、覆盖率设计

### 6.1 覆盖率配置

```ini
# backend/pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --strict-markers
    --cov=app
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-report=xml:coverage.xml
    --no-cov-on-fail

# 分阶段启用 fail-under:
# Week 1: 不设置（或 --cov-fail-under=35）
# Week 2: --cov-fail-under=50
# Week 3: --cov-fail-under=55
# Week 4: --cov-fail-under=60
```

```ini
# backend/.coveragerc
[run]
source = app
omit = 
    */tests/*
    */migrations/*
    */scripts/*
    app/main.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

### 6.2 覆盖率目标分解

| 模块 | 当前 | v1.7 目标 | 策略 |
|------|------|----------|------|
| auth | ~20% | >= 75% | 补充所有端点测试 |
| user | ~20% | >= 75% | 补充所有端点测试 |
| prediction/model | ~20% | >= 75% | mock 依赖，测试业务逻辑 |
| services | 0% | >= 65% | mock 依赖，测试业务逻辑 |
| core | 0% | >= 60% | mock 外部依赖 |
| ML | 0% | >= 60% | 使用小型数据集 |
| utils | 0% | >= 80% | 直接测试 |
| **整体** | **36.29%** | **>= 60%** | **分阶段达成** |

### 6.3 失败测试隔离策略

v1.6 遗留约 30 个失败测试，Week 1 必须处理：

1. **分类**: 运行全部测试，收集失败清单
2. **主路径优先**: 修复影响核心流程的失败项
3. **边缘隔离**: 对非阻塞失败使用 `pytest.mark.xfail(reason="...")`
4. **临时忽略**: 对已知环境问题使用 `pytest.mark.skip(reason="...")`
5. **文档化**: 每个 xfail/skip 必须有原因说明

```python
# 示例
@pytest.mark.xfail(reason="DB 连接超时，待修复基础设施")
def test_external_api_integration():
    ...
```

---

## 七、CI/CD 设计

### 7.1 工作流设计

```yaml
# .github/workflows/v1.7-ci.yml
name: v1.7 CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run unit tests
        run: |
          cd backend
          pytest tests/unit/ -v --cov=app --cov-report=xml
      
      - name: Run integration tests
        run: |
          cd backend
          pytest tests/integration/ -v
      
      - name: Run contract tests
        run: |
          cd backend
          pytest tests/contract/ -v
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./backend/coverage.xml
          fail_ci_if_error: true

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run type-check
        run: |
          cd frontend
          npm run type-check
      
      - name: Run ESLint
        run: |
          cd frontend
          npm run lint
      
      - name: Run Prettier check
        run: |
          cd frontend
          npm run format:check
      
      - name: Run unit tests
        run: |
          cd frontend
          npm run test:unit -- --coverage
      
      - name: Build
        run: |
          cd frontend
          npm run build
```

---

> **文档状态**: Round 3 Locked (Final)
> **最后更新**: 2026-04-29
> **修正记录**:
> - Round 1: 错误响应示例统一，测试工厂改为 fixture，pytest.ini 分阶段策略
> - Round 3: 最终审查通过，设计与任务/测试完全匹配
> **下一步**: 进入 Implementation Phase
