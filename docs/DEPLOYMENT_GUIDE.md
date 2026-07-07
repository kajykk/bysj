# 部署指南 v1.39

## 概述

本文档描述 Depression Warning System v1.39 版本的生产部署流程，基于 Docker Compose 容器化架构，覆盖 TLS 加密通信、Celery 异步任务、熔断器容错、健康检查、Prometheus 指标 + Grafana 仪表盘可观测性体系。

**版本**: v1.39.0
**更新日期**: 2026-07-03
**架构基线**: Docker Compose 7 服务 (postgres + redis + backend + celery_worker + celery_beat + frontend + grafana)

---

## 架构总览

```
                    ┌─────────────────────────────────────┐
                    │           外部客户端                 │
                    │   (浏览器 / curl / 移动端)           │
                    └──────────┬──────────────────────────┘
                               │
                     HTTPS 443 │  (HTTP 80 → 301 跳转 HTTPS)
                               ▼
                    ┌─────────────────────────────────────┐
                    │     frontend (nginx + Vue SPA)      │
                    │  - TLS 终结 (SEC-P1-006)            │
                    │  - 静态资源 + SPA 路由回退          │
                    │  - API/WS 反向代理 + 限流           │
                    └──────────┬──────────────────────────┘
                               │  (容器内网络)
                               ▼
                    ┌─────────────────────────────────────┐
                    │       backend (FastAPI uvicorn)     │
                    │  - REST API (/api/v1/*)             │
                    │  - WebSocket (/ws/{user_id})        │
                    │  - 5 个健康检查端点                 │
                    │  - Prometheus /metrics              │
                    │  - 熔断器: DB/ML/SMTP/Celery        │
                    └──┬─────────────┬────────────┬───────┘
                       │             │            │
            ┌──────────▼─┐   ┌──────▼─────┐   ┌──▼──────────────┐
            │  postgres  │   │   redis    │   │  celery_worker  │
            │  (PG 15)   │   │  (7-alpine)│   │  + celery_beat  │
            │            │   │  (broker)  │   │  (异步任务)     │
            └────────────┘   └────────────┘   └─────────────────┘
                               ▲
                               │
                    ┌──────────┴──────────────────────────┐
                    │       grafana (11.6.0)              │
                    │  - 仪表盘可视化                      │
                    │  - JSON Datasource → backend        │
                    │  - 14+ 告警规则                      │
                    └─────────────────────────────────────┘
```

---

## 环境要求

### 容器运行时

| 依赖 | 版本 | 说明 |
|------|------|------|
| Docker Engine | 24+ | 容器运行时 |
| Docker Compose | v2.20+ | 服务编排 (使用 `docker compose` 子命令) |
| OpenSSL | 1.1.1+ | 生成自签名 TLS 证书 |

### 后端镜像 (python:3.12-slim 基础)

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.12 | 运行环境 |
| FastAPI | 0.110+ | Web 框架 |
| SQLAlchemy | 2.0+ | 异步 ORM |
| Alembic | 1.13+ | 数据库迁移 |
| Celery | 5.3+ | 异步任务队列 |
| pybreaker / 自实现 | - | 熔断器 |
| scikit-learn | 1.3.2 | 机器学习 (Tabular 模型) |
| PyTorch | 2.0+ | 深度学习 (Text 模型, 可选) |

### 前端镜像 (nginx:1.27-alpine 基础)

| 依赖 | 版本 | 说明 |
|------|------|------|
| Node.js | 18+ | 构建环境 (仅构建阶段) |
| Vue | 3.4+ | 框架 |
| Element Plus | 2.4+ | UI 组件库 |
| ECharts | 5.4+ | 图表库 |
| nginx | 1.27+ | 静态资源 + 反向代理 |

### 基础设施

| 依赖 | 版本 | 说明 |
|------|------|------|
| PostgreSQL | 15 | 主数据库 (生产) |
| Redis | 7 | Celery broker + 缓存 + Pub/Sub |
| Grafana | 11.6.0 | 仪表盘与告警 |

---

## 快速开始 (Docker Compose)

### 1. 克隆项目并准备目录

