# DEPLOYMENT_CHECKLIST — 部署检查清单 (v1.28-final)

> **目标环境**: Linux (Ubuntu 22.04 LTS) + Docker Compose
> **生成日期**: 2026-06-02
> **关联**: LAUNCH_BLOCKERS.md, ROLLBACK_PLAN.md

---

## 1. 部署前准备 (Pre-Deployment)

### 1.1 硬件要求

| 角色 | 最低配置 | 推荐配置 | 备注 |
|:---|:---|:---|:---|
| 应用服务器 (backend) | 2 CPU / 4GB RAM | 4 CPU / 8GB RAM | 包含 FastAPI + Celery worker |
| 数据库服务器 (postgres) | 2 CPU / 4GB RAM / 50GB SSD | 4 CPU / 8GB RAM / 200GB SSD | 单机版,生产应独立部署 |
| 缓存 (redis) | 1 CPU / 1GB RAM | 2 CPU / 2GB RAM | 持久化到磁盘 |
| 前端静态资源 | 1 CPU / 512MB | 2 CPU / 1GB | Nginx 反代 |

### 1.2 软件依赖

```bash
# 服务器
docker --version          # >= 24.0
docker compose version   # >= 2.20
git --version            # >= 2.34
openssl version          # >= 3.0

# 客户端
curl --version           # 健康检查
jq --version             # JSON 格式化
```

### 1.3 域名与证书

