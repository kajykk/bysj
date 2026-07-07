# 心理健康风险评估系统 - 架构文档

> **版本**: v1.39-grafana-alert-rules + P0-P2 系统优化
> **更新日期**: 2026-06-28
> **状态**: 生产就绪

---

## 1. 系统概览

心理健康风险评估系统 (Depression Warning System, DWS) 是一个面向高校的心理健康筛查与干预平台,采用**前后端分离 + 多模态 ML 融合 + 异步任务调度 + 全链路可观测性**的全栈架构。

### 1.1 核心能力

| 能力 | 描述 |
|---|---|
| 多模态风险评估 | 结构化问卷 + 文本分析 + 生理信号三模态加权融合 |
| 实时预警通知 | WebSocket 实时推送 + 告警生命周期管理 + 多渠道通知 |
| 智能干预推荐 | 基于风险等级与主导模态的个性化干预计划 |
| 模型治理 | 金丝雀发布 + 漂移检测 + 自动回滚 + 4 层回退 |
| 可观测性 | Prometheus 指标 + Grafana 仪表盘 + Sentry 错误追踪 + 分布式链路 |
| 合规性 | GDPR 数据导出/被遗忘权 + PII 字段加密 + 审计日志 |

### 1.2 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3.5 + TypeScript 5.6 + Vite 6.2 + Element Plus 2.8 + ECharts 5.5 |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic 2.7 |
| ML | scikit-learn 1.8 + PyTorch (可选) + Transformers (可选) + NumPy/Pandas |
| 数据库 | PostgreSQL 15 (生产) / SQLite (开发测试) |
| 缓存/Broker | Redis 7 (缓存 + Celery broker + WebSocket pubsub) |
| 异步任务 | Celery 5.4 + Celery Beat |
| 监控 | Prometheus + Grafana 11.6 + Sentry SDK |
| 容器化 | Docker + docker-compose (9 个服务) |

### 1.3 架构文档导航 (C4 模型 + ADR)

本节提供架构文档的分层导航,便于快速定位系统架构的各个层面。

#### C4 模型 (4 层架构视图)

| 层级 | 文档 | 说明 |
|------|------|------|
| Level 1 | [C4 Context](./architecture/c4-context.md) | 系统上下文图: 用户与外部系统交互 |
| Level 2 | [C4 Container](./architecture/c4-container.md) | 容器图: 9 个 Docker 服务的部署架构 |
| Level 3 | [C4 Component](./architecture/c4-component.md) | 组件图: 后端模块间依赖关系 |
| Level 4 | [C4 Code](./architecture/c4-code.md) | 代码图: ModelEngine / RiskService / ObservabilityExporter 类图 |

#### ADR (架构决策记录)

| 编号 | 标题 | 文档 |
|------|------|------|
| ADR-001 | 选择 FastAPI 而非 Django/Flask | [ADR-001](./architecture/adr/ADR-001-fastapi-selection.md) |
| ADR-002 | 选择 SQLAlchemy 2.0 async + asyncpg | [ADR-002](./architecture/adr/ADR-002-sqlalchemy-async.md) |
| ADR-003 | 选择 Celery 而非 RQ/Dramatiq | [ADR-003](./architecture/adr/ADR-003-celery-selection.md) |
| ADR-004 | 选择 Vue 3 + Composition API | [ADR-004](./architecture/adr/ADR-004-vue3-composition-api.md) |
| ADR-005 | 选择 Element Plus 而非 Ant Design Vue | [ADR-005](./architecture/adr/ADR-005-element-plus.md) |
| ADR-006 | 模型推理使用 asyncio.to_thread | [ADR-006](./architecture/adr/ADR-006-asyncio-to-thread.md) |
| ADR-007 | PII 加密使用 Fernet 对称加密 | [ADR-007](./architecture/adr/ADR-007-fernet-pii-encryption.md) |
| ADR-008 | 健康检查分层 (live/ready/startup) | [ADR-008](./architecture/adr/ADR-008-health-check-probes.md) |
| ADR-009 | Redis pubsub 用于 WebSocket 多 worker | [ADR-009](./architecture/adr/ADR-009-redis-pubsub-websocket.md) |
| ADR-010 | 使用 Alembic 数据库迁移 | [ADR-010](./architecture/adr/ADR-010-alembic-migration.md) |

---

## 2. 组件架构

### 2.1 后端模块结构

