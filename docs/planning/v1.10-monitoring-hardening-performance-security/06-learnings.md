# v1.10 经验总结 (Learnings)

> **迭代名称**: v1.10-monitoring-hardening-performance-security
> **日期**: 2026-04-29

---

## Round 1 经验

### 发现的问题
1. **CSP `script-src 'unsafe-inline'`** - 削弱 XSS 防护，需要 nonce/hash 机制逐步移除
2. **Sentry DSN 缺失时的回退策略** - 需要明确 graceful degradation
3. **Service Worker 缓存清理策略** - 需要版本号机制和激活时清理
4. **告警规则无通知渠道实现** - 只有日志记录，缺少 Webhook/Email
5. **图片 WebP 转换的降级方案** - 旧浏览器不支持 WebP，需要 `<picture>` 标签
6. **A11Y 键盘导航快捷键冲突** - 可能与浏览器快捷键冲突

### 设计决策
- 使用 Sentry FastAPI Integration 官方推荐配置
- Service Worker 采用 Workbox 策略模式
- 安全头使用集中式中间件管理

### 风险与缓解
- **风险**: CSP 升级可能阻断现有功能 → **缓解**: 先用 Report-Only 模式
- **风险**: Service Worker 缓存导致旧版本长期存在 → **缓解**: 版本号 + 激活清理

---

## Round 2 经验

### 发现的问题
1. CSP nonce 需要传递到前端 (通过 meta 标签)
2. Service Worker 更新提示 UX 需要用户确认
3. Webhook 告警失败需要重试机制

### 设计决策
- CSP nonce 通过 `<meta name="csp-nonce">` 传递
- SW 更新使用 workbox-window 用户确认模式
- Webhook 使用单次发送 + 日志记录 (不阻塞主流程)

### 风险与缓解
- **风险**: nonce 生成影响性能 → **缓解**: 使用 secrets.token_urlsafe(16)，开销极小
- **风险**: SW 更新提示频繁打扰用户 → **缓解**: 仅重大更新提示，小更新静默

---

## Round 3 经验

### 发现的问题
- (待填充)

### 设计决策
- (待填充)

### 风险与缓解
- (待填充)
