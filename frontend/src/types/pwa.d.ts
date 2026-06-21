/// <reference types="vite-plugin-pwa/client" />

declare module 'virtual:pwa-register/vue' {
  import type { Ref } from 'vue'

  export interface RegisterSWOptions {
    immediate?: boolean
    onRegistered?: (registration: ServiceWorkerRegistration | undefined) => void
    onRegisterError?: (error: Error) => void
    onNeedRefresh?: () => void
    onOfflineReady?: () => void
  }

  export interface UseRegisterSWReturn {
    needRefresh: Ref<boolean>
    offlineReady: Ref<boolean>
    updateServiceWorker: (reloadPage?: boolean) => Promise<void>
  }

  export function useRegisterSW(options?: RegisterSWOptions): UseRegisterSWReturn
}