```bash
git clone <repo-url> bysj
cd bysj
```

### 2. 生成 TLS 证书 (SEC-P1-006)

```bash
# 默认 CN=localhost (开发/测试)
bash scripts/generate-self-signed-cert.sh

# 或指定域名
bash scripts/generate-self-signed-cert.sh example.com
```

输出文件:
- `infra/nginx/certs/server.crt` (证书, 644)
- `infra/nginx/certs/server.key` (私钥, 600, 已加入 .gitignore)

> 浏览器访问自签名证书会警告不安全，点击"高级 → 继续访问"即可。
> 生产环境请替换为 CA 签发证书 (Let's Encrypt / 云厂商免费 DV 证书)，直接覆盖上述两个文件。

### 3. 配置环境变量

在项目根目录创建 `.env` 文件 (参考 `backend/.env.example`):

```env
# === 必填 (生产环境) ===
POSTGRES_PASSWORD=CHANGE_ME_strong_db_password
REDIS_PASSWORD=CHANGE_ME_strong_redis_password
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
GRAFANA_ADMIN_PASSWORD=CHANGE_ME_grafana_admin

# === 应用配置 ===
APP_ENV=production
CORS_ORIGINS=https://your-domain.com
SENTRY_DSN=                            # 可选

# === 邮件 (SMTP) ===
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=noreply@example.com
SMTP_PASSWORD=CHANGE_ME_smtp_password
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=noreply@example.com

# === 密码重置链接 (SEC-P1-002: 生产必须 https://) ===
PASSWORD_RESET_BASE_URL=https://your-domain.com/reset-password

# === Grafana (可选, 调用 /grafana/* 端点鉴权) ===
GRAFANA_SERVICE_TOKEN=                 # 留空表示禁用 SA 鉴权

# === Celery 并发度 ===
CELERY_WORKER_CONCURRENCY=2
```

> **SEC-P1-002 强制约束**: 当 `APP_ENV=production` 时，`PASSWORD_RESET_BASE_URL` 必须以 `https://` 开头，否则应用启动失败 (ValueError)。

### 4. 启动全部服务

```bash
docker compose up -d
```

启动顺序 (由 `depends_on` + `condition` 控制):

```
postgres ─┐
          ├─→ alembic_migrate ──→ backend ──→ frontend
redis ────┘                    ├─→ celery_worker
                               └─→ celery_beat
                                       (backend healthy后启动) ──→ grafana
```

### 5. 验证部署

```bash
# 查看所有服务状态
docker compose ps

# 健康检查 (HTTPS)
curl -k https://localhost/health
# 期望: {"status":"ok","checks":{"database":"ok","redis":"ok","celery_worker":"ok","models":"ok"}}

# 浏览器访问
# https://localhost  (前端 SPA)
# http://localhost:3000  (Grafana, admin / 上面设置的密码)
# http://localhost:8000/docs  (FastAPI Swagger UI, 仅调试用)
```

---

## 服务清单 (docker-compose.yml)

| 服务 | 镜像 | 端口映射 | 健康检查 | 资源限制 |
|------|------|---------|---------|---------|
| `postgres` | postgres:15 | (内部) | `pg_isready` 10s/5s × 5 | - |
| `redis` | redis:7-alpine | (内部) | `redis-cli ping` 10s/5s × 5 | 256mb maxmemory |
| `alembic_migrate` | dws-backend:v1.30 | - | (one-shot) | 0.5 cpu / 512M |
| `backend` | dws-backend:v1.30 | 8000:8000 | `/health` 30s/5s × 3 | 2.0 cpu / 2G |
| `celery_worker` | dws-backend:v1.30 | - | /proc 检查 60s/10s × 3 | 1.0 cpu / 1G |
| `celery_beat` | dws-backend:v1.30 | - | /proc 检查 60s/5s × 3 | 0.5 cpu / 512M |
| `frontend` | dws-frontend:v1.30 | 80:80, 443:443 | `wget --spider https://localhost/health` 30s/5s × 3 | 0.5 cpu / 256M |
| `grafana` | grafana/grafana:11.6.0 | 3000:3000 | `/api/health` 30s/5s × 3 | 1.0 cpu / 512M |
| `test` (可选) | dws-backend:v1.30 (Dockerfile.test) | - | - | 仅 `docker compose run test` 触发 |

**关键设计**:
- `postgres` / `redis` 生产环境**不暴露端口到宿主机**，仅容器间内部通信
- `alembic_migrate` 是 one-shot 服务 (`restart: "no"`)，在 backend/celery 启动前执行 `alembic upgrade head`
- `backend` 等待 `alembic_migrate` 完成 (`service_completed_successfully`) 后才启动
- `frontend` 等待 `backend` 健康后才启动，避免用户访问时后端未就绪

---

## TLS / HTTPS 配置 (SEC-P1-006)

### nginx 配置要点 (frontend/nginx.conf)

- **80 端口**: 永久 301 跳转到 HTTPS
- **443 端口**: TLS 1.2 / 1.3 (禁用 SSLv3/TLSv1.0/TLSv1.1)
- **密码套件**: ECDHE 前向保密 + AES-GCM/CHACHA20 (Mozilla Intermediate 兼容性)
- **会话缓存**: `shared:SSL:10m` (~4 万会话)，关闭会话票据 (RFC 5077)
- **HSTS**: `max-age=31536000; includeSubDomains`
- **CSP**: `default-src 'self'; ...` (与前端 csp.ts 一致)

### 证书管理

| 环境 | 证书来源 | 生成/获取方式 |
|------|---------|--------------|
| 开发/测试 | 自签名 | `bash scripts/generate-self-signed-cert.sh` |
| 生产 (推荐) | Let's Encrypt | certbot 自动续期 / ACME 挑战 |
| 生产 (备选) | 云厂商 DV/OV 证书 | 上传到 `infra/nginx/certs/` 覆盖默认文件 |

证书路径 (容器内): `/etc/nginx/certs/server.crt` + `server.key`
证书路径 (宿主机): `infra/nginx/certs/server.crt` + `server.key` (已 .gitignore)

---

## 环境变量详解

### 应用基础配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_NAME` | Depression Warning System | 应用名称 |
| `APP_VERSION` | 3.1.0 | 应用版本 (随发布更新) |
| `APP_ENV` | development | 环境: development / production / test |

### 数据库配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | sqlite+aiosqlite:///depression_system.db | SQLAlchemy 异步连接串 |
| `POSTGRES_PASSWORD` | (必填) | Docker Compose 中 PostgreSQL 密码 |
| `DB_STATEMENT_TIMEOUT` | 10 | SQL 语句级超时 (秒, STAB-P0-002, 仅 PostgreSQL 生效) |

> 生产环境 `DATABASE_URL` 应为:
> `postgresql+asyncpg://depress_admin:${POSTGRES_PASSWORD}@postgres:5432/depression_system`

### Redis 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_URL` | redis://localhost:6379/0 | Redis 连接串 |
| `REDIS_PASSWORD` | (必填) | Docker Compose 中 Redis 密码 |

> 生产环境 `REDIS_URL` 应为:
> `redis://:${REDIS_PASSWORD}@redis:6379/0`

### JWT 安全配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET_KEY` | (必填) | JWT 签名密钥, 生成命令: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `JWT_ALGORITHM` | HS256 | 签名算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 120 | Access Token 有效期 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | Refresh Token 有效期 |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | 30 | 密码重置 Token 有效期 |

### 邮件服务配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SMTP_HOST` | (空) | SMTP 服务器地址 |
| `SMTP_PORT` | 587 | SMTP 端口 |
| `SMTP_USER` | (空) | SMTP 用户名 |
| `SMTP_PASSWORD` | (空) | SMTP 密码 |
| `SMTP_USE_TLS` | true | 是否启用 STARTTLS |
| `SMTP_FROM_EMAIL` | (空) | 发件人邮箱 |

### 密码重置 (SEC-P1-002)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PASSWORD_RESET_BASE_URL` | http://localhost:5173/reset-password | 密码重置链接前缀 |

> **生产环境强制约束**: 当 `APP_ENV=production` 时，此变量必须以 `https://` 开头，否则应用启动失败。
> HTTP 链接会通过明文传输 password reset token，存在中间人攻击风险。

### CORS 与安全

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CORS_ORIGINS` | http://localhost:5173 | 允许的 CORS 源 (逗号分隔) |
| `CORS_ALLOWED_ORIGINS` | http://localhost:5173,http://localhost:3000 | 备用 CORS 配置 |

### 模型与数据

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_DIR` | models | ML 模型文件目录 |
| `ENABLE_SEED` | false | 是否初始化种子数据 |

### 监控与可观测性

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SENTRY_DSN` | (空) | Sentry 错误监控 DSN |
| `SENTRY_ENVIRONMENT` | development | Sentry 环境标签 |
| `SENTRY_TRACES_SAMPLE_RATE` | 0.1 | Sentry 性能采样率 |
| `GRAFANA_SERVICE_TOKEN` | (空) | Grafana SA Token, 调用 /grafana/* 端点鉴权 |
| `GRAFANA_ADMIN_PASSWORD` | (必填) | Grafana 管理员密码 (Docker Compose 用) |

### Celery 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CELERY_WORKER_CONCURRENCY` | 2 | Celery worker 并发数 |

---

## 数据库迁移 (Alembic)

### 自动迁移 (推荐)

`docker compose up` 启动时，`alembic_migrate` 服务会自动执行 `alembic upgrade head`，无需手动操作。

### 手动迁移

```bash
# 进入 backend 容器
docker compose exec backend bash

# 生成新迁移 (开发环境)
alembic revision --autogenerate -m "add xxx table"

# 应用迁移
alembic upgrade head

# 回滚一个版本
alembic downgrade -1

# 查看当前版本
alembic current
```

### 关键表结构 (v1.39)

- `users` - 用户表 (含 role CheckConstraint: user/admin/counselor)
- `risk_records` - 风险评估记录
- `warnings` - 预警记录
- `warning_audits` - 预警审计日志
- `monitoring_logs` - 监控指标日志
- `canary_records` - 灰度发布记录
- `validation_results` - 离线验证结果
- `drift_alerts` - 漂移告警
- `export_tasks` / `excel_jobs` - 报告导出任务
- `operation_logs` - 操作日志 (含告警 fired/resolved, 用于 MTTR 计算)
- `alert_archives` - 告警归档 (90 天后从 operation_logs 转入)
- `alerts` - 活跃告警
- `alert_silences` - 告警静默规则

---

## 健康检查端点

应用提供 5 个健康检查端点 (均在 main.py 顶层注册, 限流豁免):

| 端点 | 方法 | 用途 | 检查项 |
|------|------|------|--------|
| `/health` | GET | 完整健康检查 (阻塞) | database + redis + celery_worker + models |
| `/health/live` | GET | 存活探针 (轻量, <5ms) | 仅进程存活 + 事件循环响应 |
| `/health/ready` | GET | 就绪探针 (非阻塞, <5ms) | 读取后台任务缓存的健康快照 |
| `/health/startup` | GET | 启动探针 | app.state.started (启动完成前 503) |
| `/health/seed` | GET | 种子数据就绪 | app.state.seed_ready |

### 响应示例 (/health)

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "celery_worker": "ok",
    "models": "ok"
  }
}
```

> `redis` / `celery_worker` / `models` 失败标记为 "failed (optional)"，不影响整体 `status` (仅 `database` 失败才降级为 "degraded")。

### Kubernetes 探针映射

| Probe 类型 | 推荐端点 | 阈值 |
|-----------|---------|------|
| `livenessProbe` | `/health/live` | period 10s, failureThreshold 3 |
| `readinessProbe` | `/health/ready` | period 5s, failureThreshold 2 |
| `startupProbe` | `/health/startup` | period 10s, failureThreshold 30 (5 分钟) |

### Docker Compose 健康检查

- `backend`: `curl -fsS http://localhost:8000/health` 30s/5s × 3
- `frontend`: `wget --no-check-certificate --spider https://localhost/health` 30s/5s × 3
- `postgres`: `pg_isready -U depress_admin` 10s/5s × 5
- `redis`: `redis-cli -a ${REDIS_PASSWORD} ping` 10s/5s × 5
- `celery_worker` / `celery_beat`: 检查 /proc 中是否有对应进程 60s × 3
- `grafana`: `wget --spider http://localhost:3000/api/health` 30s/5s × 3

