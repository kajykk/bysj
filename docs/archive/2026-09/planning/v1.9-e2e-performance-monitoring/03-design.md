# v1.9 设计文档: E2E、性能与监控详细设计

> **迭代名称**: v1.9-e2e-performance-monitoring
> **日期**: 2026-04-29
> **版本**: Round 3 Locked

---

## 1. E2E 测试设计

### 1.1 Page Objects 更新

```typescript
// tests/e2e/pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/login');
  }

  async login(username: string, password: string) {
    await this.page.fill('[data-testid="username"]', username);
    await this.page.fill('[data-testid="password"]', password);
    await this.page.click('[data-testid="login-button"]');
  }

  async expectLoginSuccess() {
    await expect(this.page).toHaveURL('/dashboard');
  }

  async expectLoginError(message: string) {
    await expect(this.page.locator('[data-testid="error-message"]')).toHaveText(message);
  }
}
```

### 1.2 测试用例设计

| 用例 ID | 场景 | 步骤 | 预期结果 | 优先级 |
|---------|------|------|----------|--------|
| E2E-001 | 用户登录成功 | 1. 访问登录页<br>2. 输入正确凭据<br>3. 点击登录 | 跳转仪表盘 | P0 |
| E2E-002 | 用户登录失败 | 1. 访问登录页<br>2. 输入错误密码<br>3. 点击登录 | 显示错误信息 | P0 |
| E2E-003 | 抑郁评估流程 | 1. 登录<br>2. 进入评估<br>3. 填写问卷<br>4. 提交 | 显示评估结果 | P0 |
| E2E-004 | 预警查看 | 1. 登录<br>2. 进入预警中心<br>3. 查看预警列表 | 列表加载成功 | P1 |
| E2E-005 | 数据导出 | 1. 登录<br>2. 进入数据管理<br>3. 点击导出 | 下载文件成功 | P1 |

### 1.3 测试数据管理

```json
// tests/e2e/fixtures/users.json
{
  "validUser": {
    "username": "test_user",
    "password": "Test@123456"
  },
  "adminUser": {
    "username": "admin",
    "password": "Admin@123456"
  },
  "invalidUser": {
    "username": "invalid",
    "password": "wrong"
  }
}
```

---

## 2. 性能优化设计

### 2.1 Lighthouse CI 配置

```json
// lighthouserc.js
module.exports = {
  ci: {
    collect: {
      url: ['http://localhost:4173/login', 'http://localhost:4173/dashboard'],
      numberOfRuns: 3,
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.8 }],
        'categories:accessibility': ['error', { minScore: 0.9 }],
        'categories:best-practices': ['warn', { minScore: 0.9 }],
        'categories:seo': ['warn', { minScore: 0.9 }],
        'first-contentful-paint': ['warn', { maxNumericValue: 1800 }],
        'largest-contentful-paint': ['warn', { maxNumericValue: 2500 }],
        'cumulative-layout-shift': ['warn', { maxNumericValue: 0.1 }],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
```

### 2.2 首屏加载优化策略

| 优化项 | 实施方案 | 预期收益 |
|--------|----------|----------|
| 路由懒加载 | `() => import('./views/xxx.vue')` | 减少初始 bundle |
| 组件异步加载 | `defineAsyncComponent` | 按需加载 |
| 图片优化 | WebP + lazy loading | 减少 LCP |
| CDN 加速 | 静态资源上 CDN | 减少 TTFB |
| 预加载关键资源 | `<link rel="preload">` | 加速 FCP |

### 2.3 Chunk 分割策略

```javascript
// vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-ui': ['element-plus'],
          'vendor-charts': ['echarts', 'vue-echarts'],
          'vendor-utils': ['axios', 'dayjs'],
        },
      },
    },
    chunkSizeWarningLimit: 500,
  },
});
```

---

## 3. 监控设计

### 3.1 Sentry 前端配置

```typescript
// main.ts
import * as Sentry from '@sentry/vue';

Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE,
  release: import.meta.env.VITE_APP_VERSION,
  integrations: [
    Sentry.browserTracingIntegration(),
    Sentry.replayIntegration(),
  ],
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0.01,
  replaysOnErrorSampleRate: 1.0,
});
```

### 3.2 Web Vitals 采集

```typescript
// utils/web-vitals.ts
import { getCLS, getFID, getFCP, getLCP, getTTFB } from 'web-vitals';

export function initWebVitals() {
  getCLS(sendToAnalytics);
  getFID(sendToAnalytics);
  getFCP(sendToAnalytics);
  getLCP(sendToAnalytics);
  getTTFB(sendToAnalytics);
}

function sendToAnalytics(metric: Metric) {
  // 发送到 Sentry 或自定义后端
  Sentry.captureMessage(`Web Vital: ${metric.name}`, {
    level: 'info',
    extra: {
      name: metric.name,
      value: metric.value,
      rating: metric.rating,
    },
  });
}
```

### 3.3 后端监控中间件

```python
# app/middleware/monitoring.py
import time
from fastapi import Request
import sentry_sdk

async def monitoring_middleware(request: Request, call_next):
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # 记录请求指标
        duration = time.time() - start_time
        if duration > 2.0:  # 慢请求告警
            sentry_sdk.capture_message(
                f"Slow request: {request.url.path} took {duration:.2f}s",
                level="warning"
            )
        
        return response
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise
```

---

## 4. 告警设计

### 4.1 告警规则配置

```yaml
# alerting-rules.yml
groups:
  - name: backend-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          
      - alert: SlowAPI
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 10m
        labels:
          severity: warning
          
  - name: frontend-alerts
    rules:
      - alert: HighJSErrorRate
        expr: rate(js_errors_total[5m]) > 0.5
        for: 5m
        labels:
          severity: warning
```

### 4.2 通知渠道

| 渠道 | 用途 | 配置 |
|------|------|------|
| Slack | 实时告警 | Webhook URL |
| 邮件 | 日报/周报 | SMTP 配置 |
| Sentry | 错误详情 | DSN 配置 |

---

## 5. 测试策略

### 5.1 E2E 测试标记

| 标记 | 含义 | 执行场景 |
|------|------|----------|
| @smoke | 核心流程 | CI PR |
| @regression | 回归测试 | CI Nightly |
| @flaky | 不稳定测试 | 手动 |
| @slow | 慢测试 | Nightly |

### 5.2 性能测试基准

| 页面 | FCP | LCP | CLS | 测试工具 |
|------|-----|-----|-----|----------|
| 登录页 | < 1.5s | < 2.0s | < 0.05 | Lighthouse |
| 仪表盘 | < 1.8s | < 2.5s | < 0.1 | Lighthouse |
| 评估页 | < 2.0s | < 3.0s | < 0.1 | Lighthouse |

---

## 6. 部署设计

### 6.1 环境配置

| 环境 | Sentry | Web Vitals | Lighthouse CI |
|------|--------|------------|---------------|
| Development | 启用 | 启用 | 手动 |
| Staging | 启用 | 启用 | CI |
| Production | 启用 | 启用 | 定时 |

### 6.2 配置管理

```bash
# .env.development
VITE_SENTRY_DSN=https://xxx@o0.ingest.sentry.io/0
VITE_APP_VERSION=1.9.0

# .env.production
VITE_SENTRY_DSN=https://xxx@o0.ingest.sentry.io/0
VITE_APP_VERSION=1.9.0
```
