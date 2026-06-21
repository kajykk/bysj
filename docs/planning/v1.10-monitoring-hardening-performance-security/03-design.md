# v1.10 设计文档: 监控硬化、性能优化与安全加固

> **迭代名称**: v1.10-monitoring-hardening-performance-security
> **日期**: 2026-04-29
> **版本**: Round 3 Locked
> **状态**: Locked

---

## 1. 监控设计

### 1.1 Sentry 后端集成设计

```python
# backend/app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

def init_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logger.warning("SENTRY_DSN not set, skipping Sentry initialization")
        return
    
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("ENV", "development"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,  # 隐私合规，默认不发送 PII
        integrations=[
            FastApiIntegration(
                transaction_style="endpoint",
                failed_request_status_codes={403, *range(500, 599)},
            ),
            SqlalchemyIntegration(),
        ],
        before_send=filter_sensitive_events,
    )

# 捕获 FastAPI RequestValidationError (默认不触发 Sentry)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    sentry_sdk.capture_exception(exc)
    return await default_validation_exception_handler(request, exc)
```

### 1.2 告警规则引擎设计

```python
# backend/app/monitoring/alerting.py
class AlertRule:
    name: str
    condition: Callable[[MetricsSnapshot], bool]
    severity: str  # P0, P1, P2
    cooldown_minutes: int
    
class AlertingEngine:
    def evaluate(self, metrics: MetricsSnapshot) -> List[AlertEvent]:
        triggered = []
        for rule in self.rules:
            if rule.condition(metrics) and not self._in_cooldown(rule):
                event = self._create_alert(rule, metrics)
                triggered.append(event)
                self._send_notification(rule, event)  # 发送 Webhook 通知
        return triggered
    
    def _send_notification(self, rule: AlertRule, event: AlertEvent):
        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        if not webhook_url:
            return
        
        payload = {
            "rule": rule.name,
            "severity": rule.severity,
            "message": event.message,
            "timestamp": event.created_at.isoformat(),
        }
        
        # 指数退避重试 (最多 3 次)
        for attempt in range(3):
            try:
                resp = requests.post(webhook_url, json=payload, timeout=5)
                if resp.status_code < 500:
                    return  # 成功或 4xx 错误不再重试
            except Exception as e:
                logger.warning(f"Alert webhook attempt {attempt + 1} failed: {e}")
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
        
        logger.error(f"Failed to send alert notification after 3 attempts")
```

### 1.3 Web Vitals 存储设计

```sql
-- web_vitals 表
CREATE TABLE web_vitals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_path VARCHAR(255) NOT NULL,
    metric_name VARCHAR(20) NOT NULL CHECK (metric_name IN ('CLS', 'FID', 'FCP', 'LCP', 'TTFB')),
    value FLOAT NOT NULL,
    rating VARCHAR(20) NOT NULL CHECK (rating IN ('good', 'needs-improvement', 'poor')),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_web_vitals_page ON web_vitals(page_path);
CREATE INDEX idx_web_vitals_metric ON web_vitals(metric_name);
CREATE INDEX idx_web_vitals_created ON web_vitals(created_at);
```

---

## 2. 性能设计

### 2.1 Service Worker 缓存策略

```typescript
// frontend/src/service-worker.ts
const BUILD_NUMBER = '__BUILD_NUMBER__';  // 构建时注入

const CACHE_STRATEGIES = {
  static: new CacheFirst({
    cacheName: `static-${BUILD_NUMBER}`,
    plugins: [
      new ExpirationPlugin({ maxAgeSeconds: 7 * 24 * 60 * 60 })
    ]
  }),
  api: new NetworkFirst({
    cacheName: `api-${BUILD_NUMBER}`,
    plugins: [
      new ExpirationPlugin({ maxAgeSeconds: 5 * 60 })
    ]
  }),
  images: new StaleWhileRevalidate({
    cacheName: `images-${BUILD_NUMBER}`,
    plugins: [
      new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 24 * 60 * 60 })
    ]
  })
};

// 激活时清理旧版本缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.endsWith(BUILD_NUMBER) === false)
          .map((name) => caches.delete(name))
      );
    })
  );
});

// SW 更新提示 (通过 workbox-window)
// frontend/src/main.ts
import { Workbox } from 'workbox-window';

const wb = new Workbox('/service-worker.js');

wb.addEventListener('waiting', () => {
  // 显示 "更新可用" Toast
  showUpdateToast({
    message: '新版本可用，点击刷新更新',
    onConfirm: () => wb.messageSkipWaiting(),
  });
});

wb.addEventListener('controlling', () => {
  window.location.reload();
});

wb.register();
```