---

## 监控与可观测性

### Prometheus 指标 (/metrics)

后端通过 `/metrics` 端点 (顶层注册) 暴露 Prometheus 格式指标，包含:

**应用指标**:
- `http_requests_total{method,path,status}` - HTTP 请求总数
- `http_request_duration_seconds{method,path}` - HTTP 请求延迟分布
- `model_predict_total{model_type,status}` - ML 预测次数
- `model_predict_duration_seconds{model_type}` - ML 预测延迟
- `model_success_rate` - 模型成功率
- `fallback_rate` - 回退率

**熔断器指标**:
- `db_circuit_failure_count` - DB 熔断器失败计数
- `db_circuit_state` - DB 熔断器状态 (0=closed, 1=open, 2=half_open)
- `ml_circuit_failure_count` / `ml_circuit_state` - ML 熔断器
- `smtp_circuit_failure_count` / `smtp_circuit_state` - SMTP 熔断器
- `celery_circuit_failure_count` / `celery_circuit_state` - Celery 熔断器
- `redis_circuit_state` - Redis 熔断器

**连接池指标**:
- `db_pool_size` - DB 连接池大小
- `db_pool_utilization` - DB 连接池使用率

**告警与 MTTR 指标**:
- `alert_mttr_seconds{severity}` - 按严重程度分组的平均恢复时长 (AR-206 阈值 300s)
- `alert_resolved_total` - 24h 内已配对恢复的告警总数
- `alert_unresolved_count` - 24h 内未恢复的告警数 (AR-207 阈值 >0 持续 1h)
- `celery_worker_heartbeat` - Celery worker 心跳 (1.0=活, 0.0=死)

