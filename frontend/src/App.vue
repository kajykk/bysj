<template>
  <div
    v-loading.fullscreen.lock="loadingStore.isLoading"
    class="app-root"
    :element-loading-text="loadingStore.loadingText"
  >
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useLoadingStore } from '@/stores/loading'
import { useAuthStore } from '@/stores/auth'
// P3-3: 启用前端 Web Vitals 采集 (FCP/LCP/INP/CLS/TTFB) + 自动上报到后端
// usePerformanceMonitor 内部通过 PerformanceObserver 采集, onMounted 启动, onUnmounted 清理
// autoReport 每 5 分钟上报一次; 页面卸载/隐藏时通过 sendBeacon 上报
import { usePerformanceMonitor } from '@/composables/usePerformanceMonitor'

const loadingStore = useLoadingStore()
const auth = useAuthStore()

// UI 升级 v3.2: 注入 body[data-role] 激活角色强调色系统
// --role-accent-current 会自动跟随角色变化，让三端导航/Header 视觉差异化
watch(
  () => auth.role,
  (role) => {
    if (typeof document === 'undefined') return
    if (role && ['user', 'counselor', 'admin'].includes(role)) {
      document.body.dataset.role = role
    } else {
      delete document.body.dataset.role
    }
  },
  { immediate: true }
)

// 启用性能监控: 自动采集 Core Web Vitals 并上报到 /api/v1/monitoring/frontend-metrics
usePerformanceMonitor({ autoReport: true })
</script>

<style scoped>
.app-root {
  min-height: 100dvh;
}
</style>