```
backend/app/
├── api/v1/              # FastAPI 路由层 (23 个路由文件)
├── core/                # 基础设施层 (33 个模块)
├── models/              # SQLAlchemy ORM (10 个文件, 30+ 张表)
├── schemas/             # Pydantic 请求/响应 Schema (15 个文件)
├── services/            # 业务服务层 (29 个服务)
├── ml/                  # 机器学习模块 (27 个文件)
├── tasks/               # Celery 异步任务 (4 个文件)
├── monitoring/          # 告警生命周期管理 (7 个模块)
├── middleware/          # ASGI 中间件 (3 个: monitoring/security/xss)
└── main.py              # 应用入口 + lifespan 管理
```

### 2.2 核心基础设施模块 (app/core/)

| 模块 | 职责 | 关键特性 |
|---|---|---|
| `config.py` | Pydantic Settings 配置中心 | 运行时检测 ML 依赖可用性,降级策略 |
| `database.py` | SQLAlchemy 异步 engine | 支持 SQLite/PostgreSQL,连接池可调 |
| `cache.py` | Redis 缓存 + 内存回退 | 单例客户端 + 断路器 + LRU+TTL 内存层 |
| `ws.py` | WebSocket 连接管理 | Redis pubsub 多 worker 支持 + node_id 回环保护 |
| `celery_app.py` | Celery 实例 | broker/backend 均为 Redis, 7 个定时任务 |
| `health.py` | 分层健康检查 | /health/live (无 I/O) /ready (缓存) /startup |
| `metrics.py` | Prometheus 指标 | Counter/Histogram/Gauge,零依赖 exposition |
| `security.py` | JWT + bcrypt | access/refresh/reset token,72 字节密码 |
| `pii_crypto.py` | PII 字段加密 | 启动时自动生成临时密钥 (dev) |
| `model_engine.py` | ML 模型引擎 | 多模态加载 + 4 层回退 + 预加载 |
| `fallback_hierarchy.py` | 回退策略 | 主模型→融合→规则→启发式 |

### 2.3 ML 模型架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FusionEngine (融合引擎)                    │
│  默认权重: structured=0.55, text=0.30, physiological=0.15    │
│  动态调整: 基于置信度 + 模态缺失权重重分配                     │
└─────────────────────────────────────────────────────────────┘
                            ↑
            ┌───────────────┼───────────────┐
            │               │               │
   ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
   │ Structured     │ │ Text           │ │ Physiological  │
   │ (结构化问卷)    │ │ (文本分析)     │ │ (生理信号)      │
   │                │ │                │ │                │
   │ LR / RF        │ │ BERT (可选)    │ │ PyTorch MLP    │
   │ Multiclass     │ │ → TF-IDF/LR    │ │ (13 特征)      │
   │ (4 级风险)     │ │ → 启发式回退   │ │                │
   └────────────────┘ └────────────────┘ └────────────────┘
```

**文本分析三级回退** (P0 优化):
1. BERT 模型 (若 Transformers 可用)
2. TF-IDF + LR (improved_bilingual)
3. 启发式规则 (关键词正则匹配)

**CrisisDetector**: 检测文本中的自杀/自伤关键词,命中即强制 critical 级别,绕过融合引擎。

### 2.4 服务层关键服务

| 服务 | 职责 |
|---|---|
| `risk_service` | 风险评估编排,CSV 公式注入防护 |
| `model_predict_service` | 模型预测服务,调用 FusionEngine |
| `intervention_service` | 干预计划推荐与任务执行 |
| `alert_lifecycle_service` | 告警状态机 (DriftAlert/Severity) |
| `gdpr_service` | GDPR 合规:数据导出 + 被遗忘权 |
| `pdf_job_store` | 异步 PDF 任务存储 (P1-4) |
| `observability_service` | 延迟直方图 + 可观测性数据收集 |
| `canary_manager` | 金丝雀发布状态管理 |

---

## 3. 数据流

### 3.1 风险评估主流程

```
用户端 (Vue)
    │
    │  POST /api/v1/user/data/collect
    ▼
[user_data.py] ──→ [user_data_service] ──→ PostgreSQL (StructuredAssessment/TextEntry/PhysiologicalRecord)
    │
    │  POST /api/v1/model/predict/fusion
    ▼
[model_predict.py] ──→ [model_predict_service]
    │
    │  调用 model_engine.predict()
    ▼