### 2.2 图片优化设计

```typescript
// 图片组件伪代码
interface OptimizedImageProps {
  src: string;
  alt: string;
  width?: number;
  height?: number;
  lazy?: boolean;
}

// 自动 WebP 转换 + srcset 生成
function generateSrcSet(src: string, widths: number[]): string {
  return widths.map(w => `${convertToWebP(src, w)} ${w}w`).join(', ');
}
```

---

## 3. 安全设计

### 3.1 安全中间件设计

```python
# backend/app/middleware/security.py
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # HSTS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # CSP
        response.headers["Content-Security-Policy"] = self._build_csp()
        
        # 其他安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        
        return response
    
    def __init__(self, app, csp_report_only: bool = True):
        super().__init__(app)
        self.csp_report_only = csp_report_only
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 生成随机 nonce
        nonce = secrets.token_urlsafe(16)
        
        # HSTS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # CSP (Report-Only or Enforce)
        csp_header = "Content-Security-Policy-Report-Only" if self.csp_report_only else "Content-Security-Policy"
        response.headers[csp_header] = self._build_csp(nonce)
        
        # 将 nonce 注入 HTML
        self._inject_nonce_to_html(response, nonce)
        
        # 其他安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        
        return response
    
    def _build_csp(self, nonce: str) -> str:
        return "; ".join([
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "connect-src 'self' https://sentry.io",
            "font-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "report-uri /api/csp-report",
        ])
    
    def _inject_nonce_to_html(self, response: Response, nonce: str):
        """将 nonce 注入到 HTML 响应的 meta 标签中"""
        if response.headers.get("content-type", "").startswith("text/html"):
            nonce_meta = f'<meta name="csp-nonce" content="{nonce}">'
            response.body = response.body.replace(b"<head>", f"<head>{nonce_meta}".encode())
```

### 3.2 XSS 防护设计

```python
# 输入净化中间件
import bleach

class InputSanitizationMiddleware(BaseHTTPMiddleware):
    ALLOWED_TAGS = []
    ALLOWED_ATTRIBUTES = {}
    
    async def dispatch(self, request: Request, call_next):
        # 对 JSON body 中的字符串字段进行净化
        if request.headers.get("content-type") == "application/json":
            body = await request.json()
            sanitized = self._sanitize_dict(body)
            # 替换 request.state 中的 body
            request.state.sanitized_body = sanitized
        
        return await call_next(request)
```

---

## 4. 可访问性设计

### 4.1 ARIA 规范

| 组件类型 | 必需 ARIA 属性 |
|---|---|
| Button (图标) | `aria-label` |
| Modal | `role="dialog"`, `aria-modal="true"` |
| Toast | `role="alert"`, `aria-live="polite"` |
| Navigation | `role="navigation"`, `aria-label` |
| Form Input | `aria-describedby` (关联错误提示) |

### 4.2 键盘导航规范

| 快捷键 | 功能 | 冲突检查 |
|---|---|---|
| Tab / Shift+Tab | 焦点移动 | 无冲突 |
| Enter / Space | 激活按钮/链接 | 无冲突 |
| Escape | 关闭 Modal/Toast | 无冲突 |
| Alt+Shift+1 | 跳转到主内容区 | 避开 Alt+1 (Chrome 收藏夹) |
| Alt+Shift+M | 打开消息通知 | 避开常用快捷键 |

### 4.3 分布式追踪规范

| 头名称 | 生成位置 | 传递方式 |
|---|---|---|
| X-Request-ID | 前端/网关 | 所有请求携带 |
| sentry-trace | Sentry SDK | 自动传播 |
| baggage | Sentry SDK | 自动传播 |
