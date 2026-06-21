# PWA Integration Report v1.11

> **迭代**: v1.11-production-readiness-hardening
> **日期**: 2026-04-29
> **状态**: Phase 1 PWA 生产闭环完成

---

## 1. 变更摘要

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `frontend/package.json` | 修改 | 新增 `vite-plugin-pwa` 和 `workbox-window` 依赖 |
| `frontend/vite.config.ts` | 修改 | 集成 `VitePWA` 插件，配置 manifest 和 workbox |
| `frontend/src/utils/serviceWorker.ts` | 重写 | 使用 `virtual:pwa-register/vue` 替代手动注册 |
| `frontend/src/service-worker.ts` | 废弃 | 添加 `@deprecated` 标记，保留历史参考 |
| `frontend/src/types/pwa.d.ts` | 新增 | PWA 虚拟模块 TypeScript 类型声明 |
| `frontend/tsconfig.app.json` | 修改 | types 增加 `vite-plugin-pwa/client` |

---

## 2. 技术方案

### 2.1 方案选择

采用 `vite-plugin-pwa` + `generateSW` 策略：

- **自动生成 SW**: 构建时由插件自动生成 `sw.js`
- **自动注册**: `injectRegister: 'auto'` 自动注入注册代码
- **虚拟模块**: `virtual:pwa-register/vue` 提供 Vue 组合式函数

### 2.2 废弃旧方案

旧的手写 `src/service-worker.ts` 已标记为 `@deprecated`：
- 不再参与构建
- 缓存策略由 Workbox 配置接管
- 注册逻辑由 `virtual:pwa-register/vue` 接管

---

## 3. Manifest 配置

```json
{
  "name": "抑郁症动态预警与干预系统",
  "short_name": "抑郁预警系统",
  "description": "基于多模态数据的智能风险评估平台",
  "theme_color": "#409eff",
  "background_color": "#ffffff",
  "display": "standalone",
  "scope": "/",
  "start_url": "/",
  "icons": [
    { "src": "/icon-192x192.png", "sizes": "192x192" },
    { "src": "/icon-512x512.png", "sizes": "512x512" }
  ]
}
```

**注意**: icons 文件 (`icon-192x192.png`, `icon-512x512.png`) 需放入 `public/` 目录。

---

## 4. Workbox 缓存策略

| 资源类型 | 策略 | 配置 |
|----------|------|------|
| 静态资源 (JS/CSS/HTML/字体/图片) | Precache | `globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}']` |
| API 请求 | NetworkFirst | 缓存名 `api-cache`, 24h 过期 |
| 图片 | StaleWhileRevalidate | 缓存名 `image-cache`, 7天过期 |
| 字体 | CacheFirst | 缓存名 `font-cache`, 365天过期 |
| 导航降级 | offline.html | `navigateFallback: '/offline.html'` |

---

## 5. 注册逻辑

使用 `virtual:pwa-register/vue` 提供的 `useRegisterSW`：

```typescript
import { useRegisterSW } from 'virtual:pwa-register/vue'

useRegisterSW({
  immediate: true,
  onRegistered: (r) => console.log('[SW] Registered:', r?.scope),
  onRegisterError: (error) => console.error('[SW] Registration failed:', error),
  onNeedRefresh: () => { /* 提示用户更新 */ },
  onOfflineReady: () => { /* 提示离线可用 */ },
})
```

---

## 6. 构建产物

执行 `npm run build` 后，dist 目录将包含：

```
dist/
  ├── sw.js                    # 自动生成的 Service Worker
  ├── manifest.webmanifest     # Web App Manifest
  ├── workbox-*.js             # Workbox 运行时
  ├── offline.html             # 离线兜底页面 (来自 public/)
  └── assets/                  # 构建产物
```

---

## 7. 验证状态

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 插件安装 | ✅ | package.json 已包含依赖 |
| vite.config.ts 配置 | ✅ | VitePWA 插件已配置 |
| Manifest 配置 | ✅ | 字段完整 |
| Workbox 缓存策略 | ✅ | JS/CSS/API/图片/字体策略已配置 |
| offline.html 预缓存 | ✅ | navigateFallback 已配置 |
| SW 注册逻辑 | ✅ | virtual:pwa-register/vue 已集成 |
| 旧 SW 废弃 | ✅ | @deprecated 标记已添加 |
| TypeScript 类型 | ✅ | pwa.d.ts 已创建 |
| 构建产物验证 | ⚠️ | 环境限制，无法实际构建 |
| 浏览器 SW 激活 | [-] | 需浏览器环境 |
| 断网离线页面 | [-] | 需浏览器环境 |

---

## 8. 后续建议

1. **图标文件**: 将 PWA 图标 (`icon-192x192.png`, `icon-512x512.png`) 放入 `frontend/public/`
2. **构建验证**: 在支持 npm 的环境中执行 `npm install && npm run build` 验证产物
3. **浏览器测试**: 使用 Chrome DevTools 验证 SW 注册和离线功能
4. **Lighthouse PWA 审计**: 环境可用时运行 Lighthouse 检查 PWA 合规性

---

> **产出日期**: 2026-04-29
> **报告状态**: 已归档
