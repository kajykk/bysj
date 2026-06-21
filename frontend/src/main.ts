import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { applyCspMetaTag } from './csp'
import { useAuthStore } from './stores/auth'
import { registerServiceWorker } from './utils/serviceWorker'
import { initSentry, captureException } from './plugins/sentry'

import './styles/variables.scss'
import './styles/mixins.scss'
import './styles/transitions.scss'
import './styles/theme.scss'
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

// 初始化 Sentry 监控（需在 router 注册之后、mount 之前）
initSentry(app, router)

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
