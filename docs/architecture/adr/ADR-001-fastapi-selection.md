# ADR-001: 选择 FastAPI 而非 Django/Flask

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
心理健康风险评估系统 (Depression Warning System, DWS) 是一个基于多模态融合的大学生抑郁症预警与干预系统, 后端需要承担以下职责:

1. **高并发异步 API**: 系统需同时处理 WebSocket 实时告警推送 (`app/core/ws.py`)、ML 模型推理 (`app/api/v1/model_predict/`)、PDF 报告导出等长耗时请求, 事件循环中存在大量 I/O 阻塞点 (数据库查询、Redis 缓存、模型加载)。
2. **自动 OpenAPI 文档生成**: 项目采用契约测试驱动 (见 `tests/contract/openapi.json`), 需要框架自动生成 OpenAPI Schema 供前端 `frontend/src/api/` 进行类型映射 (见 `docs/api/v1.5-api-documentation.md`)。
3. **Pydantic 数据校验**: 风险评估、用户上传、PII 加密等接口涉及复杂的嵌套数据结构与字段约束 (`app/schemas/`), 需要在请求入口完成校验并产出统一的错误响应 (`app/core/openapi_responses.py`)。
4. **轻量化需求**: Django 自带的 ORM、模板引擎、admin 后台对本项目均非必需 (本项目使用独立的前端 SPA 与自研管理后台), 引入 Django 会带来不必要的体积与启动开销。

## 决策 (Decision)
选择 **FastAPI (>=0.110.0)** 作为后端框架, 配合 Uvicorn ASGI 服务器运行 (见 `backend/requirements.txt`)。

具体落地方式:
- 路由层使用 `APIRouter` 组织, 按业务域拆分 (`app/api/v1/auth.py`、`app/api/v1/reports.py`、`app/api/v1/user_risk.py` 等)。
- 请求/响应模型统一使用 Pydantic v2 (`app/schemas/`), 通过类型注解自动注入校验与文档。
- 依赖注入通过 `app/core/deps.py` 集中管理 (DB session、当前用户、权限校验)。
- OpenAPI Schema 由 `scripts/export_openapi.py` 导出供契约测试使用。

## 替代方案 (Alternatives Considered)
- **Django REST Framework**: 太重, 自带 ORM/模板/admin 后台与本系统架构不匹配; 异步支持虽在 3.1+ 引入但生态成熟度不及 FastAPI。
- **Flask + Flask-RESTful**: 异步支持不原生, 需借助 ASGI 适配层, 性能与开发体验均不如 FastAPI; 自动文档需额外引入 flasgger 等库。
- **Tornado**: 异步成熟但生态小, 缺少 Pydantic 集成与自动 OpenAPI 能力, 团队熟悉度低。

## 后果 (Consequences)
- **正面**:
  - 原生 `async/await` 支持, 与 SQLAlchemy 2.0 async、asyncpg、aiosqlite 无缝配合 (见 ADR-002)。
  - 自动生成 OpenAPI 文档, 前端类型与契约测试可基于同一份 Schema 生成, 降低前后端联调成本。
  - Pydantic 类型安全贯穿请求校验、配置加载 (`app/core/config.py` 使用 `pydantic-settings`) 与数据序列化。
  - 中间件机制清晰, 便于接入请求 ID 追踪、CSP 报告、限流 (`app/middleware/`)。
- **负面**:
  - 生态不如 Django, 无内置 admin 后台与 ORM, 需自研管理接口 (`app/api/v1/admin.py`、`app/api/v1/admin_metrics.py`)。
  - 异步生态对部分第三方库兼容性需谨慎 (如 `python-magic`、`reportlab` 需放入线程池执行)。
- **中性**:
  - 团队需熟悉 ASGI 部署模型 (Uvicorn worker 数量、事件循环阻塞排查)。

## 关联 (Related)
- ADR-002: SQLAlchemy 2.0 async 数据库选型
- ADR-003: Celery 异步任务选型
- `backend/requirements.txt` (FastAPI 版本约束)
- `backend/app/main.py` (FastAPI 应用入口)
- `backend/app/core/deps.py` (依赖注入)
- `backend/scripts/export_openapi.py` (OpenAPI 导出)
- `docs/api/v1.5-api-documentation.md`
