# Test Environment Setup v1.11.2

> **迭代**: v1.11.2-security-test-closure
> **日期**: 2026-04-30
> **目标**: 明确测试环境依赖配置，支持 release gate 测试集运行

---

## 1. Redis 依赖

### 1.1 状态
- **生产环境**: 使用 Redis 作为 Celery Broker 和缓存后端
- **测试环境**: 通过 mock/patch 替代，无需真实 Redis 服务

### 1.2 测试策略
```python
# 在 conftest.py 中已配置
from app.core.rate_limit import limiter
limiter.enabled = False  # 禁用速率限制器
```

### 1.3 需要 Redis 的测试
- `test_core_health.py` - check_redis 通过 mock 测试
- 所有 Celery 相关测试通过 `patch("app.core.health.celery_app")` mock

---

## 2. Celery 配置

### 2.1 状态
- **生产环境**: Celery worker 异步处理任务
- **测试环境**: 使用 eager 模式或 mock

### 2.2 测试策略
```python
# 测试中直接使用 mock
with patch("app.core.health.celery_app") as mock_celery:
    mock_inspect = MagicMock()
    mock_inspect.stats.return_value = {"worker1": {"stats": "data"}}
    mock_celery.control.inspect.return_value = mock_inspect
```

---

## 3. 数据库配置

### 3.1 状态
- **生产环境**: PostgreSQL (asyncpg)
- **测试环境**: SQLite + aiosqlite (内存或文件)

### 3.2 测试配置
```python
# conftest.py
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test_app.db"
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, future=True)
```

### 3.3 Fixture 策略
- `setup_schema`: session 级别，自动创建/删除表结构
- `db_connection`: 每个测试独立事务，自动回滚
- `db_session`: 基于 connection 的异步 session

---

## 4. BERT/模型 Fixture 策略

### 4.1 状态
- **生产环境**: 加载预训练 BERT 模型进行文本特征提取
- **测试环境**: 使用 mock 模型或跳过模型加载

### 4.2 测试策略
- 模型加载测试通过 `pytest.mark.skipif` 控制
- 使用 mock 替代真实模型推理
- 模型相关测试标记为 `slow` 或 `integration`

---

## 5. Release Gate 测试集

### 5.1 最小生产放行测试集

```bash
cd backend
pytest tests/test_core_health.py \
       tests/test_core_modules.py \
       tests/test_core_security.py \
       tests/api/test_auth_flow.py \
       tests/api/test_csp_report.py \
       tests/test_core_*_extended.py \
       -v
```

### 5.2 通过标准
1. 所有 release gate 测试 100% passed
2. 不出现 import mismatch
3. 不依赖 Redis/Celery/BERT/Postgres 外部不可控服务
4. CSP Report 测试全部通过
5. core/security/auth 关键路径通过

---

## 6. 环境限制说明

以下命令在当前环境返回 exit code `-1073741510`：

- `npm run build`
- `npm audit`
- `bandit -r app`
- `pytest --cov=app`
- `npx lighthouse`

**处理方式**: 配置审查 + 代码审查替代实际运行，CI 环境验证。

---

> **产出日期**: 2026-04-30
> **报告状态**: 已归档