### Grafana 仪表盘

- 访问地址: `http://localhost:3000` (admin / `GRAFANA_ADMIN_PASSWORD`)
- 数据源: simpod-json-datasource (JSON Datasource 插件)
- Provisioning: `infra/grafana/provisioning/` (datasources + dashboards + alerting)
- 仪表盘 JSON: `infra/grafana/dashboards/`
- 鉴权: 调用后端 `/grafana/*` 端点时使用 `GRAFANA_SERVICE_TOKEN` (留空表示禁用 SA 鉴权，仅允许 Admin User JWT)

### 告警规则 (21 条)

告警规则定义在 `backend/app/core/alert_rules.py`，按 `labels` 中 `category` 标签分类:

| 类别 | 规则数 | 规则 ID | 示例 |
|------|--------|---------|------|
| 性能 (performance) | 2 | AR-001/002 | P95 延迟 >2s 持续 5min (AR-001)、P99 延迟 >5s 持续 5min (AR-002) |
| 资源 (resource) | 3 | AR-101~103 | CPU >80% 持续 10min (AR-101)、内存 >75% 持续 10min (AR-102)、DB 连接池使用率 >80% 持续 5min (AR-103) |
| 稳定性 (stability) | 8 | AR-003/201~207 | 5xx 错误率 >0.1% 持续 5min (AR-003)、DB 熔断器 OPEN (AR-201)、Redis 不可用 (AR-202)、模型 fallback 率 >30% (AR-203)、Celery 任务失败激增 (AR-204)、Celery 心跳失败 (AR-205)、MTTR >300s (AR-206)、未恢复告警 >0 持续 1h (AR-207) |
| 安全 (security) | 6 | AR-301~306 | 鉴权失败激增 (AR-301)、审计日志写入失败 (AR-302)、高频访问 (AR-303, SEC-P1-005)、非工作时间访问 (AR-304)、异地访问 (AR-305)、横向越权 (AR-306) |
| 可维护性 (maintainability) | 2 | AR-401/402 | 测试覆盖率 <60% (AR-401)、循环依赖 >0 (AR-402) |
| **合计** | **21** | - | - |

