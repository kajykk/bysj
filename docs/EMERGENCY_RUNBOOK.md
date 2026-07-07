# 应急预案与故障处理手册 (T-302)

> 生成时间: 2026-06-28 | 对应任务: T-302 故障演练 + 应急预案 | 关联 KPI: ST-06

## 1. 故障等级定义

| 等级 | 定义 | 响应时间 | 示例 |
|------|------|----------|------|
| **P0 严重** | 系统完全不可用, 全部用户受影响 | < 5 min | DB 宕机、应用进程崩溃 |
| **P1 高** | 核心功能不可用, 多数用户受影响 | < 15 min | 模型推理全部失败、登录不可用 |
| **P2 中** | 部分功能降级, 少数用户受影响 | < 30 min | Redis 宕机(缓存降级)、PDF 生成失败 |
| **P3 低** | 性能下降, 无功能影响 | < 2 h | 响应延迟升高、缓存命中率下降 |

## 2. 故障检测

### 2.1 健康检查端点

| 端点 | 用途 | 检查项 |
|------|------|--------|
| `GET /health/live` | k8s liveness probe | 进程存活 (无 I/O) |
| `GET /health/ready` | k8s readiness probe | DB + Redis + Celery |
| `GET /health/startup` | k8s startup probe | 启动完成标志 |
| `GET /health` | 完整健康检查 | DB + Redis + Celery 详情 |

### 2.2 告警阈值

| 指标 | P2 告警 | P1 告警 | P0 告警 |
|------|---------|---------|---------|
| `/health/live` 失败率 | > 1% | > 5% | > 10% |
| `/health/ready` 失败率 | > 5% | > 10% | > 20% |
| API 错误率 (5xx) | > 1% | > 5% | > 10% |
| API P99 延迟 | > 基线 2x | > 基线 5x | > 基线 10x |
| CPU 使用率 | > 70% | > 85% | > 95% |
| 内存使用率 | > 75% | > 90% | > 95% |
| DB 连接池使用率 | > 70% | > 85% | > 95% |

## 3. 故障处理流程

### 3.1 通用响应流程

```
1. 确认故障: 检查告警 + 健康端点 + 日志
2. 定级: 根据 §1 确定故障等级
3. 通知: P0/P1 立即通知相关人员
4. 止血: 优先恢复服务 (重启/回滚/扩容)
5. 排查: 定位根因
6. 修复: 实施修复
7. 验证: 确认服务恢复
8. 复盘: 记录故障原因与改进措施
```

### 3.2 数据库故障 (P0/P1)

**症状**: `/health` 返回 `database: failed`, API 返回 500

**排查**:
```bash
# 1. 检查 DB 连接
python -c "import asyncio; from app.core.database import engine; asyncio.run(engine.dispose())"

# 2. 检查 DB 文件 (SQLite)
ls -la *.db

# 3. 检查 DB 连接池状态
curl http://localhost:8000/health | python -m json.tool
```

**修复**:
- **SQLite 文件损坏**: 从备份恢复 `cp backup.db app.db`
- **PostgreSQL 连接超时**: 检查网络/重启 DB/增加连接池
- **连接池耗尽**: 增加 `DB_POOL_SIZE` 环境变量, 重启应用

**降级**: 应用自动降级, `/health/live` 仍返回 200 (进程存活), `/health/ready` 返回 degraded

### 3.3 Redis 故障 (P2)

**症状**: `/health` 返回 `redis: failed (optional)`, 缓存命中率骤降

**影响**: 缓存降级到 `_MemoryTTLCache`, 响应延迟升高但不影响功能

**排查**:
```bash
# 1. 检查 Redis 连通性
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping

# 2. 检查 Redis 内存
redis-cli info memory | grep used_memory_human

# 3. 检查限流器 Redis 后端 (生产环境)
# 日志中搜索 "Rate limiter Redis backend is UNREACHABLE"
```

**修复**:
- **Redis 进程崩溃**: 重启 Redis `systemctl restart redis`
- **网络分区**: 检查网络路由/防火墙规则
- **内存不足**: 配置 `maxmemory-policy allkeys-lru` 或扩容

**降级**: 自动降级, 应用继续运行, 限流器降级到进程内内存存储

### 3.4 模型推理故障 (P1)

**症状**: `/api/v1/model/predict/*` 返回 503 "模型服务暂时不可用"

**排查**:
```bash
# 1. 检查模型加载状态
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/model/status

# 2. 检查模型文件
ls -la backend/models/*/
# 预期: model.json, scaler.json, feature_names.json

# 3. 检查 .sha256 校验文件
ls -la backend/models/*/*.sha256
```

**修复**:
- **模型文件缺失**: 从备份/CI artifact 恢复模型文件
- **模型文件损坏**: 验证 `.sha256` 校验, 重新下载
- **内存不足导致加载失败**: 扩容内存/减少 uvicorn workers

**降级**: 自动降级到三级回退策略:
1. BERT 模型 (首选) → 503 时降级
2. TF-IDF + LR (次选) → 自动回退
3. 启发式规则 (兜底) → 永不失败

### 3.5 PII 加密密钥故障 (P1)

**症状**: PII 字段解密失败, 日志 "PII decryption failed"

