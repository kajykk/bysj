# 容量规划与压测报告 (T-301)

> 生成时间: 2026-06-28 | 对应任务: T-301 压力测试 + 容量规划 | 关联 KPI: ST-04

## 1. 压测基线目标

### 1.1 单实例基线 (SQLite, 无 Redis, 4C/8G)

| 端点 | P50 | P99 | 目标 RPS | 说明 |
|------|-----|-----|----------|------|
| `GET /health/live` | < 5ms | < 30ms | > 1000 | 无 I/O, 纯内存 |
| `GET /health/ready` | < 10ms | < 50ms | > 500 | 非阻塞读缓存 |
| `GET /reports/templates` | < 50ms | < 200ms | > 100 | 纯内存 |
| `GET /observability/trend` (cached) | < 30ms | < 100ms | > 200 | 5min TTL 缓存 |
| `POST /model/predict/tabular` | < 200ms | < 500ms | 12 | 异步推理 (P1 优化) |
| `POST /model/predict/text` | < 400ms | < 800ms | 10 | BERT 推理较重 |
| `POST /model/predict/fusion` | < 600ms | < 1200ms | 8 | 三模态融合最重 |
| `POST /reports/user-risk/pdf/async` | < 100ms | < 300ms | 20 | 异步队列 |

### 1.2 压测场景

| 场景 | 命令 | 目的 |
|------|------|------|
| 基线压测 | `locust --headless -u 50 -r 10 -t 60s` | 验证常规负载下的吞吐与延迟 |
| 峰值压测 | `locust --headless -u 200 -r 20 -t 120s` | 验证高并发下的降级行为 |
| 持久压测 | `locust --headless -u 50 -r 5 -t 600s` | 检测内存泄漏与连接池耗尽 |
| 推理专项 | `locust --headless -u 20 -r 5 -t 120s --tags inference` | 模型推理端点专项压测 |
| 管理员专项 | `locust --headless -u 100 -r 10 -t 60s --tags admin` | 管理端点专项压测 |

## 2. 单实例容量基线

### 2.1 资源配置

| 资源 | 最小配置 | 推荐配置 | 生产配置 |
|------|----------|----------|----------|
| CPU | 2 核 | 4 核 | 8 核+ |
| 内存 | 2 GB | 4 GB | 8 GB+ |
| 磁盘 | 20 GB SSD | 50 GB SSD | 100 GB SSD |
| 网络 | 10 Mbps | 100 Mbps | 1 Gbps+ |

### 2.2 并发容量估算

基于 uvicorn 单 worker + asyncio 事件循环:

| 负载类型 | 单实例最大并发 | 单实例最大 RPS | 瓶颈资源 |
|----------|----------------|----------------|----------|
| I/O 密集 (健康检查/报告) | 500 | 1000+ | 网络/连接池 |
| 混合负载 (含 DB 查询) | 200 | 300 | DB 连接池 |
| CPU 密集 (模型推理) | 20 | 30 | CPU (GIL + to_thread) |
| 重负载 (融合推理) | 10 | 15 | CPU + 内存 |

### 2.3 资源水位告警阈值

| 指标 | 告警阈值 | 严重阈值 | 扩容触发 |
|------|----------|----------|----------|
| CPU 使用率 | > 70% | > 85% | > 80% 持续 5min |
| 内存使用率 | > 75% | > 90% | > 85% 持续 5min |
| 磁盘使用率 | > 80% | > 95% | > 90% |
| 请求延迟 P99 | > 基线 2x | > 基线 5x | > 基线 3x 持续 2min |
| 错误率 | > 1% | > 5% | > 3% 持续 1min |
| DB 连接池使用率 | > 70% | > 90% | > 80% |

## 3. 扩缩容策略

### 3.1 水平扩容

```
扩容公式:
    所需实例数 = ceil(目标 RPS / 单实例 RPS)

示例:
    目标 500 RPS (混合负载), 单实例 300 RPS
    所需实例数 = ceil(500 / 300) = 2 实例

    目标 100 RPS (推理负载), 单实例 30 RPS
    所需实例数 = ceil(100 / 30) = 4 实例
```

