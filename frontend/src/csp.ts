// FE-002 修复：收紧 connect-src，避免允许任意 http/https/ws/wss 源。
//
// 生产环境：仅允许 'self' 和 Sentry 错误上报。
// 开发环境：额外允许 Vite HMR（ws/wss）和本地后端（localhost）。
const PROD_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self'",
  "connect-src 'self' https://sentry.io https://*.sentry.io",
].join('; ')

const DEV_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self'",
  // 开发环境：允许 Vite HMR（ws/wss）和本地后端调试
  "connect-src 'self' ws: wss: http://localhost:* http://127.0.0.1:* https://sentry.io https://*.sentry.io",
].join('; ')

const DEFAULT_POLICY = import.meta.env.PROD ? PROD_POLICY : DEV_POLICY

export function applyCspMetaTag() {
  if (typeof document === 'undefined') return
  const existing = document.querySelector('meta[http-equiv="Content-Security-Policy"]')
  if (existing) return
  const meta = document.createElement('meta')
  meta.setAttribute('http-equiv', 'Content-Security-Policy')
  meta.setAttribute('content', DEFAULT_POLICY)
  document.head.appendChild(meta)
}