---

## 熔断器体系

系统实现了 5 个熔断器，覆盖所有外部依赖:

| 熔断器 | 模块 | 失败阈值 | 恢复超时 | HALF_OPEN 最大调用 | 失败分类器 |
|--------|------|---------|---------|------------------|-----------|
| DB | `app/core/db_breaker.py` | 5 | 30s | 1 | OperationalError/OSError/TimeoutError |
| ML | `app/core/ml_breaker.py` | 5 | 30s | 1 | TimeoutError/OSError/FileNotFoundError/RuntimeError/MemoryError/ImportError |
| SMTP | `app/core/smtp_breaker.py` | 5 | 60s | 1 | smtplib.SMTPException/OSError/ConnectionError/TimeoutError |
| Celery | `app/core/celery_breaker.py` | 5 | 30s | 1 | kombu.exceptions.OperationalError/celery.exceptions.TimeoutError/redis.exceptions.ConnectionError |
| Redis | (内置降级) | - | - | - | 连接失败自动降级到内存缓存 |

### 熔断器状态机

```
CLOSED ──(连续 N 次失败)──→ OPEN ──(恢复超时后)──→ HALF_OPEN ──(测试成功)──→ CLOSED
                                                          │
                                                          └──(测试失败)──→ OPEN
```

- `CLOSED`: 正常放行请求
- `OPEN`: 拒绝请求 (DB/ML/SMTP → 503; Celery → 快速失败返回 False)
- `HALF_OPEN`: 放行有限次测试请求 (默认 1 次)