### 3.2 自动扩缩容规则 (Kubernetes HPA)

```yaml
# HPA 配置示例
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70  # CPU > 70% 扩容
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 75  # 内存 > 75% 扩容
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60   # 扩容冷却 60s
      policies:
        - type: Percent
          value: 100                   # 每次最多翻倍
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300  # 缩容冷却 5min
      policies:
        - type: Percent
          value: 25                    # 每次最多缩 25%
          periodSeconds: 60
```

### 3.3 垂直扩容 (单实例)

| 场景 | 操作 | 预期效果 |
|------|------|----------|
| DB 连接池耗尽 | 增加 `DB_POOL_SIZE` (默认 10→20) | 并发查询能力提升 2x |
| 模型推理慢 | 增加 uvicorn workers (`--workers 4`) | CPU 利用率提升, 吞吐提升 |
| Redis 缓存命中率低 | 增加 `CACHE_TTL` (默认 300s→600s) | DB 负载降低 |
| PDF 生成排队 | 增加 `PDF_MAX_WORKERS` (默认 2→4) | PDF 吞吐提升 2x |

## 4. 容量瓶颈分析

### 4.1 已知瓶颈

| 瓶颈点 | 原因 | 缓解措施 | 状态 |
|--------|------|----------|------|
| SQLite 写锁 | 单写者锁, 高并发写受限 | 迁移至 PostgreSQL | 待迁移 |
| 模型推理 GIL | Python GIL 限制 CPU 并行 | `asyncio.to_thread` + 多 worker | P1 已优化 |
| BERT 文本推理 | CPU 推理慢 (~400ms) | 缓存相同文本结果 / GPU 加速 | 监控中 |
| PDF 生成线程池 | 默认 2 worker | 可配置 `PDF_MAX_WORKERS` | P1 已优化 |

### 4.2 容量规划公式

```
总容量 = min(CPU容量, 内存容量, DB容量, 网络容量)

CPU容量 = 实例数 × 单实例RPS × (1 - CPU预留)
DB容量 = DB连接池总数 / 单请求平均连接占用时间
内存容量 = (总内存 - 系统预留 - 模型加载内存) / 单请求平均内存

示例 (4 实例, 4C/8G):
    CPU容量 = 4 × 300 × 0.8 = 960 RPS
    DB容量 = (4 × 20) / 0.1s = 800 RPS
    内存容量 = (8GB - 2GB - 2GB) / 10MB = 400 RPS
    总容量 = min(960, 800, 400) = 400 RPS
```

## 5. 压测执行检查清单

执行压测前确认:

- [ ] 后端已启动且 DB 已 seed (`ENABLE_SEED=true`)
- [ ] Redis 已连接 (可选, 用于缓存命中率验证)
- [ ] 模型已预加载 (`/api/v1/model/status` 返回 loaded)
- [ ] Locust 已安装 (`pip install locust`)
- [ ] 测试账号已配置 (`LOCUST_ADMIN_USER` / `LOCUST_USER_USER` 环境变量)
- [ ] 监控已启用 (Prometheus / Grafana 用于观察资源水位)
- [ ] 压测时间避开业务高峰 (如为生产环境)

执行后记录:

- [ ] 记录各端点 P50/P99/P999 延迟
- [ ] 记录最大 RPS 与错误率
- [ ] 记录 CPU/内存/DB 连接池峰值
- [ ] 对比基线目标, 标记未达标项
- [ ] 更新本文档的基线数据

## 6. 相关文件

- 压测脚本: [locustfile.py](file:///e:/code/bysj/backend/load_tests/locustfile.py)
- 系统优化计划: [SYSTEM_OPTIMIZATION_PLAN.md](file:///e:/code/bysj/docs/SYSTEM_OPTIMIZATION_PLAN.md)
- 部署指南: [DEPLOYMENT_GUIDE.md](file:///e:/code/bysj/docs/DEPLOYMENT_GUIDE.md)
