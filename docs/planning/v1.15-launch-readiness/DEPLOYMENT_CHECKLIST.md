# 部署检查清单

> **迭代名称**: v1.15-launch-readiness  
> **用途**: 上线前确认构建、配置、启动和健康检查全部可用  
> **状态**: Draft

---

## 1. 前端部署检查

- [ ] 确认前端依赖安装命令。
- [ ] 确认前端生产构建命令。
- [ ] 运行前端生产构建。
- [ ] 确认构建产物目录。
- [ ] 确认 API Base URL 配置。
- [ ] 确认路由刷新策略。
- [ ] 确认静态资源路径正确。
- [ ] 确认核心页面无白屏。

### 前端命令记录

| 项目 | 命令/配置 | 状态 |
|---|---|---|
| 安装依赖 | `cd frontend && npm ci` | ✅ 已确认 |
| 类型检查 | `cd frontend && npm run typecheck` | ✅ 已确认 |
| 生产构建 | `cd frontend && npm run build` | ✅ 已确认 |
| 本地预览 | `cd frontend && npm run preview` | ✅ 已确认 |
| API Base URL | `VITE_API_BASE_URL=/api/v1` | ✅ 已确认 |
| 构建输出目录 | `frontend/dist/` | ✅ 已确认 |

---

## 2. 后端部署检查

- [ ] 确认后端依赖安装命令。
- [ ] 确认后端启动命令。
- [ ] 确认生产环境配置加载方式。
- [ ] 确认健康检查接口路径。
- [ ] 确认 CORS 白名单。
- [ ] 确认认证密钥配置。
- [ ] 确认日志级别。
- [ ] 确认服务端口。
- [ ] 确认核心 API 可访问。

### 后端命令记录

| 项目 | 命令/配置 | 状态 |
|---|---|---|
| 安装依赖 | `cd backend && pip install -r requirements.txt` | ✅ 已确认 |
| 启动服务 | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000` | ✅ 已确认 |
| 健康检查 | `curl http://localhost:8000/health` | ✅ 已确认 |
| 关键测试 | `cd backend && pytest tests/ -x -v` | ✅ 已确认 |
| 数据库迁移 | `cd backend && alembic upgrade head` | ✅ 已确认 |

---

## 3. 数据库检查

- [ ] 确认数据库类型。
- [ ] 确认数据库连接字符串。
- [ ] 确认数据库用户权限。
- [ ] 确认初始化或迁移步骤。
- [ ] 确认核心表结构存在。
- [ ] 确认核心数据可写入。
- [ ] 确认备份策略，如生产需要。

---

## 4. 模型/算法检查

- [ ] 确认模型/算法依赖。
- [ ] 确认模型文件路径或加载方式。
- [ ] 确认目标环境可安装依赖。
- [ ] 确认典型输入可返回结果。
- [ ] 确认异常输入不会导致服务崩溃。

---

## 5. 环境变量检查

| 变量名 | 用途 | 示例/说明 | 是否必需 | 状态 |
|---|---|---|---|---|
| `APP_ENV` | 应用环境 | `production` / `development` / `test` | ✅ 必需 | ✅ 已确认 |
| `DATABASE_URL` | 数据库连接 | `sqlite+aiosqlite:///...` 或 `postgresql+asyncpg://...` | ✅ 必需 | ✅ 已确认 |
| `REDIS_URL` | Redis 连接 | `redis://:password@host:6379/0` | ⚠️ 可选 | ✅ 已确认 |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | ✅ 必需 | ✅ 已确认 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 过期时间 | `120` | ✅ 必需 | ✅ 已确认 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token 过期 | `7` | ✅ 必需 | ✅ 已确认 |
| `PASSWORD_RESET_BASE_URL` | 密码重置链接 | `https://your-domain.com/reset-password` | ✅ 必需 | ✅ 已确认 |
| `SMTP_HOST` | SMTP 服务器 | `smtp.example.com` | ⚠️ 可选 | ✅ 已确认 |
| `SMTP_PORT` | SMTP 端口 | `587` | ⚠️ 可选 | ✅ 已确认 |
| `SMTP_USER` | SMTP 用户名 | `mailer@example.com` | ⚠️ 可选 | ✅ 已确认 |
| `SMTP_PASSWORD` | SMTP 密码 | `change_me` | ⚠️ 可选 | ✅ 已确认 |
| `MODEL_DIR` | 模型文件目录 | `./models` | ✅ 必需 | ✅ 已确认 |
| `VITE_API_BASE_URL` | 前端 API 地址 | `/api/v1` | ✅ 必需 | ✅ 已确认 |
| `CORS_ALLOWED_ORIGINS` | CORS 白名单 | `https://your-domain.com` | ✅ 必需 | ✅ 已确认 |

要求：

- [x] 不提交真实密钥。
- [x] `.env.example` 或等价说明完整。
- [ ] 生产环境变量已配置。
- [x] 本地、CI、生产配置边界明确。

---

## 6. 上线前最终检查

- [ ] 前端构建通过。
- [ ] 后端启动通过。
- [ ] 健康检查通过。
- [ ] 数据库连接通过。
- [ ] 核心 API 通过。
- [ ] 核心流程通过。
- [ ] P0 阻塞项清零。
- [ ] 回滚方案完成。
- [ ] 上线后检查清单完成。

---

> **最后更新**: 2026-05-01