[model_engine]
    │
    ├──→ FusionEngine.fuse(structured, text, physiological)
    │       │
    │       ├──→ StructuredModel.predict (LR/RF)
    │       ├──→ TextAnalyzer.analyze → BERT/TF-IDF/启发式
    │       ├──→ PhysiologicalModel.predict (PyTorch MLP)
    │       └──→ CrisisDetector.check (强制 critical)
    │
    │  返回融合分数 + 风险等级 + 模型贡献度
    ▼
[risk_service] ──→ PostgreSQL (RiskAssessment)
    │
    │  若 risk_level >= threshold
    ▼
[warning_service] ──→ PostgreSQL (WarningNotification)
    │
    ├──→ ws_manager.send_to_user (WebSocket 实时推送)
    │       │
    │       ├──→ 本地连接投递
    │       └──→ Redis pubsub → 其他 FastAPI workers
    │
    └──→ Celery task: notify_counselor (异步通知咨询师)
```

### 3.2 异步任务调度

```
Celery Beat (单实例)
    │
    │  按 beat_schedule 触发
    ▼
┌──────────────────────────────────────────┐
│  7 个定时任务:                             │
│  ├── daily_risk_scan (08:00)             │
│  ├── stale_warning_reminder (09:00)      │
│  ├── daily_intervention_check (07:30)    │
│  ├── weekly_log_archive (周一 03:00)     │
│  ├── canary_auto_rollback_check (30s)    │
│  ├── escalate_pending_alerts (60s)       │
│  └── archive_old_alerts (03:00)         │
└──────────────────────────────────────────┘
    │
    ▼
Celery Worker (concurrency=2)
    │
    │  执行任务,通过 Redis pubsub 通知 FastAPI
    ▼
FastAPI Worker (WebSocket 投递给客户端)
```

### 3.3 WebSocket 跨进程通信 (P2-1)

```
┌─────────────┐         ┌──────────────┐
│ Celery Worker│         │ FastAPI Worker│
│ (无 WS 连接) │         │ (持有 WS 连接)│
└──────┬───────┘         └──────┬───────┘
       │                        │
       │  send_to_user()        │
       │  1. 本地发送 (空)      │
       │  2. Redis publish      │
       │     ws:user:{id}       │
       │     ┌────────────┐     │
       │     │   Redis    │     │
       └────→│  pubsub    │─────┘
             └─────┬──────┘
                   │
                   │  pmessage
                   ▼
             FastAPI Worker 的
             _pubsub_loop 收到消息
                   │
                   │  node_id 检查
                   │  (跳过本节点发布的)
                   ▼
             _local_send_to_user()
             投递给本地 WebSocket 连接
```

---

## 4. 部署架构

### 4.1 Docker Compose 拓扑 (9 个服务)

```
                    ┌─────────────┐
                    │   用户端     │
                    │  (浏览器)    │
                    └──────┬──────┘
                           │ :80
                    ┌──────▼──────┐
                    │  frontend   │  Nginx + Vue SPA
                    │  (Nginx)    │  反向代理 → backend:8000
                    └──────┬──────┘
                           │ :8000
                    ┌──────▼──────┐
                    │  backend    │  FastAPI (4 workers)
                    │  (uvicorn)  │  + WebSocket pubsub subscriber
                    └──┬───┬───┬──┘
                       │   │   │
           ┌───────────┘   │   └───────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │ PostgreSQL  │ │    Redis    │ │   Grafana   │
    │   :5432     │ │    :6379    │ │   :3000     │
    │  (持久卷)   │ │  (缓存+broker│ │  (仪表盘)   │
    └─────────────┘ │  +pubsub)   │ └─────────────┘
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │celery_worker│ │ celery_beat │ │alembic_migr │
    │ (任务执行)  │ │ (定时调度)  │ │  (one-shot) │
    │ concurrency │ │  单实例     │ │  迁移完成后  │
    │     =2      │ │             │ │  自动退出    │
    └─────────────┘ └─────────────┘ └─────────────┘
