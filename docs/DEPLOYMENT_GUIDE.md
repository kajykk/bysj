# v1.5 部署指南

## 概述

本文档描述 v1.5 版本的部署流程，包含环境准备、服务配置、灰度发布策略和监控告警设置。

**版本**: v1.5.0  
**更新日期**: 2024-01-15

---

## 环境要求

### 后端

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.9+ | 运行环境 |
| FastAPI | 0.104+ | Web 框架 |
| SQLAlchemy | 2.0+ | ORM |
| scikit-learn | 1.3.2 | 机器学习 |
| PyTorch | 2.0+ | 深度学习 (可选) |
| PostgreSQL | 14+ | 数据库 |
| Redis | 6+ | 缓存 |

### 前端

| 依赖 | 版本 | 说明 |
|------|------|------|
| Node.js | 18+ | 运行环境 |
| Vue | 3.3+ | 框架 |
| Element Plus | 2.4+ | UI 组件库 |
| ECharts | 5.4+ | 图表库 |

---

## 部署步骤

### 1. 数据库迁移

```bash
# 创建新表
alembic revision --autogenerate -m "add monitoring and canary tables"
alembic upgrade head
```

**新增表结构**:

- `monitoring_logs` - 监控指标日志
- `canary_records` - 灰度发布记录
- `validation_results` - 离线验证结果
- `drift_alerts` - 漂移告警
- `export_tasks` - 导出任务

### 2. 后端服务部署

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库连接、Redis 等

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**关键配置项**:

```env
# 监控配置
MONITORING_ENABLED=true
METRICS_RETENTION_DAYS=30

# 灰度发布配置
CANARY_DEFAULT_TRAFFIC=5
CANARY_SUCCESS_THRESHOLD=0.98
CANARY_AUTO_ROLLBACK=true

# 报告导出配置
REPORTS_STORAGE_PATH=/data/reports
MAX_EXPORT_FILE_SIZE=50MB
```

### 3. 前端构建部署

```bash
# 安装依赖
npm install

# 构建生产版本
npm run build

# 部署到 Nginx
cp -r dist/* /var/www/html/
```

**Nginx 配置示例**:

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        root /var/www/html;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 灰度发布流程

### 标准发布流程

```
1. 部署基线版本 (100% 流量)
   ↓
2. 部署灰度版本 (5% 流量)
   ↓
3. 监控指标 (成功率 > 98%)
   ↓
4. 逐步扩量 (5% → 25% → 50% → 100%)
   ↓
5. 完成发布 / 触发回滚
```

### API 调用示例

```bash
# 1. 创建灰度发布
curl -X POST http://api.example.com/api/v1/canary/deployments \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "baseline_version": "v1.0.0",
    "canary_version": "v2.0.0",
    "traffic_percent": 5,
    "auto_rollback": true
  }'

# 2. 查询灰度状态
curl http://api.example.com/api/v1/canary/deployments/deploy_12345 \
  -H "Authorization: Bearer <token>"

# 3. 扩量到 25%
curl -X PATCH http://api.example.com/api/v1/canary/deployments/deploy_12345 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"traffic_percent": 25}'

# 4. 完成发布（全量）
curl -X POST http://api.example.com/api/v1/canary/deployments/deploy_12345/promote \
  -H "Authorization: Bearer <token>"

# 5. 或执行回滚
curl -X POST http://api.example.com/api/v1/canary/deployments/deploy_12345/rollback \
  -H "Authorization: Bearer <token>"
```

---

## 监控告警配置

### 关键指标阈值

| 指标 | 警告阈值 | 严重阈值 | 处理方式 |
|------|----------|----------|----------|
| 模型成功率 | < 98% | < 95% | 自动回滚 |
| 回退率 | > 5% | > 10% | 告警通知 |
| P99 延迟 | > 300ms | > 500ms | 扩容/优化 |
| 错误率 | > 2% | > 5% | 自动回滚 |

### 告警通知配置

```python
# config/alerts.py
ALERT_CHANNELS = {
    "email": {
        "enabled": True,
        "recipients": ["ops@example.com"],
    },
    "webhook": {
        "enabled": True,
        "url": "https://hooks.slack.com/services/xxx",
    },
    "sms": {
        "enabled": False,
        "phone_numbers": [],
    },
}
```

---

## 性能基准

### 负载测试指标

| 场景 | 并发用户 | 平均延迟 | P99 延迟 | 成功率 |
|------|----------|----------|----------|--------|
| 风险评估 | 100 | < 150ms | < 300ms | > 99% |
| 监控查询 | 50 | < 50ms | < 100ms | > 99.9% |
| 报告导出 | 10 | < 5s | < 10s | > 98% |

### 资源使用

| 组件 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 后端服务 | 2 核 | 4GB | 20GB |
| 数据库 | 2 核 | 8GB | 100GB |
| Redis | 1 核 | 2GB | 10GB |

---

## 故障排查

### 常见问题

#### 1. 灰度发布失败

**症状**: 灰度版本成功率低于阈值

**排查步骤**:
1. 检查 `/monitoring/metrics` 查看实时指标
2. 查看 `canary_records` 表中的错误日志
3. 检查模型版本是否正确加载

**解决方案**:
```bash
# 手动回滚
curl -X POST http://api.example.com/api/v1/canary/deployments/{id}/rollback \
  -H "Authorization: Bearer <token>"
```

#### 2. 报告导出超时

**症状**: 导出任务状态长时间为 processing

**排查步骤**:
1. 检查 `export_tasks` 表中的任务状态
2. 查看后端服务日志
3. 检查磁盘空间

**解决方案**:
- 增加导出服务的超时时间
- 清理历史导出文件
- 优化查询 SQL

#### 3. 前端性能指标异常

**症状**: LCP > 2.5s 或 CLS > 0.1

**排查步骤**:
1. 使用 Lighthouse 进行性能审计
2. 检查资源加载时间
3. 分析 JavaScript 执行时间

**解决方案**:
- 启用路由懒加载
- 优化图片加载策略
- 减少主线程阻塞

---

## 回滚策略

### 自动回滚触发条件

1. 灰度版本成功率 < 98% (持续 5 分钟)
2. 错误率 > 5% (持续 2 分钟)
3. P99 延迟 > 500ms (持续 5 分钟)

### 手动回滚命令

```bash
# 回滚灰度发布
curl -X POST http://api.example.com/api/v1/canary/deployments/{id}/rollback \
  -H "Authorization: Bearer <token>"

# 回滚数据库迁移
alembic downgrade -1
```

---

## 安全注意事项

1. **API 密钥管理**: 使用环境变量存储敏感配置
2. **访问控制**: 灰度发布和报告导出接口需要管理员权限
3. **数据备份**: 定期备份 `monitoring_logs` 和 `canary_records` 表
4. **日志审计**: 启用操作日志记录，保留 90 天

---

## 附录

### 相关文档

- [API 文档](./api/v1.5-api-documentation.md)
- [CHANGELOG](../CHANGELOG.md)
- [测试计划](./planning/v1.5-performance-observability-insights/05-test-plan.md)

### 联系方式

- 技术支持: tech@example.com
- 运维值班: ops@example.com
