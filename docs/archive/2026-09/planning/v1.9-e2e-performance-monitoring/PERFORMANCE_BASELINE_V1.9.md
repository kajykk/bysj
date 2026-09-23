# v1.9 性能基线报告 (PERFORMANCE_BASELINE_V1.9.md)

> **迭代名称**: v1.9-e2e-performance-monitoring
> **日期**: 2026-04-29
> **状态**: Phase 3 完成

---

## 1. 性能优化配置

### 1.1 Vite 构建配置

| 配置项 | 状态 | 说明 |
|--------|------|------|
| manualChunks | ✅ 已配置 | 按库分割 chunk |
| chunkSizeWarningLimit | ✅ 500KB | 警告阈值 |
| cssCodeSplit | ✅ 已启用 | CSS 代码分割 |
| sourcemap | ✅ 已启用 | 调试支持 |
| minify | ✅ terser | 代码压缩 |
| drop_console | ✅ 已启用 | 移除 console |
| optimizeDeps | ✅ 已配置 | 预构建依赖 |

### 1.2 Chunk 分割策略

| Chunk 名称 | 包含内容 | 目标大小 |
|------------|----------|----------|
| vue-core | vue (不含 router) | < 100KB |
| router | vue-router | < 50KB |
| state | pinia | < 50KB |
| ui | element-plus | < 200KB |
| icons | @element-plus/icons-vue | < 100KB |
| charts | echarts | < 300KB |
| datetime | dayjs | < 30KB |
| security | dompurify | < 30KB |
| http | axios | < 50KB |
| i18n | vue-i18n | < 50KB |
| vendor | 其他依赖 | < 200KB |

### 1.3 路由懒加载

| 路由类型 | 加载方式 | 状态 |
|----------|----------|------|
| 登录页 | 动态导入 | ✅ 已配置 |
| 用户页面 | 动态导入 + chunkName | ✅ 已配置 |
| 咨询师页面 | 动态导入 + chunkName | ✅ 已配置 |
| 管理员页面 | 动态导入 + chunkName | ✅ 已配置 |

---

## 2. Lighthouse CI 配置

### 2.1 测试页面

| 页面 | URL | 优先级 |
|------|-----|--------|
| 登录页 | /login | P0 |
| 用户仪表盘 | /user/dashboard | P0 |
| 评估历史 | /user/assessments | P0 |
| 预警列表 | /user/warnings | P0 |

### 2.2 断言阈值

| 指标 | 警告阈值 | 错误阈值 |
|------|----------|----------|
| Performance | >= 80 | - |
| Accessibility | >= 90 | < 90 |
| Best Practices | >= 90 | - |
| SEO | >= 90 | - |
| FCP | < 1.8s | - |
| LCP | < 2.5s | - |
| CLS | < 0.1 | - |
| TBT | < 300ms | - |
| Speed Index | < 3.0s | - |

---

## 3. 性能基线数据

> **注意**: 由于环境限制，实际性能数据需在支持环境中采集。

### 3.1 预期基线

| 页面 | Performance | FCP | LCP | CLS | TBT |
|------|-------------|-----|-----|-----|-----|
| 登录页 | >= 85 | < 1.5s | < 2.0s | < 0.05 | < 200ms |
| 仪表盘 | >= 80 | < 1.8s | < 2.5s | < 0.1 | < 300ms |
| 评估页 | >= 80 | < 2.0s | < 3.0s | < 0.1 | < 300ms |
| 预警页 | >= 80 | < 1.8s | < 2.5s | < 0.1 | < 300ms |

---

## 4. 优化建议

### 4.1 已实施优化

| 优化项 | 状态 | 影响 |
|--------|------|------|
| 路由懒加载 | ✅ | 减少初始加载 |
| Chunk 分割 | ✅ | 并行加载 |
| 依赖预构建 | ✅ | 加速开发 |
| CSS 分割 | ✅ | 减少阻塞 |
| Console 移除 | ✅ | 减少代码 |

### 4.2 待实施优化

| 优化项 | 优先级 | 预期收益 |
|--------|--------|----------|
| 图片 WebP 格式 | P1 | 减少 30% 体积 |
| 图片懒加载 | P1 | 减少 LCP |
| 字体预加载 | P2 | 加速 FCP |
| Service Worker | P2 | 缓存优化 |
| HTTP/2 推送 | P3 | 减少延迟 |

---

## 5. 监控配置

### 5.1 Web Vitals 指标

| 指标 | 目标 | 采集方式 |
|------|------|----------|
| FCP | < 1.8s | Performance API |
| LCP | < 2.5s | Performance API |
| CLS | < 0.1 | Performance API |
| FID | < 100ms | Performance API |
| TTFB | < 600ms | Navigation Timing |

---

## 6. 签名

- **配置完成**: 2026-04-29
- **验证方式**: 代码审查
- **下一步**: Phase 4 监控体系搭建
