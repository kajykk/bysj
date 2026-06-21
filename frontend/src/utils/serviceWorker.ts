/**
 * Service Worker registration using vite-plugin-pwa virtual module.
 * Replaces the legacy manual registration with auto-generated SW support.
 */

import { useRegisterSW } from 'virtual:pwa-register/vue'

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
      if (confirm('新版本可用，是否立即更新？')) {
        updateServiceWorker(true)
      }
    },
    onOfflineReady() {
      console.log('[SW] Offline ready')
    },
  })
}

export function unregisterServiceWorker(): void {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready.then((registration) => {
      registration.unregister()
    })
  }
}