```

### 4.2 启动顺序

```
1. postgres + redis (并行启动, 等待 healthy)
2. alembic_migrate (运行 alembic upgrade head, 完成后退出)
3. backend + celery_worker + celery_beat (并行启动, 等 alembic 完成)
4. frontend (等 backend healthy)
5. grafana (等 backend healthy)
```

### 4.3 资源限制

| 服务 | CPU 限制 | 内存限制 | CPU 预留 | 内存预留 |
|---|---|---|---|---|
| backend | 2.0 | 2G | 0.5 | 512M |
| celery_worker | 1.0 | 1G | 0.25 | 256M |
| celery_beat | 0.5 | 512M | 0.1 | 128M |
| alembic_migrate | 0.5 | 512M | 0.1 | 128M |
| frontend | 0.5 | 256M | 0.1 | 64M |
| grafana | 1.0 | 512M | 0.2 | 128M |

---

## 5. 可观测性架构

### 5.1 监控数据流

```
FastAPI 应用
    │
    ├──→ Prometheus 指标 (/metrics 端点)
    │       │
    │       ▼
    │    Prometheus 抓取 → Grafana 仪表盘
    │
    ├──→ Sentry 错误追踪 (异常自动上报)
    │
    ├──→ 结构化日志 (JSON 格式, 含 request_id)
    │
    └──→ Grafana SimpleJson 数据源
            │
            ▼
        /api/v1/alerts/observability/grafana/*
        (延迟趋势/响应时间/告警统计)
```

### 5.2 健康检查分层 (P0-1.1)

| 端点 | 用途 | 延迟目标 | 实现 |
|---|---|---|---|
| `/health/live` | k8s liveness probe | < 5ms | 仅返回 `{"status":"ok"}`,无 I/O |
| `/health/ready` | k8s readiness probe | < 5ms | 读取 10s 后台刷新的缓存快照 |
| `/health/startup` | k8s startup probe | < 5ms | 检查 `app.state.started` 标志 |

### 5.3 告警生命周期

```
DriftAlert 产生 (漂移检测/金丝雀指标)
    │
    ▼
告警进入系统 (alert_lifecycle_service)
    │
    ├──→ DedupEngine (去重,基于指纹)
    │       │
    │       └──→ DedupLock (Redis 分布式锁, 多实例安全)
    │
    ├──→ Severity 状态机 (info → warning → critical)
    │
    ├──→ Silence 匹配 (静默规则, 按 label/time 匹配)
    │
    └──→ 通知渠道
            ├──→ WebSocket 实时推送 (管理员)
            ├──→ Grafana Alerting (webhook/email/slack)
            └──→ 归档 (AlertArchive, 90 天后)
```

---

## 6. 安全架构

### 6.1 认证与授权

| 层 | 机制 |
|---|---|
| 认证 | JWT (access token 2h + refresh token 7d) |
| 密码 | bcrypt 哈希,72 字节长度限制 |
| 授权 | 基于角色的访问控制 (user/counselor/admin) |
| 限流 | slowapi (受信代理 IP 解析) |
| PII | 字段级加密 (email_hash 盲索引) |
| CSRF | SameSite Cookie + Origin 校验 |
| XSS | DOMPurify + CSP 报告端点 |
| SQL 注入 | SQLAlchemy 参数化查询 |

### 6.2 PII 加密 (P0-1.2)

- 生产环境:强制 32+ 字节强密钥 (环境变量 `PII_ENCRYPTION_KEY`)
- 开发环境:自动生成临时密钥,持久化到 `backend/.pii_key` (重启不失效)
- 加密字段:`email` (AES-256-GCM)
- 盲索引:`email_hash` (HMAC-SHA256,支持按 email 查询)

---

## 7. P0-P2 优化记录

### P0 阶段 (Week 1-2): 稳定性与基线

| 任务 | 状态 |
|---|---|
| P0-1.1 健康检查分层 | ✅ /health/live < 5ms |
| P0-1.2 PII 密钥持久化 | ✅ dev 环境自动生成 |
| P0-1.3 测试失败清零 | ✅ 576+ 项测试全通过 |
| P0-1.4 覆盖率基线 | ✅ --cov-fail-under=40 |
| P0-1.5 joblib 升级 | ✅ 1.3.2 → 1.5.3,模型重序列化 |

### P1 阶段 (Week 3-5): 性能与异步

| 任务 | 状态 |
|---|---|
| P1-1 模型推理异步化 | ✅ asyncio.to_thread |
| P1-2 Redis 连接复用 | ✅ 单例 + 4 个消费方迁移 |
| P1-3 缓存降级 | ✅ LRU+TTL 内存回退 |
| P1-4 PDF 异步队列 | ✅ PdfJobStore + 4 端点 |
| P1-5 Locust 压测基线 | ✅ 3 个加权 User 类 |

### P2 阶段 (Week 6-8): 多实例与容器化

| 任务 | 状态 |
|---|---|
| P2-1 WebSocket 多 worker | ✅ Redis pubsub + node_id 回环保护 |
| P2-2 容器化 | ✅ Celery worker/beat + Alembic 迁移 + .dockerignore |
| P2-3 架构文档 | ✅ 本文档 |
| P2-4 密钥轮换 | 待实施 |

---

## 8. 关键设计决策

### 8.1 为什么用 Redis pubsub 而不是消息队列?

WebSocket 通知是**低延迟、瞬时性**的消息,不需要持久化。Redis pubsub 提供了:
- 亚毫秒级延迟 (与 Redis 缓存共用连接池)
- 无需额外组件 (Redis 已在架构中)
- 自动适配多 worker (每个 FastAPI worker 订阅同一 channel)

消息丢失容忍度: WebSocket 通知失败时,告警已持久化到 PostgreSQL,用户下次刷新页面仍能看到。

### 8.2 为什么 Celery worker 和 FastAPI 共用镜像?

- 减少镜像构建时间 (一次构建,多服务复用)
- 保证代码版本一致性 (无版本漂移风险)
- 简化 CI/CD 流水线 (一个 Dockerfile,一个构建步骤)
- 通过 `command` 字段区分运行命令

### 8.3 为什么用 node_id 而不是消息去重?

WebSocket 通知的 originator (Celery worker 或 FastAPI worker) 需要避免消息回环:
- originator 本地已经发送过消息
- Redis pubsub 会将消息广播给所有订阅者 (包括 originator)
- `node_id` 检查是最轻量的回环保护 (无内存开销,无去重表)

### 8.4 为什么 alembic_migrate 是独立服务?

- **隔离性**: 迁移失败不影响 backend 容器启动
- **顺序保证**: `service_completed_successfully` 确保 backend 等待迁移完成
- **幂等性**: `alembic upgrade head` 可安全重复运行
- **资源隔离**: 迁移过程独占 CPU/内存,不与 backend 竞争

### 8.5 为什么用 Python /proc 检查而不是 pgrep?

`python:3.12-slim` 镜像不包含 `procps` 包 (`pgrep`/`ps` 命令)。安装 `procps` 会增加镜像体积。Python 内置的 `/proc` 文件系统读取是零依赖的替代方案,且更轻量。

---

## 附录

### A. 环境变量清单

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `DATABASE_URL` | ✅ | - | SQLAlchemy 异步连接字符串 |
| `REDIS_URL` | ✅ | - | Redis 连接字符串 (含密码) |
| `JWT_SECRET_KEY` | ✅ | - | JWT 签名密钥 (32+ 字节) |
| `POSTGRES_PASSWORD` | ✅ | - | docker-compose 引用 |
| `REDIS_PASSWORD` | ✅ | - | docker-compose 引用 |
| `PII_ENCRYPTION_KEY` | 生产 | 自动生成 | PII 字段加密密钥 |
| `SENTRY_DSN` | 可选 | 空 | Sentry 错误追踪 |
| `WEB_CONCURRENCY` | 可选 | 4 | FastAPI worker 数 |
| `CELERY_WORKER_CONCURRENCY` | 可选 | 2 | Celery worker 并发数 |
| `CORS_ORIGINS` | 可选 | localhost:5173 | 允许的前端源 |

### B. 测试策略

| 层 | 工具 | 覆盖率 |
|---|---|---|
| 单元测试 | pytest + pytest-asyncio | ~60% |
| 契约测试 | schemathesis + hypothesis | API 契约验证 |
| E2E 测试 | Playwright | 11 个 spec 文件 |
| 性能测试 | Locust + pytest-benchmark | P99 延迟基线 |
| 安全测试 | bandit | 代码安全扫描 |
| 覆盖率门禁 | pytest-cov | --cov-fail-under=40 |

### C. 参考资料

- [SYSTEM_OPTIMIZATION_PLAN.md](file:///e:/code/bysj/docs/SYSTEM_OPTIMIZATION_PLAN.md) - 完整优化计划
- [DEPLOYMENT_GUIDE.md](file:///e:/code/bysj/docs/DEPLOYMENT_GUIDE.md) - 部署指南
- [DEEP_AUDIT_REPORT_202606.md](file:///e:/code/bysj/docs/DEEP_AUDIT_REPORT_202606.md) - 深度审计报告
