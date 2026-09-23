# PWA & Lighthouse Verification v1.11.2

> **迭代**: v1.11.2-security-test-closure  
> **日期**: 2026-04-30  
> **状态**: Ready for Verification  
> **目标**: 补齐 v1.11.1 中 PWA 浏览器行为与 Lighthouse 实跑记录

---

## 1. 目标

v1.11.1 已确认前端构建和 PWA 产物生成，但仍需补充：

1. 浏览器中 Service Worker 是否注册。
2. Service Worker 是否 activated。
3. Manifest 是否被识别。
4. Cache Storage 是否符合预期。
5. 断网后是否显示 `offline.html`。
6. Lighthouse Performance / Accessibility / PWA 审计结果。

---

## 2. 前置条件

| 条件 | 要求 |
|---|---|
| 前端构建 | `npm run build` 通过 |
| 预览服务 | `npm run preview` 可运行 |
| PWA 产物 | `sw.js`、manifest、offline.html 存在 |
| 图标 | `icon-192x192.png`、`icon-512x512.png` 存在 |
| 浏览器 | Chrome / Chromium 可用 |
| Lighthouse | npx lighthouse 或 Chrome DevTools 可用 |

---

## 3. 验证命令

```bash
cd frontend
npm run build
npm run preview
```

Lighthouse 示例：

```bash
npx lighthouse http://localhost:4173/login --output=json --output=html
npx lighthouse http://localhost:4173/user/dashboard --output=json --output=html
npx lighthouse http://localhost:4173/user/assessments --output=json --output=html
npx lighthouse http://localhost:4173/user/warnings --output=json --output=html
```

> 如果 preview 端口不是 4173，以实际端口为准。

---

## 4. PWA 浏览器验证清单

| 编号 | 验证项 | 期望 | 结果 |
|---|---|---|---|
| PWA-001 | Service Worker registered | 是 | TBD |
| PWA-002 | Service Worker activated | 是 | TBD |
| PWA-003 | Manifest recognized | 是 | TBD |
| PWA-004 | Manifest name/short_name 正确 | 是 | TBD |
| PWA-005 | 192 图标识别 | 是 | TBD |
| PWA-006 | 512 图标识别 | 是 | TBD |
| PWA-007 | Cache Storage 有 precache | 是 | TBD |
| PWA-008 | JS/CSS/font 被缓存 | 是 | TBD |
| PWA-009 | 图片缓存策略生效 | 是 | TBD |
| PWA-010 | API GET 使用 NetworkFirst | 是 | TBD |
| PWA-011 | API POST/PUT/DELETE 不被缓存 | 是 | TBD |
| PWA-012 | 断网后访问导航页面 | 显示 `offline.html` | TBD |
| PWA-013 | 新版本更新提示 | 可用或有说明 | TBD |

---

## 5. Lighthouse 验证页面

| 页面 | URL | 用途 |
|---|---|---|
| Login | `/login` | 首屏、非图表页面 |
| Dashboard | `/user/dashboard` | 用户主页面 |
| Assessments | `/user/assessments` | 评估列表 |
| Warnings | `/user/warnings` | 预警页面 |

---

## 6. Lighthouse 结果记录

| 页面 | Performance | Accessibility | Best Practices | SEO | PWA | 结论 |
|---|---:|---:|---:|---:|---|---|
| `/login` | TBD | TBD | TBD | TBD | TBD | TBD |
| `/user/dashboard` | TBD | TBD | TBD | TBD | TBD | TBD |
| `/user/assessments` | TBD | TBD | TBD | TBD | TBD | TBD |
| `/user/warnings` | TBD | TBD | TBD | TBD | TBD | TBD |

---

## 7. 指标阈值

| 指标 | 目标 | 阻塞级别 |
|---|---:|---|
| Performance | >= 80，或有优化清单 | P1 |
| Accessibility | >= 90 | P1 |
| Best Practices | >= 90 | P2 |
| SEO | >= 90 | P2 |
| PWA 关键项 | 无关键失败 | P1 |
| LCP | <= 2500ms | warn |
| CLS | <= 0.1 | warn |
| TBT | <= 300ms | warn |

---

## 8. Chunk 验证

构建后记录关键 chunk：

| Chunk | v1.10.1 基线 | v1.11.2 目标 | 实际 |
|---|---:|---:|---:|
| charts | 813KB | 不进入登录页首屏，尽量 < 500KB | TBD |
| vendor | 621KB | 尽量 < 500KB | TBD |
| vue-core | 483KB | < 500KB | TBD |
| ui | 427KB | 不明显劣化 | TBD |
| export-excel | 无独立记录 | 独立 chunk | TBD |
| export-pdf | 无独立记录 | 独立 chunk | TBD |

---

## 9. 失败处理

| 失败项 | 处理 |
|---|---|
| SW 未注册 | 检查 `vite-plugin-pwa` 配置和注册入口 |
| SW 未激活 | 清理旧 SW/cache 后重试 |
| offline.html 不显示 | 检查 `navigateFallback` 和 precache |
| 图标缺失 | 补齐 public 图标 |
| Lighthouse A11Y < 90 | 优先修复 aria/label/viewport/图表替代内容 |
| Performance < 80 | 记录瓶颈，进入性能优化清单 |
| charts 进入登录首屏 | 检查路由懒加载和图表 import |

---

## 10. 结论模板

```text
PWA 浏览器验证：通过 / 未通过
Service Worker：registered / activated / failed
离线页面：通过 / 未通过
Manifest：通过 / 未通过
Lighthouse Performance：达标 / 未达标但有清单 / 未运行
Lighthouse Accessibility：达标 / 未达标
Chunk 验证：通过 / 待优化
是否允许进入 v1.11.2 质量门禁：是 / 否
```
