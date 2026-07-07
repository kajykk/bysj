# ADR-002: 选择 SQLAlchemy 2.0 async + asyncpg

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统后端基于 FastAPI (见 ADR-001) 运行在 ASGI 事件循环之上, 数据库访问层必须满足以下约束:

1. **异步非阻塞**: 风险评估接口 (`app/api/v1/user_risk.py`)、WebSocket 推送 (`app/core/ws.py`)、告警生命周期服务 (`app/services/alert_lifecycle_service.py`) 均在异步上下文中执行, 若使用同步数据库驱动将阻塞整个事件循环, 导致实时告警延迟。
2. **双数据库支持**: 生产环境使用 PostgreSQL (PII 加密、JSONB、行级安全), 开发与测试环境使用 SQLite (`tests/conftest.py` 依赖 SQLite 内存库), 同一套 ORM 模型与查询代码需在两者间无缝切换。
3. **成熟 ORM 能力**: 业务涉及复杂关联查询 (用户-风险评估-告警-干预-咨询师), 需要 ORM 抽象以降低 SQL 维护成本, 同时支持 Alembic 迁移 (`backend/alembic/`)。
4. **PII 加密与类型安全**: 用户敏感字段 (邮箱、电话、证件号) 需通过 `app/core/pii_crypto.py` 透明加解密, 要求 ORM 提供 `TypeDecorator` 自定义类型能力。

## 决策 (Decision)
采用 **SQLAlchemy 2.0 新版 async API** 作为 ORM, 配合双驱动:

- **PostgreSQL 生产驱动**: `asyncpg>=0.29.0`
- **SQLite 开发/测试驱动**: `aiosqlite>=0.19.0`
- **依赖约束**: `sqlalchemy[asyncio]>=2.0.29` (见 `backend/requirements.txt`)

具体落地方式:
- 异步引擎与 Session 工厂在 `app/core/database.py` 中根据 `settings.database_url` 协议自动选择驱动 (`postgresql+asyncpg://` 或 `sqlite+aiosqlite:///`)。
- Session 通过 `app/core/deps.py` 的 `get_db` 依赖注入到路由层, 使用 `async with AsyncSession` 管理生命周期。
- 数据库熔断器 (`app/core/db_breaker.py`) 包装关键读写, 防止数据库抖动拖垮 API。
- Alembic 迁移脚本 (`backend/alembic/env.py`) 复用同一套模型元数据, 支持双数据库方言。
- PII 字段使用自定义 `TypeDecorator` (`app/core/pii_crypto.py`) 在 ORM 层透明加解密。

## 替代方案 (Alternatives Considered)
- **Tortoise ORM**: 原生异步, 但生态小, 缺少成熟的迁移工具与复杂查询能力, 不适合多关联业务场景。
- **Peewee**: 无原生 async 支持, 需借助异步包装层, 与 FastAPI 事件循环模型不匹配。
- **原生 asyncpg (无 ORM)**: 性能最佳但放弃 ORM 抽象, SQL 维护成本高, PII 加解密需手写, 不利于团队协作。
- **SQLAlchemy 1.4**: async 支持标记为 "alpha/beta", 2.0 版本对 async API 进行了重新设计并稳定化, 1.4 升级路径不清晰。

## 后果 (Consequences)
- **正面**:
  - 成熟 ORM + 异步 + 双数据库支持, 一套模型覆盖开发/测试/生产。
  - SQLAlchemy 2.0 的 `Mapped` / `mapped_column` 类型注解与 Pydantic 协同良好, IDE 补全与类型检查到位。
  - Alembic 迁移与 ORM 元数据统一, 避免迁移与代码漂移。
  - 自定义 `TypeDecorator` 优雅实现 PII 透明加解密, 业务代码无感知。
- **负面**:
  - SQLAlchemy 2.0 API 风格与 1.x 差异较大, 学习曲线陡峭, 团队需适应 `select()` 新风格与 `AsyncSession` 用法。
  - `AsyncSession` 生命周期管理复杂, 忘记 `await session.commit()` 或在请求外使用 session 会导致难以排查的 bug, 需通过 `app/core/deps.py` 严格约束。
  - asyncpg 不支持 SQLite 方言部分特性, 部分 SQL 函数需在模型层做方言适配。
- **中性**:
  - 需建立连接池监控 (`app/core/db_breaker.py` + `app/core/metrics.py`), 防止连接泄漏。

## 关联 (Related)
- ADR-001: FastAPI 框架选型 (事件循环约束驱动了 async 数据库需求)
- `backend/requirements.txt` (SQLAlchemy / asyncpg / aiosqlite 版本)
- `backend/app/core/database.py` (异步引擎与 Session 工厂)
- `backend/app/core/deps.py` (Session 依赖注入)
- `backend/app/core/db_breaker.py` (数据库熔断器)
- `backend/app/core/pii_crypto.py` (PII 透明加解密 TypeDecorator)
- `backend/alembic/env.py` (Alembic 迁移配置)
- `docs/security/secrets-rotation-sop.md` (PII 密钥轮换)
