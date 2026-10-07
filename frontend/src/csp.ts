// FE-002 修复：收紧 connect-src，避免允许任意 http/https/ws/wss 源。
//
// 生产环境：仅允许 'self' 和 Sentry 错误上报。
// 开发环境：额外允许 Vite HMR（ws/wss）和本地后端（localhost）。
//
// M-34 修复：生产环境 CSP 由后端 CSP 中间件统一管理（H-02 已实现 nonce-based CSP），
// 前端不再设置 meta 标签，避免与后端 header 冲突。
// 开发环境保留 'unsafe-inline' 以支持 Vite HMR 注入的样式。
//
// RES-P2-007 修复：移除 Google Fonts CDN 白名单（fonts.googleapis.com / fonts.gstatic.com），
// 前端已改用系统字体栈（见 index.html + variables.scss），不再依赖外部 CDN。
export const PROD_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  // RES-P2-007: 移除 https://fonts.gstatic.com，仅允许 self + data:
  "font-src 'self' data:",
  // 注意：'unsafe-inline' 因 Element Plus 运行时注入样式而保留
  // 生产环境由后端 CSP header 覆盖此 meta 标签
  // RES-P2-007: 移除 https://fonts.googleapis.com
  "style-src 'self' 'unsafe-inline'",
  // CSP-unsafe-eval 加固：生产不再允许 eval。
  // 实测依据（2026-10-08）：dist/assets 全量 chunk 中 `new Function` / 裸 `eval(` / `Function('`
  // 均 0 命中；用真实 Chromium 遍历 19 条登录后路由（ECharts 已实际渲染出 canvas）做 A/B：
  // 去掉 'unsafe-eval' 后零 securitypolicyviolation，渲染文本与基线逐字符一致。
  // 历史归因（ed2a3a6, 2026-08-07 因白屏引入）对当前产物不成立 —— 现用 vue-i18n v11 的
  // @intlify/message-compiler 全包不含 new Function，不做运行时代码生成。
  "script-src 'self'",
  // RES-P2-007: 移除 https://fonts.googleapis.com https://fonts.gstatic.com
  "connect-src 'self' https://sentry.io https://*.sentry.io",
].join('; ')

export const DEV_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  // RES-P2-007: 移除 https://fonts.gstatic.com
  "font-src 'self' data:",
  // RES-P2-007: 移除 https://fonts.googleapis.com
  "style-src 'self' 'unsafe-inline'",
  // 开发环境同样不含 'unsafe-eval'，与生产保持一致（避免本地测不出 eval 回归）。
  // 依据（静态）：@intlify/* 全包无 new Function；src/ 中无任何 `template:` 字符串模板选项，
  // 故 dev 下 Vue 也不会走 compileToFunction（那才是 new Function 的来源）。
  // 未验证项（如实记账）：本轮未能端到端跑通 vite dev server —— 其依赖预构建 commit 阶段
  // 需批量删除 node_modules/.vite/deps_temp（55 个文件），被沙箱批量删除守卫拦截；
  // 关掉预发现后又因 dayjs CJS 互操作报错而无法完整渲染。dev 侧结论目前只有静态依据。
  // 若本地出现 CSP 报错，先恢复本行的 'unsafe-eval' 并回退此项加固。
  "script-src 'self'",
  // 开发环境：允许 Vite HMR（ws/wss）和本地后端调试
  // L-FE-13 修复：收紧 localhost 端口为已知端口，避免允许任意本地服务
  // RES-P2-007: 移除 https://fonts.googleapis.com https://fonts.gstatic.com
  "connect-src 'self' ws: wss: http://localhost:5173 http://localhost:8000 http://127.0.0.1:5173 http://127.0.0.1:8000 https://sentry.io https://*.sentry.io",
].join('; ')

const DEFAULT_POLICY = import.meta.env.PROD ? PROD_POLICY : DEV_POLICY

export function applyCspMetaTag() {
  if (typeof document === 'undefined') return
  // M-34 修复：生产环境由后端 CSP 中间件统一管理（H-02 nonce-based CSP），
  // 前端不设置 meta 标签，避免冲突
  if (import.meta.env.PROD) return
  const existing = document.querySelector('meta[http-equiv="Content-Security-Policy"]')
  if (existing) return
  const meta = document.createElement('meta')
  meta.setAttribute('http-equiv', 'Content-Security-Policy')
  meta.setAttribute('content', DEFAULT_POLICY)
  document.head.appendChild(meta)
}
