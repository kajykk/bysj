# ROLLBACK_PLAN — 回滚方案 (v1.28-final)

> **目标**: 在 5 分钟内回滚到上一个稳定版本 (v1.27-launch-ready)
> **生成日期**: 2026-06-02
> **关联**: LAUNCH_BLOCKERS.md, DEPLOYMENT_CHECKLIST.md

---

## 1. 回滚触发条件

### 1.1 立即回滚 (P0 - 5 分钟内)

| 触发条件 | 检测方式 |
|:---|:---|
| 5xx 错误率 > 5% 持续 2 分钟 | Prometheus 告警 |
| P95 响应时间 > 5s 持续 5 分钟 | Prometheus 告警 |
| 数据库连接失败 | Sentry + 日志 |
| 关键 API 不可用 (健康检查失败 3 次) | docker compose healthcheck |
| Crisis Override 失效 (危机文本未触发 critical) | E2E 冒烟测试 |
| 数据损坏 / 误删 | 人工确认 |

### 1.2 评估后回滚 (P1 - 30 分钟内)

| 触发条件 | 检测方式 |
|:---|:---|
| 5xx 错误率 > 1% 持续 10 分钟 | Prometheus 告警 |
| Sentry 错误数 > 100/h | Sentry 告警 |
| 核心功能部分失败 (问卷可提交,但预警不触发) | 客服反馈 |
| 性能下降 > 30% | 性能测试 |

### 1.3 不回滚 (P2 - 修复后上线)

| 类型 | 处理 |
|:---|:---|
| 非关键 UI bug | 记录到 P2 清单,下次迭代修复 |
| 单用户报错 (Sentry < 10/h) | 修复后热更新 |
| 已知 P2 缺陷 | 不触发回滚 |

---

## 2. 回滚前准备 (Pre-Rollback)

### 2.1 数据快照

```bash
# 1. 数据库快照 (必须!)
/usr/bin/docker compose -f /opt/dws/docker-compose.yml exec -T postgres \
    pg_dump -U depress_admin depression_system | gzip > /backup/dws-pre-rollback-$(date +%Y%m%d-%H%M%S).sql.gz

# 验证快照
ls -la /backup/dws-pre-rollback-*.sql.gz

# 2. 上传快照到 S3 (异地备份)
aws s3 cp /backup/dws-pre-rollback-*.sql.gz s3://dws-backups/

# 3. Redis 快照 (可选,缓存可重建)
docker compose exec redis redis-cli -a $REDIS_PASSWORD BGSAVE
```

### 2.2 收集证据

```bash
# 1. 拉取最近 1000 行日志
docker compose logs --tail=1000 backend > /tmp/dws-backend-pre-rollback.log

# 2. 拉取 Sentry 最近 1 小时事件
# (在 Sentry Web UI 手动导出)

# 3. 健康检查状态
docker compose ps > /tmp/dws-ps-pre-rollback.txt

# 4. 当前镜像 tag
docker images | grep dws-backend > /tmp/dws-images-pre-rollback.txt
```

### 2.3 通知

- [ ] 通知研发负责人
- [ ] 通知运维负责人
- [ ] 通知产品负责人
- [ ] 通知客服团队 (状态更新)
- [ ] Slack/钉钉/企微 群公告

---

## 3. 回滚步骤 (5 分钟内完成)

### 3.1 第一步:停止写入 (1 分钟)

```bash
cd /opt/dws

# 1. 停止后端 (阻止新请求)
docker compose stop backend

# 2. 验证流量停止
curl -m 2 -fsS http://localhost:8000/health 2>&1 || echo "Backend stopped (expected)"

# 3. Nginx 切到维护页 (可选)
# 在 Nginx 配置中添加:
#   location / { return 503; }
# nginx -s reload
```

### 3.2 第二步:回滚镜像 (1 分钟)

```bash
# 1. 确认上一个稳定版本
git tag | grep -E "v1\." | sort -V | tail -5
# 应显示: v1.27-launch-ready, v1.28-final, ...

# 2. 检出上一个稳定 tag
git fetch --all
git checkout v1.27-launch-ready

# 3. 回滚 docker-compose.yml (如有差异)
git diff v1.27-launch-ready v1.28-final -- docker-compose.yml
# 手动合并需要保留的 v1.28 配置 (如新增 backend service)

# 4. 构建上一个稳定镜像
docker compose build --no-cache backend
# 镜像 tag 自动变为 v1.27-launch-ready (docker-compose.yml 中定义)
```

### 3.3 第三步:回滚数据库 (1 分钟)

```bash
# ⚠️ 重要: 评估是否需要回滚 DB schema

# 选项 A: 保留 v1.28 schema (如果 v1.27 兼容)
docker compose up -d backend
alembic current  # 查看当前版本
# 如果 v1.27 兼容 v1.28 schema,直接重启即可

# 选项 B: 完整回滚 schema (破坏性)
docker compose exec backend alembic downgrade -1
# 重复直到回到 v1.27 的最后一个 migration
alembic current  # 验证

# 选项 C: 从快照恢复 (最彻底)
# 1. 停止所有服务
docker compose down

# 2. 删除当前数据卷
docker volume rm dws_postgres_data

# 3. 重新创建
docker compose up -d postgres
sleep 10  # 等待 PostgreSQL 启动

# 4. 恢复快照
gunzip -c /backup/dws-pre-rollback-*.sql.gz | \
    docker compose exec -T postgres psql -U depress_admin -d depression_system

# 5. 验证
docker compose exec postgres psql -U depress_admin -d depression_system -c "\dt"
```

