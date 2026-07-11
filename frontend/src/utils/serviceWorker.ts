/**
 * Service Worker registration using vite-plugin-pwa virtual module.
 * Replaces the legacy manual registration with auto-generated SW support.
 */

import { useRegisterSW } from 'virtual:pwa-register/vue'
import { ElNotification } from 'element-plus/es/components/notification/index'
import i18n from '@/i18n'

const t = i18n.global.t.bind(i18n.global)

export function registerServiceWorker(): void {
  const { updateServiceWorker } = useRegisterSW({
    immediate: true,
    onRegistered(r) {
      if (r) {
        console.log('[SW] Registered:', r.scope)
      }
    },
    onRegisterError(error) {
      console.error('[SW] Registration failed:', error)
    },
    onNeedRefresh() {
      console.log('[SW] New version available')
      // M-31 修复：使用异步通知替代同步 confirm()，避免阻塞主线程
      ElNotification({
        title: t('serviceWorker.updateAvailableTitle'),
        message: t('serviceWorker.updateAvailableMessage'),
        type: 'success',
        duration: 0,
        onClick: () => {
          updateServiceWorker(true)
        },
      })
    },
    onOfflineReady() {
      console.log('[SW] Offline ready')
    },
  })
}

export function unregisterServiceWorker(): void {
  if ('serviceWorker' in navigator) {
    // M-L 修复：添加 .catch() 处理注销失败，避免未捕获的 Promise rejection
    navigator.serviceWorker.ready
      .then((registration) => registration.unregister())
      .catch((error) => {
        console.error('[SW] Unregister failed:', error)
      })
  }
}
