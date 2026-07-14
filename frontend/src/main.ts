import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { applyCspMetaTag } from './csp'
import { useAuthStore } from './stores/auth'
import { setRedirectToLogin } from './api/request'
import { registerServiceWorker } from './utils/serviceWorker'

// WF-1 性能优化：Sentry 延迟初始化，移除首屏关键渲染路径
// 首屏阶段用空实现缓冲，Sentry 异步加载完成后再赋值为真实实现
let captureException: (err: Error, ctx?: Record<string, unknown>) => void = () => {}

// 性能分析：Vite 会将以下 CSS 内联到主 chunk，不会产生额外网络请求，因此同步 import 的实际开销有限。
// variables/theme 为首屏必需；mixins/transitions/utilities 为工具样式，可能被首屏组件引用，保留同步加载以避免 FOUC。
// element-plus 暗色变量：若改为 useTheme.ts 动态 import，会在切换暗色时产生 FOUC（暗色类已加但 CSS 未就绪），故保留在此处。
import './styles/variables.scss'
import './styles/mixins.scss'
import './styles/transitions.scss'
import './styles/theme.scss'
import './styles/utilities.scss'
import 'element-plus/theme-chalk/dark/css-vars.css'

applyCspMetaTag()
registerServiceWorker()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(i18n)

const auth = useAuthStore(pinia)
auth.restore()

// 循环依赖治理：注入 router.replace 回调，替代 request.ts 内部的动态 import('@/router')。
// 必须在 mount 之前注入：restore() 不发请求，首个可能触发 401 的请求发生在组件挂载之后。
// R-002 修复：保留完整 URL（pathname + search + hash），登录后可恢复 query/hash 上下文。
setRedirectToLogin(() => {
  const { pathname, search, hash } = window.location
  router.replace({ path: '/login', query: { redirect: pathname + search + hash } })
})

// 初始化 Sentry 监控（延迟到 mount 之后异步执行，避免阻塞首屏渲染）
// 在 router 注册之后加载；首屏渲染期间错误由上方空实现缓冲
import('./plugins/sentry').then(({ initSentry, captureException: cap }) => {
  initSentry(app, router)
  captureException = cap
}).catch(() => {})

// 全局组件异常捕获：将 Vue 内部错误上报到 Sentry
app.config.errorHandler = (err, _instance, info) => {
  captureException(err instanceof Error ? err : new Error(String(err)), { info })
  // 修复：生产环境不输出详细错误到控制台，避免泄露 API 响应体/组件树等敏感信息
  if (import.meta.env.DEV) {
    console.error('[Vue ErrorHandler]', err, info)
  }
}

// 捕获未处理的 Promise 拒绝，避免静默失败并上报到 Sentry
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  const error = reason instanceof Error ? reason : new Error(String(reason))
  captureException(error, { source: 'unhandledrejection' })
  // 修复：生产环境不输出详细错误到控制台
  if (import.meta.env.DEV) {
    console.error('[Unhandled Rejection]', reason)
  }
})

app.mount('#app')