### 服务降级行为

| 熔断器 | OPEN 时行为 |
|--------|-----------|
| DB | 返回 503 SERVICE_UNAVAILABLE |
| ML | 返回 503, 前端可降级到启发式规则 |
| SMTP | 转为 ValueError("邮件服务暂时不可用，请稍后重试") 快速失败 |
| Celery | 健康检查返回 False; 金丝雀回滚由 asyncio.create_task fallback 接管 (STAB-P1-009) |
| Redis | 自动降级到内存缓存 (不触发熔断, 仅日志告警) |

### 金丝雀回滚 fallback (STAB-P1-009)

`canary_fallback_monitor.py` 在 FastAPI lifespan 进程内启动后台任务:
- 每 30s 检查 `celery_breaker` 状态
- `closed`: 跳过 (让 Celery beat 处理，避免双重执行)
- `open` / `half_open`: 调用 `auto_rollback_service.check_all_canaries()` 执行 fallback rollback check

---

## Celery 异步任务

### 定时任务 (beat_schedule)

定义在 `backend/app/core/celery_app.py`:

| 任务名 | 调度 | 说明 |
|--------|------|------|
| `daily-risk-scan` | 08:00 每天 | 每日风险扫描 |
| `stale-warning-reminder` | 09:00 每天 | 过期预警提醒 |
| `daily-intervention-check` | 07:30 每天 | 每日干预检查 |
| `weekly-log-archive` | 03:00 每周一 | 每周日志归档 |
| `canary-auto-rollback-check` | 每 30s | 金丝雀自动回滚检查 (Celery 不可用时由 canary_fallback_monitor 接管, STAB-P1-009) |
| `escalate-pending-alerts` | 每 60s | 告警升级 (v1.34) |
| `archive-old-alerts` | 03:00 每天 | 告警归档 (v1.34) |
| `flush-lock-stats` | 每 60s | dedup_lock 统计 flush (v1.36) |
| `cleanup-training-jobs` | 每 6h | TRAINING_JOBS 字典 LRU 清理 (RES-P1-005) |
| `cleanup-uploads-dir` | 03:30 每天 | uploads/ 目录清理 30 天前文件 (RES-P1-006) |
| `cleanup-experiment-artifacts` | 04:00 每周一 | experiment artifact 清理保留最近 10 次 (RES-P1-007) |
| `detect-anomaly-access` | 每 5min (300s) | 异常访问检测扫描 OperationLog (SEC-P1-005, AR-303~306) |

### 资源限制

- `celery_worker`: `--concurrency=2` `--max-tasks-per-child=100` `--time-limit=300` `--soft-time-limit=270`
- `celery_beat`: 单实例运行 (避免重复调度)
- 资源限制: worker 1.0 cpu / 1G, beat 0.5 cpu / 512M

