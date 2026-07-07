// FE-002 修复：收紧 connect-src，避免允许任意 http/https/ws/wss 源。
//
// 生产环境：仅允许 'self' 和 Sentry 错误上报。
// 开发环境：额外允许 Vite HMR（ws/wss）和本地后端（localhost）。
//
// M-34 修复：生产环境 CSP 由后端 CSP 中间件统一管理（H-02 已实现 nonce-based CSP），
// 前端不再设置 meta 标签，避免与后端 header 冲突。
// 开发环境保留 'unsafe-inline' 以支持 Vite HMR 注入的样式。
const PROD_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data: https://fonts.gstatic.com",
  // 注意：'unsafe-inline' 因 Element Plus 运行时注入样式而保留
  // 生产环境由后端 CSP header 覆盖此 meta 标签
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "script-src 'self' 'unsafe-eval'",
  "connect-src 'self' https://sentry.io https://*.sentry.io https://fonts.googleapis.com https://fonts.gstatic.com",
].join('; ')

const DEV_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data: https://fonts.gstatic.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "script-src 'self' 'unsafe-eval'",
  // 开发环境：允许 Vite HMR（ws/wss）和本地后端调试
  // L-FE-13 修复：收紧 localhost 端口为已知端口，避免允许任意本地服务
  "connect-src 'self' ws: wss: http://localhost:5173 http://localhost:8000 http://127.0.0.1:5173 http://127.0.0.1:8000 https://sentry.io https://*.sentry.io https://fonts.googleapis.com https://fonts.gstatic.com",
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
