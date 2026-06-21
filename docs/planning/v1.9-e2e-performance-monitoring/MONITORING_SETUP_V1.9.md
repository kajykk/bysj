# v1.9 监控体系配置报告 (MONITORING_SETUP_V1.9.md)

> **迭代名称**: v1.9-e2e-performance-monitoring
> **日期**: 2026-04-29
> **状态**: Phase 4 完成

---

## 1. Sentry 错误监控

### 1.1 前端配置

| 配置项 | 状态 | 说明 |
|--------|------|------|
| SDK | 已安装 | `@sentry/vue ^10.50.0` |
| 初始化 | 已配置 | `src/plugins/sentry.ts` |
| DSN | 环境变量 | `VITE_SENTRY_DSN` |
| BrowserTracing | 已启用 | 路由追踪 |
| Replay | 已启用 | 会话回放 |
| 采样率 | 可配置 | `VITE_SENTRY_TRACES_SAMPLE_RATE` |

### 1.2 前端 API

```typescript
// 初始化
initSentry(app, router)

// 捕获异常
captureException(error, context)

// 发送消息
captureMessage(message, level)
```

### 1.3 后端配置

| 配置项 | 状态 | 说明 |
|--------|------|------|
| SDK | 待安装 | `sentry-sdk[fastapi]` |
| 初始化 | 待配置 | FastAPI 集成 |
| DSN | 环境变量 | `SENTRY_DSN` |

---

## 2. Web Vitals 性能监控

### 2.1 前端采集

| 指标 | 采集方式 | 目标 |
|------|----------|------|
| CLS | `getCLS()` | < 0.1 |
| FID | `getFID()` | < 100ms |
| FCP | `getFCP()` | < 1.8s |
| LCP | `getLCP()` | < 2.5s |
| TTFB | `getTTFB()` | < 600ms |

### 2.2 数据上报

- **Sentry**: 作为 breadcrumb 发送
- **后端**: `/api/analytics/web-vitals` 端点
- **开发环境**: Console 输出

### 2.3 采集代码

```typescript
// 初始化
initWebVitals()

// 获取汇总
const summary = await getWebVitalsSummary()
```

---

## 3. 后端性能监控

### 3.1 中间件配置

| 功能 | 状态 | 说明 |
|------|------|------|
| 请求耗时 | 已配置 | `X-Response-Time` 响应头 |
| 慢请求告警 | 已配置 | 阈值: 2s |
| 错误日志 | 已配置 | 自动捕获异常 |

### 3.2 使用方式

```python
from app.middleware.monitoring import MonitoringMiddleware

app.add_middleware(
    MonitoringMiddleware,
    slow_request_threshold=2.0
)
```

---

## 4. 分析 API

### 4.1 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/analytics/web-vitals` | POST | 接收 Web Vitals |
| `/api/analytics/performance` | POST | 接收性能指标 |
| `/api/analytics/health` | GET | 健康检查 |

### 4.2 数据模型

```python
class WebVitalsPayload(BaseModel):
    name: str      # CLS, FID, FCP, LCP, TTFB
    value: float
    rating: str    # good, needs-improvement, poor
    delta: float | None
    url: str | None
    user_agent: str | None
```

---

## 5. 环境变量配置

### 5.1 前端

```bash
# .env.production
VITE_SENTRY_DSN=https://xxx@o0.ingest.sentry.io/0
VITE_SENTRY_TRACES_SAMPLE_RATE=0.1
VITE_SENTRY_REPLAYS_SAMPLE_RATE=0.1
VITE_APP_VERSION=1.9.0
```

### 5.2 后端

```bash
# .env
SENTRY_DSN=https://xxx@o0.ingest.sentry.io/0
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=1.9.0
```

---

## 6. 告警规则 (建议)

| 条件 | 级别 | 通知方式 |
|------|------|----------|
| 500 错误 > 10/小时 | P0 | 邮件 + Slack |
| 登录失败率 > 5% | P1 | Slack |
| API 响应时间 > 2s | P1 | Slack |
| JS Error > 50/小时 | P2 | 邮件 |
| LCP > 2.5s | P2 | Slack |

---

## 7. 签名

- **配置完成**: 2026-04-29
- **验证方式**: 代码审查
- **待完成**: Sentry 后端 SDK 安装、告警规则配置
- **下一步**: Phase 5 CI/CD 集成
