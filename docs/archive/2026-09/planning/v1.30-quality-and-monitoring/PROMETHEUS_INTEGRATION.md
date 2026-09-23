# Prometheus Integration Guide (v1.30)

> **版本**: v1.30-quality-monitoring
> **创建日期**: 2026-06-02

---

## 1. 端点说明

### 1.1 `/api/v1/metrics`

- **方法**: `GET`
- **认证**: 不需要 (`@limiter.exempt`)
- **Content-Type**: `text/plain; version=0.0.4; charset=utf-8`
- **格式**: Prometheus exposition format
- **用途**: 供 Prometheus 抓取系统指标

### 1.2 抓取配置示例

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'dws-backend'
    scrape_interval: 15s
    static_configs:
      - targets: ['dws-backend:8000']
    metrics_path: /api/v1/metrics
```

---

## 2. 可用指标

### 2.1 HTTP 请求指标

| 指标 | 类型 | 标签 | 说明 |
|:---|:---|:---|:---|
| `http_requests_total` | Counter | method, path, status | HTTP 请求累计计数 |
| `http_request_duration_seconds` | Histogram | method, path | 请求耗时分布 |

**Path 归一化**: 使用 FastAPI 路由模板,避免高基数 (例如 `/api/v1/user/data/{data_id}` 而非 `/api/v1/user/data/42`)

### 2.2 模型推理指标

| 指标 | 类型 | 标签 | 说明 |
|:---|:---|:---|:---|
| `model_inference_total` | Counter | model_name, status | 推理调用累计 |
| `model_inference_duration_seconds` | Histogram | model_name | 推理耗时分布 |

### 2.3 WebSocket 指标

| 指标 | 类型 | 标签 | 说明 |
|:---|:---|:---|:---|
| `websocket_connections_active` | Gauge | - | 当前活跃 WebSocket 连接数 |
| `websocket_messages_total` | Counter | direction, type | 消息累计 (预留) |

### 2.4 数据库指标

| 指标 | 类型 | 标签 | 说明 |
|:---|:---|:---|:---|
| `db_pool_size` | Gauge | - | SQLAlchemy 连接池大小 |

### 2.5 应用信息

| 指标 | 类型 | 标签 | 说明 |
|:---|:---|:---|:---|
| `app_info` | Info | version, name | 应用元信息 |

---

## 3. 示例输出

```text
# HELP http_requests_total Total HTTP requests processed, labeled by method, path, status.
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health",status="200"} 42
http_requests_total{method="POST",path="/api/v1/auth/login",status="200"} 15
http_requests_total{method="POST",path="/api/v1/auth/login",status="401"} 3

# HELP http_request_duration_seconds HTTP request duration in seconds.
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.005",method="GET",path="/health"} 38
http_request_duration_seconds_bucket{le="0.01",method="GET",path="/health"} 41
http_request_duration_seconds_bucket{le="+Inf",method="GET",path="/health"} 42
http_request_duration_seconds_sum{method="GET",path="/health"} 0.234
http_request_duration_seconds_count{method="GET",path="/health"} 42

# HELP websocket_connections_active Current number of active WebSocket connections.
# TYPE websocket_connections_active gauge
websocket_connections_active 5

# HELP app Application information.
# TYPE app info
app_info{version="v1.30-quality-monitoring",name="depression-warning-system"} 1
```

---

## 4. Grafana Dashboard 建议

### 4.1 HTTP 性能面板

- **请求速率 (RPS)**: `sum(rate(http_requests_total[5m])) by (path)`
- **P50 延迟**: `histogram_quantile(0.5, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path))`
- **P99 延迟**: `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path))`
- **错误率**: `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`

### 4.2 模型性能面板

- **推理速率**: `sum(rate(model_inference_total[5m])) by (model_name)`
- **P95 推理延迟**: `histogram_quantile(0.95, sum(rate(model_inference_duration_seconds_bucket[5m])) by (le, model_name))`
- **模型失败率**: `sum(rate(model_inference_total{status="error"}[5m])) by (model_name) / sum(rate(model_inference_total[5m])) by (model_name)`

### 4.3 WebSocket 面板

- **活跃连接数**: `websocket_connections_active`
- **连接速率**: `rate(websocket_connections_active[5m])`

### 4.4 数据库面板

- **连接池利用率**: `db_pool_size / <max_pool_size>`

---

## 5. 告警规则建议

```yaml
groups:
  - name: dws-backend
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m])) > 0.05
        for: 5m
        annotations:
          summary: "5xx 错误率超过 5%"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le, path)
          ) > 1.0
        for: 5m
        annotations:
          summary: "P99 延迟超过 1 秒"

      - alert: ModelInferenceFailure
        expr: |
          sum(rate(model_inference_total{status="error"}[5m])) by (model_name)
          / sum(rate(model_inference_total[5m])) by (model_name) > 0.10
        for: 5m
        annotations:
          summary: "模型 {{ $labels.model_name }} 失败率超过 10%"
```

---

## 6. 实现细节

### 6.1 零依赖

v1.30 使用自研 `app/core/metrics.py`,无外部依赖 (无需 `prometheus_client`):

- 优点: 不增加包体积, 启动更快, 无版本冲突
- 兼容: 输出格式与 Prometheus exposition format 一致

### 6.2 路径归一化

通过 `request.scope['route'].path` 获取 FastAPI 路由模板,避免高基数:

- ✅ 计入: `/api/v1/user/data/{data_id}`
- ❌ 不计入: `/api/v1/user/data/42`

### 6.3 自激保护

`/api/v1/metrics` 端点自身不计入 `http_requests_total`,避免无限递归。

### 6.4 优雅降级

- 指标中间件异常被捕获,不影响主请求
- 指标收集失败时, /metrics 端点仍返回 (空内容)

---

## 7. 测试覆盖

- `tests/api/test_metrics.py` (9 个测试)
  - 端点可访问性
  - 格式合规
  - Counter / Histogram 行为
  - WebSocket gauge 同步
  - 自激保护
  - Label 校验
  - Render 一致性

---

## 8. 后续优化 (P2)

- [ ] 添加 pprof 性能分析端点
- [ ] 添加 OpenTelemetry tracing
- [ ] 指标采集与采样率配置
- [ ] 自定义业务指标 (用户注册数、风险预测分布等)
- [ ] 集成 Sentry 性能监控

---

> **文档版本**: v1.0
> **最后更新**: 2026-06-02