**排查**:
```bash
# 1. 检查密钥配置
echo $PII_ENCRYPTION_KEY | head -c 10
echo $PII_PREVIOUS_KEYS

# 2. 运行密钥轮换 dry-run 检查
cd backend && python scripts/rotate_pii_keys.py --dry-run
```

**修复**:
- **密钥丢失/错误**: 从 `.env` 恢复正确的密钥配置
- **密钥轮换不完整**: 执行 `python scripts/rotate_pii_keys.py --apply`
- **密钥损坏**: 从备份恢复 `.env` 文件

**降级**: 多密钥回退机制 — 当前密钥失败时自动尝试 `PII_PREVIOUS_KEYS` 中的旧密钥

### 3.6 磁盘空间不足 (P0/P1)

**症状**: 文件写入失败, 日志 "No space left on device"

**排查**:
```bash
# 1. 检查磁盘空间
df -h

# 2. 检查日志文件大小
du -sh backend/logs/

# 3. 检查上传文件大小
du -sh backend/uploads/

# 4. 检查数据库大小
du -sh backend/*.db
```

**修复**:
- **日志文件过大**: 轮转/清理旧日志 `find logs/ -mtime +30 -delete`
- **上传文件堆积**: 清理过期上传 `find uploads/ -mtime +7 -delete`
- **数据库过大**: 归档旧数据/执行 VACUUM (SQLite)

### 3.7 限流误触发 (P2/P3)

**症状**: 用户收到 429 "请求过于频繁"

**排查**:
```bash
# 1. 检查限流器状态
# 日志中搜索 "Rate limit exceeded"

# 2. 检查 Redis 限流后端连通性 (生产环境)
# 日志中搜索 "Rate limiter Redis backend"

# 3. 检查 TRUSTED_PROXIES 配置
# 若未配置, 所有请求来自 nginx 的 IP, 共享限流桶
```

**修复**:
- **TRUSTED_PROXIES 未配置**: 设置为 nginx/ALB 的 IP
- **限流阈值过低**: 调整 `default_limits` 配置
- **Redis 限流后端不可用**: 修复 Redis 连接

## 4. 回滚流程

### 4.1 应用回滚

```bash
# 1. 获取当前版本
git log --oneline -1

# 2. 回滚到上一个稳定版本
git checkout <stable-commit>
# 或使用 Docker
docker pull <image>:<previous-tag>
docker-compose up -d --no-deps backend

# 3. 验证服务恢复
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

### 4.2 数据库回滚 (Alembic)

```bash
# 1. 查看迁移历史
cd backend && alembic history

# 2. 回滚到上一个版本
alembic downgrade -1

# 3. 回滚到指定版本
alembic downgrade <revision>

# 4. 验证 schema
alembic current
```

### 4.3 模型回滚

```bash
# 1. 备份当前模型
cp -r backend/models/ backend/models.backup.$(date +%Y%m%d)

# 2. 恢复上一版本模型 (从 CI artifact 或备份)
cp -r /backups/models/v1.X/ backend/models/

# 3. 验证 .sha256 校验文件
cd backend && python -c "from app.core.model_engine import model_engine; import asyncio; asyncio.run(model_engine.preload())"

# 4. 验证推理
curl -X POST http://localhost:8000/api/v1/model/predict/tabular \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"features": {"age": 25}}'
```

## 5. 故障演练计划

### 5.1 定期演练 (每月一次)

| 场景 | 演练方式 | 预期行为 | 验证脚本 |
|------|----------|----------|----------|
| Redis 宕机 | 停止 Redis 容器 | 缓存降级, API 正常 | `test_fault_injection.py::TestRedisCacheDegradation` |
| DB 故障 | 断开 DB 网络 | 健康检查降级, API 返回 500 | `test_fault_injection.py::TestHealthCheckDegradation` |
| 模型缺失 | 重命名模型目录 | 503 + 三级回退 | `test_fault_injection.py::TestFrontendMetricsResilience` |
| PII 密钥轮换 | 切换环境变量 | 多密钥回退解密 | `test_fault_injection.py::TestPIIKeyFallback` |

### 5.2 演练执行命令

```bash
# 运行全部故障注入测试
cd backend && python -m pytest tests/test_fault_injection.py -v

# 运行特定场景
python -m pytest tests/test_fault_injection.py::TestRedisCacheDegradation -v
python -m pytest tests/test_fault_injection.py::TestHealthCheckDegradation -v
```

## 6. 相关文件

- 故障注入测试: [test_fault_injection.py](file:///e:/code/bysj/backend/tests/test_fault_injection.py)
- 容量规划: [CAPACITY_PLANNING.md](file:///e:/code/bysj/docs/CAPACITY_PLANNING.md)
- 部署指南: [DEPLOYMENT_GUIDE.md](file:///e:/code/bysj/docs/DEPLOYMENT_GUIDE.md)
- PII 密钥轮换脚本: [rotate_pii_keys.py](file:///e:/code/bysj/backend/scripts/rotate_pii_keys.py)
- 健康检查模块: [health.py](file:///e:/code/bysj/backend/app/core/health.py)
- 缓存降级模块: [cache.py](file:///e:/code/bysj/backend/app/core/cache.py)