- [ ] 已购买/解析域名: `depression-warning.example.com`
- [ ] 已申请 SSL 证书 (Let's Encrypt 推荐)
- [ ] 反向代理 (Nginx/Caddy) 已配置 HTTPS 跳转
- [ ] CORS 白名单已添加前端域名

---

## 2. 环境变量配置

### 2.1 必填变量 (`.env` 文件)

```bash
# === 数据库 ===
POSTGRES_PASSWORD=<openssl rand -base64 32>

# === Redis ===
REDIS_PASSWORD=<openssl rand -base64 24>

# === JWT ===
JWT_SECRET_KEY=<openssl rand -base64 64>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# === Sentry (错误监控) ===
SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project>
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_ENVIRONMENT=production

# === CORS ===
CORS_ORIGINS=https://depression-warning.example.com,https://admin.example.com

# === 应用 ===
APP_ENV=production
LOG_LEVEL=INFO
```

### 2.2 生成强随机密钥

```bash
# PostgreSQL 密码
openssl rand -base64 32

# Redis 密码
openssl rand -base64 24

# JWT 密钥 (必须 base64, 64 字节)
openssl rand -base64 64
```

### 2.3 验证环境变量

```bash
# 检查 .env 文件存在且权限正确
ls -la .env
chmod 600 .env   # 仅 root 可读

# 检查所有必填项
grep -E "^(POSTGRES_PASSWORD|REDIS_PASSWORD|JWT_SECRET_KEY|SENTRY_DSN)" .env
```

---

## 3. 后端部署 (Backend)

### 3.1 构建镜像

```bash
cd /opt/dws   # 项目根目录

# 拉取最新代码
git fetch --all
git checkout v1.28-final
git log -1   # 验证 commit hash

# 构建后端镜像 (multi-stage, 约 800MB)
docker compose build --no-cache backend

# 验证镜像
docker images | grep dws-backend
# 应显示: dws-backend v1.28-final <hash>  <size>
```

### 3.2 启动服务

```bash
# 启动 (后台)
docker compose up -d

# 查看状态
docker compose ps
# 所有服务应显示 "Up" + "healthy"

# 查看日志
docker compose logs -f --tail=200 backend
```

### 3.3 健康检查

```bash
# 后端 /health
curl -fsS http://localhost:8000/health
# 预期: {"status":"ok","database":true,...}

# 版本端点
curl -fsS http://localhost:8000/api/v1/version
# 预期: {"version":"v1.28-final","status":"FINAL-GO",...}

# OpenAPI 文档
curl -fsS http://localhost:8000/openapi.json | jq '.info'
```

### 3.4 数据库迁移

```bash
# 进入后端容器
docker compose exec backend bash

# 在容器内执行
cd /app
alembic current
alembic upgrade head
alembic current   # 验证已到 head

# 退出
exit
```

### 3.5 初始化数据

```bash
# 创建管理员账户
docker compose exec backend python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.core.security import get_password_hash

async def main():
    async with AsyncSessionLocal() as db:
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=get_password_hash('CHANGE_ME'),
            role='admin',
            status='active',
        )
        db.add(admin)
        await db.commit()
        print(f'Admin created: {admin.id}')

asyncio.run(main())
"

# 立即修改默认密码!
```

---

## 4. 前端部署 (Frontend)

### 4.1 构建静态资源

```bash
cd /opt/dws/frontend

# 安装依赖
npm ci --no-audit --no-fund

# 生产构建
npm run build

# 产物
ls -la dist/
# 应包含: index.html, assets/, favicon.ico, ...

# 验证构建产物
du -sh dist/
# 预期: < 5MB
```

### 4.2 Nginx 配置

```nginx
# /etc/nginx/sites-available/depression-warning
server {
    listen 80;
    server_name depression-warning.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name depression-warning.example.com;

    ssl_certificate /etc/letsencrypt/live/depression-warning.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/depression-warning.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 前端静态资源
    root /opt/dws/frontend/dist;
    index index.html;

    # SPA 路由 fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反代
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # 健康检查
    location /health {
        proxy_pass http://localhost:8000/health;
        access_log off;
    }

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
}
```

### 4.3 启用配置

```bash
# 创建软链
ln -s /etc/nginx/sites-available/depression-warning /etc/nginx/sites-enabled/

# 测试配置
nginx -t

# 重载
nginx -s reload
```

---

## 5. 模型资产同步

### 5.1 必须存在的 4 个模型目录

```bash
ls -la backend/models/artifacts/
# 期望:
#   physiological/             (4 files: model.json, scaler.json, metrics.json, feature_names.json)
#   structured_v1.20/          (5 files)
#   structured_v1.21/          (12 files)
#   text_depression_classifier/(2 files: model.pkl, vectorizer.pkl)
#   physiological_optimized/   (manifest.json, README.md)  -- 仅占位

# 验证完整性
for dir in physiological structured_v1.20 structured_v1.21 text_depression_classifier; do
    echo "=== $dir ==="
    ls backend/models/artifacts/$dir/
done
```

### 5.2 模型 SHA256 校验

```bash
# 在生产服务器上校验
sha256sum -c models.sha256
# models.sha256 由 v1.28 维护
```

---

## 6. 监控与告警 (Monitoring)

### 6.1 Sentry (应用错误)

```bash
# 验证 Sentry DSN 配置
docker compose exec backend python -c "
from app.core.config import settings
assert settings.sentry_dsn, 'SENTRY_DSN not set'
print('Sentry DSN configured:', settings.sentry_dsn[:30] + '...')
"

# 触发测试错误
curl -X POST http://localhost:8000/api/v1/test/error  # (如存在)
```

### 6.2 Prometheus (可选)

```yaml
# /etc/prometheus/prometheus.yml (追加)
scrape_configs:
  - job_name: 'dws-backend'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['localhost:8000']
```

### 6.3 日志

```bash
# 实时日志
docker compose logs -f backend

# 错误日志过滤
docker compose logs backend 2>&1 | grep -i "error\|exception" | tail -50

# 日志持久化 (可选)
# docker-compose.yml 中添加:
#   backend:
#     volumes:
#       - /var/log/dws:/app/logs
```

---

## 7. 上线验证 (Smoke Test)

### 7.1 用户端流程

```bash
# 1. 注册
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"smoke_test","email":"smoke@test.com","password":"Test1234!"}'

# 2. 登录
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=smoke@test.com&password=Test1234!" | jq -r '.access_token')

# 3. 提交问卷
curl -X POST http://localhost:8000/api/v1/user/data/collect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"age":22,"stress_level":5,"sleep_duration":3}'

# 4. 危机文本测试 (应触发 critical)
curl -X POST http://localhost:8000/api/v1/user/data/text/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"我想自杀,生活没有意义"}'
# 预期: risk_level >= 3
```

### 7.2 管理端流程

```bash
# 登录管理员
ADMIN_TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin@example.com&password=<admin_password>" | jq -r '.access_token')

# 查看系统状态
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/admin/dashboard-summary

# 查看模型快照
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/admin/engine-snapshot
```

### 7.3 健康检查 (终态)

```bash
# 所有服务应 Up + healthy
docker compose ps

# 后端
curl -fsS http://localhost:8000/health
# 预期: {"status":"ok","database":true,"redis":true,"celery_worker":true}

# 前端
curl -fsS -o /dev/null -w "%{http_code}\n" https://depression-warning.example.com/
# 预期: 200
```

---

## 8. 部署后清理

```bash
# 清理构建缓存
docker system prune -af --volumes

# 清理临时文件
rm -rf frontend/node_modules/.cache
rm -rf backend/htmlcov backend/.pytest_cache backend/.coverage

# 备份数据库 (每日 cron)
0 2 * * * /usr/bin/docker compose -f /opt/dws/docker-compose.yml exec -T postgres \
    pg_dump -U depress_admin depression_system | gzip > /backup/dws-$(date +\%Y\%m\%d).sql.gz

# 保留 30 天
find /backup -name "dws-*.sql.gz" -mtime +30 -delete
```

---

## 9. 部署签字

| 角色 | 姓名 | 签字 | 日期 |
|:---|:---:|:---:|:---:|
| 部署工程师 | | | |
| 测试工程师 | | | |
| 运维负责人 | | | |
| 产品负责人 | | | |

---

**关联文档**:
- [LAUNCH_BLOCKERS.md](./LAUNCH_BLOCKERS.md)
- [ROLLBACK_PLAN.md](./ROLLBACK_PLAN.md)
- [FINAL_RELEASE_CHECKLIST.md](./FINAL_RELEASE_CHECKLIST.md)
- [DEFENSE_MATERIALS.md](./DEFENSE_MATERIALS.md)
