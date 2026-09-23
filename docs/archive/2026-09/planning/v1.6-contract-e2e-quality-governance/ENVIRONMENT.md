# 依赖与环境说明文档

## 1. Python 环境

### 1.1 版本要求
- Python >= 3.10
- 推荐版本: 3.12

### 1.2 核心依赖
| 包名 | 版本 | 用途 |
|------|------|------|
| fastapi | >=0.104.0 | Web 框架 |
| uvicorn | >=0.24.0 | ASGI 服务器 |
| sqlalchemy | >=2.0.0 | ORM |
| alembic | >=1.12.0 | 数据库迁移 |
| pydantic | >=2.5.0 | 数据验证 |
| scikit-learn | >=1.3.2,<1.4.0 | 机器学习 |
| numpy | >=1.24.0 | 数值计算 |
| pandas | >=2.0.0 | 数据处理 |
| psycopg2-binary | >=2.9.0 | PostgreSQL 驱动 |
| redis | >=5.0.0 | 缓存 |
| celery | >=5.3.0 | 任务队列 |
| python-jose | >=3.3.0 | JWT 认证 |
| passlib | >=1.7.0 | 密码哈希 |
| python-multipart | >=0.0.6 | 文件上传 |
| reportlab | >=4.0.0 | PDF 生成 |
| openpyxl | >=3.1.0 | Excel 生成 |

### 1.3 开发依赖
| 包名 | 版本 | 用途 |
|------|------|------|
| pytest | >=7.4.0 | 测试框架 |
| pytest-asyncio | >=0.21.0 | 异步测试 |
| pytest-cov | >=4.1.0 | 覆盖率 |
| schemathesis | >=3.21.0 | 契约测试 |
| hypothesis | >=6.88.0 | 属性测试 |
| httpx | >=0.25.0 | HTTP 客户端 |
| ruff | >=0.1.0 | 代码检查 |
| black | >=23.0.0 | 代码格式化 |
| mypy | >=1.7.0 | 类型检查 |
| bandit | >=1.7.0 | 安全扫描 |

## 2. Node.js 环境

### 2.1 版本要求
- Node.js >= 18
- 推荐版本: 20

### 2.2 核心依赖
| 包名 | 版本 | 用途 |
|------|------|------|
| vue | ^3.3.0 | 前端框架 |
| vue-router | ^4.2.0 | 路由 |
| pinia | ^2.1.0 | 状态管理 |
| axios | ^1.6.0 | HTTP 客户端 |
| echarts | ^5.4.0 | 图表库 |
| element-plus | ^2.4.0 | UI 组件库 |
| @sentry/vue | ^7.80.0 | 错误追踪 |

### 2.3 开发依赖
| 包名 | 版本 | 用途 |
|------|------|------|
| vite | ^5.0.0 | 构建工具 |
| vitest | ^1.0.0 | 测试框架 |
| @playwright/test | ^1.40.0 | E2E 测试 |
| typescript | ^5.3.0 | 类型系统 |
| eslint | ^8.54.0 | 代码检查 |
| prettier | ^3.1.0 | 代码格式化 |
| @lhci/cli | ^0.12.0 | Lighthouse CI |

## 3. 数据库

### 3.1 PostgreSQL
- 版本: >= 15
- 用途: 主数据库
- 配置: 参见 `backend/alembic.ini`

### 3.2 Redis
- 版本: >= 7
- 用途: 缓存、消息队列

## 4. 外部服务

### 4.1 Sentry
- 用途: 错误追踪
- 配置: `SENTRY_DSN` 环境变量

### 4.2 Codecov
- 用途: 覆盖率报告
- 配置: `CODECOV_TOKEN` 环境变量

## 5. 开发环境搭建

### 5.1 后端
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
alembic upgrade head
```

### 5.2 前端
```bash
cd frontend
npm install
npm run dev
```

### 5.3 测试
```bash
# 后端测试
cd backend
pytest tests/ -v

# 前端测试
cd frontend
npm run test:unit
npx playwright test
```

## 6. 生产环境

### 6.1 Docker
```bash
docker-compose up -d
```

### 6.2 环境变量
```bash
# 必需
DATABASE_URL=postgresql://user:pass@host:5432/db
SECRET_KEY=your-secret-key

# 可选
SENTRY_DSN=https://...
REDIS_URL=redis://localhost:6379
```

## 7. CI/CD

### 7.1 GitHub Actions
- `.github/workflows/contract-tests.yml` - 契约测试
- `.github/workflows/e2e-tests.yml` - E2E 测试
- `.github/workflows/coverage.yml` - 覆盖率
- `.github/workflows/lighthouse.yml` - 性能测试
- `.github/workflows/pr-quality-gates.yml` - PR 质量门禁

### 7.2 质量门禁
- 单元测试通过率: 100%
- 集成测试通过率: 100%
- 契约测试通过率: 100%
- 覆盖率: 后端 >= 85%, 前端 >= 80%
- Lighthouse: 性能 >= 80, 可访问性 >= 90
