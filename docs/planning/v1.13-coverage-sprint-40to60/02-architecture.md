# 02-架构设计文档 (Architecture Design Document)

> **迭代名称**: v1.13-coverage-sprint-40to60
> **日期**: 2026-04-30
> **状态**: Draft (Round 1)

---

## 1. 技术栈 (Technology Stack)

- **后端框架**: FastAPI (Python)
- **测试框架**: pytest
- **覆盖率工具**: pytest-cov
- **Mock 工具**: unittest.mock, pytest-mock
- **数据库**: SQLite (测试用), PostgreSQL (生产)

---

## 2. 测试架构 (Test Architecture)

### 2.1 目录结构

```
backend/
├── app/
│   ├── api/           # API 路由层
│   ├── core/          # 核心配置/安全
│   ├── services/      # 业务逻辑层
│   └── ml/            # ML 模块 (v1.12 已覆盖)
├── tests/
│   ├── test_api/      # API 层测试
│   ├── test_services/ # 服务层测试
│   ├── test_core/     # 核心模块测试
│   └── conftest.py    # 共享固件
└── pytest.ini         # pytest 配置
```

### 2.2 测试策略

#### 2.2.1 单元测试 (Unit Tests)
- **目标**: 覆盖单个函数/方法
- **工具**: pytest, unittest.mock
- **范围**: services/, core/

#### 2.2.2 API 测试 (API Tests)
- **目标**: 覆盖 FastAPI 端点
- **工具**: TestClient (FastAPI)
- **范围**: api/

#### 2.2.3 集成测试 (Integration Tests)
- **目标**: 覆盖模块间交互
- **工具**: pytest, 内存数据库
- **范围**: services + api

### 2.3 Mock 策略

| 依赖 | Mock 方式 | 说明 |
|------|-----------|------|
| Database | SQLite 内存 | 使用 `create_engine("sqlite:///:memory:")` |
| External API | unittest.mock | Mock requests/httpx |
| ML Model | unittest.mock | Mock predict/predict_proba |
| Redis | fakeredis | 内存 Redis 实现 |

---

## 3. 核心模块设计 (Core Module Design)

### 3.1 conftest.py (共享固件)

**状态**: ✅ 已存在 ([tests/conftest.py](file:///e:/code/bysj/backend/tests/conftest.py))

已配置：
- SQLite + aiosqlite 异步内存数据库
- TestClient (FastAPI)
- 用户认证 override (get_current_user)
- 数据库依赖 override (get_db)
- 限速器禁用 (rate_limiter)
- 多种 seed fixtures:
  - `seeded_user_id`: 预置用户 (user/counselor/admin)
  - `seed_risk_and_content`: 风险评估和教育内容
  - `seed_intervention_for_user`: 干预计划和任务
  - `seed_counselor_data`: 咨询师绑定和警告通知
  - `seed_admin_data`: 干预模板和模型反馈

### 3.2 测试基类

```python
# tests/base.py
import pytest
from unittest.mock import Mock, patch

class BaseServiceTest:
    """服务层测试基类"""
    
    @pytest.fixture(autouse=True)
    def setup(self, db_session):
        self.db = db_session
        self.mock_repo = Mock()
```

---

## 4. API 设计 (API Design)

### 4.1 测试端点覆盖

| 端点 | 方法 | 测试优先级 |
|------|------|------------|
| /api/v1/physiological | GET/POST | P0 |
| /api/v1/assessment | GET/POST | P0 |
| /api/v1/warning | GET/PUT | P0 |
| /api/v1/user | GET/PUT | P1 |
| /api/v1/auth | POST | P1 |

### 4.2 测试场景

```python
# 示例: API 测试
def test_create_assessment(client, mock_user):
    response = client.post("/api/v1/assessment", json={
        "user_id": mock_user["id"],
        "data": {"hr": 80, "bp": "120/80"}
    })
    assert response.status_code == 201
    assert "id" in response.json()
```

---

## 5. 数据库设计 (Database Design)

### 5.1 测试数据库

- **类型**: SQLite (内存)
- **初始化**: 每次测试前创建表，测试后销毁
- **固件**: 使用 pytest fixture 提供测试数据

### 5.2 数据固件

```python
# tests/fixtures.py
import pytest
from app.models import User, Assessment

@pytest.fixture
def sample_user(db_session):
    user = User(id=1, username="test", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture
def sample_assessment(db_session, sample_user):
    assessment = Assessment(
        user_id=sample_user.id,
        data={"hr": 80}
    )
    db_session.add(assessment)
    db_session.commit()
    return assessment
```

---

## 6. CI/CD 集成

### 6.1 Workflow 更新

```yaml
# .github/workflows/coverage.yml
- name: Run Tests
  run: |
    cd backend
    pytest --cov=app --cov-report=xml --cov-fail-under=60
```

### 6.2 覆盖率报告

- **格式**: HTML + XML (Codecov)
- **阈值**: 60% (fail-under)
- **通知**: PR comment

---

## 7. 质量门禁 (Quality Gates)

| 门禁 | 标准 | 验证方式 |
|------|------|----------|
| 覆盖率 | >= 60% | pytest-cov |
| 测试通过 | 100% | pytest |
| 代码风格 | pass | flake8/black |
| 类型检查 | pass | mypy |

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-04-30