---

## 限流策略

### nginx 层 (frontend/nginx.conf)

| Zone | 路径 | 速率 | burst |
|------|------|------|-------|
| `api_limit` | `/api/` | 10 r/s | 20 |
| `auth_limit` | `/api/v1/auth/` | 10 r/m | 10 |
| `auth_refresh_limit` | `/api/v1/auth/refresh` | 20 r/m | 5 |

### 应用层 (slowapi)

| 接口类别 | 限流 |
|---------|------|
| PDF/Excel 生成、ML 实验、校验运行 | 5/minute |
| 金丝雀部署/回滚/pause/resume/traffic | 10/minute |
| 普通查询 (列表/详情/templates) | 30/minute |

健康检查端点 (`/health/*`) 全部 `@limiter.exempt` 豁免限流。

---

## 性能基准

### 资源使用 (Docker Compose limits)

| 服务 | CPU 限制 | 内存限制 | CPU 预留 | 内存预留 |
|------|---------|---------|---------|---------|
| backend | 2.0 | 2G | 0.5 | 512M |
| celery_worker | 1.0 | 1G | 0.25 | 256M |
| celery_beat | 0.5 | 512M | 0.1 | 128M |
| frontend | 0.5 | 256M | 0.1 | 64M |
| grafana | 1.0 | 512M | 0.2 | 128M |
| alembic_migrate | 0.5 | 512M | 0.1 | 128M |
| **总计** | **5.0** | **4.75G** | **1.25** | **1.18G** |

### 延迟目标

| 场景 | 平均延迟 | P99 延迟 | 成功率 |
|------|---------|---------|--------|
| 风险评估 (Tabular) | < 150ms | < 300ms | > 99% |
| 风险评估 (Text) | < 200ms | < 500ms | > 98% |
| 监控查询 | < 50ms | < 100ms | > 99.9% |
| 报告导出 (异步) | < 5s | < 10s | > 98% |
| 健康检查 (/health/live) | < 5ms | < 10ms | > 99.9% |

---

## 故障排查

### 1. 服务启动失败

**症状**: `docker compose up` 后某些服务持续 unhealthy 或退出

**排查步骤**:

```bash
# 查看服务状态
docker compose ps

# 查看具体服务日志
docker compose logs backend
docker compose logs celery_worker
docker compose logs alembic_migrate

# 检查环境变量是否注入
docker compose config
```

**常见原因**:
- `POSTGRES_PASSWORD` / `REDIS_PASSWORD` / `JWT_SECRET_KEY` / `GRAFANA_ADMIN_PASSWORD` 未设置 (启动失败提示 "must be set")
- `PASSWORD_RESET_BASE_URL` 在 production 环境未使用 https:// (启动失败提示 ValueError)
- `alembic_migrate` 失败导致 backend/celery 等待 `service_completed_successfully` 超时

### 2. TLS 证书问题

**症状**: 浏览器访问 https://localhost 提示证书无效

**排查**:
```bash
# 检查证书是否存在
ls -la infra/nginx/certs/

# 重新生成
bash scripts/generate-self-signed-cert.sh

# 检查证书内容
openssl x509 -in infra/nginx/certs/server.crt -text -noout
```

### 3. 熔断器 OPEN

**症状**: API 返回 503 SERVICE_UNAVAILABLE

**排查**:
```bash
# 查看熔断器状态 (通过 /metrics)
curl -k https://localhost/metrics | grep circuit_state

# state=1 表示 OPEN
```

**解决方案**:
- DB OPEN: 检查 postgres 容器健康 → 等待 30s 自动 HALF_OPEN → 测试成功后 CLOSED
- ML OPEN: 检查模型文件 (models/ 目录) + ML 推理服务
- SMTP OPEN: 检查 SMTP 服务器连通性 → 等待 60s 自动恢复
- Celery OPEN: 检查 redis 容器健康 + celery_worker 进程

### 4. Celery 任务未执行

**症状**: 定时任务未触发，或异步任务堆积