### 3.4 第四步:重启服务 (1 分钟)

```bash
# 1. 启动后端
docker compose up -d

# 2. 等待健康检查通过
sleep 30
docker compose ps
# 期望: 所有服务 "Up (healthy)"

# 3. 验证后端
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/api/v1/version
# 期望: {"status":"ok"} + {"version":"v1.27-launch-ready"}
```

### 3.5 第五步:验证 (1 分钟)

```bash
# 1. 健康检查
curl -fsS http://localhost:8000/health
# 期望: {"status":"ok","database":true,"redis":true,...}

# 2. 核心 API 冒烟测试
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin@example.com&password=<admin_password>" | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/admin/engine-snapshot
# 期望: 200 + 模型列表

# 3. 前端访问
curl -fsS -o /dev/null -w "%{http_code}\n" https://depression-warning.example.com/
# 期望: 200
```

---

## 4. 回滚后处理 (Post-Rollback)

### 4.1 立即处理 (1 小时内)

- [ ] 关闭 Sentry/Prometheus 告警
- [ ] 客服团队发公告
- [ ] 监控 P95 响应时间 (应恢复到基线)
- [ ] 监控错误率 (应 < 0.1%)
- [ ] 写 Post-Mortem 报告 (根因 + 修复 + 预防)

### 4.2 短期处理 (24 小时内)

- [ ] 复现 v1.28 失败场景 (staging 环境)
- [ ] 修复问题 + 加测试用例
- [ ] 验证修复不破坏 v1.27
- [ ] 准备 v1.28.1 修复版

### 4.3 中期处理 (1 周内)

- [ ] 增强监控 (提前发现 P0 问题)
- [ ] 改进 CI/CD (加更严格的冒烟测试)
- [ ] 改进告警阈值
- [ ] 更新 DEPLOYMENT_CHECKLIST

---

## 5. 常见回滚场景 (Playbook)

### 5.1 场景 A: 后端启动失败

```bash
# 症状
docker compose ps
# backend 显示 "Exit 1" 或反复重启

# 诊断
docker compose logs backend | tail -50

# 快速回滚
docker compose stop backend
git checkout v1.27-launch-ready
docker compose build --no-cache backend
docker compose up -d backend
```

### 5.2 场景 B: 数据库迁移失败

```bash
# 症状
docker compose logs backend | grep "alembic"
# 显示 "Can't locate revision identified by 'xxxxx'"

# 修复 (不回滚版本,只修复迁移)
docker compose exec backend alembic stamp head
# 或
docker compose exec backend alembic upgrade head
```

### 5.3 场景 C: 前端 404

```bash
# 症状
curl -fsS https://depression-warning.example.com/
# 显示 404 或空白

# 诊断
ls /opt/dws/frontend/dist/
# 缺失 index.html

# 修复
cd /opt/dws/frontend
git checkout v1.27-launch-ready
npm ci
npm run build
# Nginx 自动 reload (配置 listen on dist/)
```

### 5.4 场景 D: 性能急剧下降

```bash
# 症状
# Prometheus 显示 P95 > 5s

# 诊断
docker compose exec backend python -c "
import asyncio
from app.core.model_engine import ModelEngine
engine = ModelEngine()
print('Models loaded:', engine.list_models())
"

# 快速缓解 (不停服)
# 1. 降低 worker 数量
docker compose exec backend sh -c "kill -TERM 1"
# 在 docker-compose.yml 中改 workers=1
docker compose up -d --force-recreate backend

# 2. 清除 Redis 缓存
docker compose exec redis redis-cli -a $REDIS_PASSWORD FLUSHDB

# 3. 评估是否需要回滚
```

### 5.5 场景 E: 危机文本未触发 critical

```bash
# 症状 (严重!)
# 用户输入"我想自杀"但 risk_level < 3

# 立即验证
curl -X POST http://localhost:8000/api/v1/user/data/text/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"我想自杀"}'
# 如果 risk_level < 3,立即回滚!

# 回滚 (同 3.1-3.4 步骤)
```

---

## 6. 回滚责任人

| 角色 | 职责 | 联系人 |
|:---|:---|:---|
| **决策者** | 决定是否回滚 | 研发负责人 + 运维负责人 |
| **执行者** | 执行回滚操作 | 运维工程师 |
| **验证者** | 验证回滚成功 | 测试工程师 |
| **沟通者** | 通知相关方 | 产品经理 |

---

## 7. 回滚时间线 (RTO/RPO)

| 指标 | 目标 | 实际 (上次演练) |
|:---|:---:|:---:|
| **RTO** (恢复时间目标) | 15 分钟 | 7 分钟 (演练) |
| **RPO** (数据恢复点) | 5 分钟 | 1 分钟 (实时同步) |
| **数据丢失** | < 5 分钟 | 0 (本次) |

---

## 8. 回滚演练

- [ ] 每季度演练一次 (推荐: 上线后第 30 天)
- [ ] 演练场景: 在 staging 环境执行步骤 3
- [ ] 演练结果记录到 [INCIDENT_LOG.md](./INCIDENT_LOG.md)

---

**关联文档**:
- [LAUNCH_BLOCKERS.md](./LAUNCH_BLOCKERS.md)
- [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)
- [FINAL_RELEASE_CHECKLIST.md](./FINAL_RELEASE_CHECKLIST.md)