**排查**:
```bash
# 检查 celery_worker 进程
docker compose exec celery_worker celery -A app.core.celery_app inspect ping

# 检查 celery_beat 进程
docker compose exec celery_beat ps aux | grep beat

# 查看任务队列
docker compose exec celery_worker celery -A app.core.celery_app inspect active
```

### 5. 前端 502/504

**症状**: 浏览器访问 https://localhost 返回 502 或 504

**排查**:
```bash
# 检查 backend 健康
docker compose ps backend
docker compose logs backend --tail 50

# 检查 nginx 配置
docker compose exec frontend nginx -t

# 检查 nginx 日志
docker compose exec frontend cat /var/log/nginx/error.log
```

---

## 回滚策略

### 应用回滚

```bash
# 回滚到上一版本镜像
docker compose down
# 编辑 docker-compose.yml: image: dws-backend:v1.29 (降级版本号)
docker compose up -d
```

### 数据库回滚

```bash
# 回滚一个 Alembic 版本
docker compose exec backend alembic downgrade -1

# 回滚到指定版本
docker compose exec backend alembic downgrade <revision_id>
```

### 金丝雀发布回滚

```bash
# 通过 API 回滚
curl -X POST https://localhost/api/v1/canary/deployments/{deployment_id}/rollback \
  -H "Authorization: Bearer <admin_token>"
```

> 当 Celery 不可用时，`canary_fallback_monitor` 会自动接管回滚检查 (STAB-P1-009)。

---

## 安全注意事项

1. **密钥管理**: 所有密钥通过环境变量注入 (`.env` 文件不提交，已在 .gitignore)
2. **TLS 强制**: HTTP 80 自动 301 跳转 HTTPS 443 (SEC-P1-006)
3. **密码重置链接**: 生产环境必须 `https://` (SEC-P1-002, 启动时校验)
4. **PostgreSQL/Redis 端口不暴露**: 仅容器间内部通信
5. **CSP/HSTS/X-Frame-Options**: nginx 层设置完整安全头
6. **限流**: nginx 层 (api/auth/refresh 三档) + 应用层 (slowapi 5/10/30 per minute)
7. **熔断器**: 5 个熔断器覆盖所有外部依赖，防止级联失败
8. **审计日志**: `operation_logs` 表记录所有关键操作，保留 90 天后归档到 `alert_archives`
9. **GDPR 合规**: 提供 `/api/v1/user/gdpr/*` 数据导出与删除接口

---

## 附录

### 相关文档

- [API 文档](./api/v1.5-api-documentation.md) (待补齐为 v1.39 全量 API, MAINT-P1-002)
- [OpenAPI 规范](../backend/tests/contract/openapi.json)
- [CHANGELOG](../CHANGELOG.md)
- [系统优化状态](../.trae/sysopt/STATE.md)

### 运维命令速查

```bash
# 启动全部服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看实时日志
docker compose logs -f backend

# 重启某个服务
docker compose restart backend

# 进入容器
docker compose exec backend bash
docker compose exec postgres psql -U depress_admin depression_system

# 停止全部服务
docker compose down

# 停止并删除数据卷 (谨慎!)
docker compose down -v

# 重新构建镜像
docker compose build backend
docker compose build frontend

# 运行测试
docker compose run test
```

### 联系方式

- 技术支持: tech@example.com
- 运维值班: ops@example.com

---

## 变更日志

### v1.39.0 (2026-07-03)

- **重写** 部署指南对齐 v1.39 架构 (MAINT-P1-001)
- **新增** Docker Compose 7 服务架构文档
- **新增** TLS/HTTPS 配置章节 (SEC-P1-006)
- **新增** 熔断器体系章节 (DB/ML/SMTP/Celery/Redis)
- **新增** 健康检查端点章节 (5 个端点 + K8s 探针映射)
- **新增** Prometheus 指标 + Grafana 仪表盘章节
- **新增** Celery 定时任务清单 (10 个 beat task)
- **新增** 限流策略章节 (nginx + slowapi 双层)
- **废弃** v1.5 时代的 `pip install + uvicorn` 直接启动方式
- **废弃** v1.5 时代的 80 端口 nginx 配置 (改为 443 TLS + 80 跳转)
