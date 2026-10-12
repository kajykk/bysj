import { ref } from 'vue'
import { defineStore } from 'pinia'
// P1-28 修复：改用 safeStorage，不再裸调 localStorage。
// 原实现在 store 初始化时 `localStorage.getItem(...)`，存储不可用时
// （Safari 隐私模式 / 禁用站点数据 / 配额已满 / 企业策略禁止）直接抛异常
// → 应用挂载链断裂 → 整站白屏，用户连错误提示都看不到。
import { safeLocalGetItem, safeLocalSetItem } from '@/utils/safeStorage'

const SIDEBAR_COLLAPSED_KEY = 'dws_sidebar_collapsed'

export const useLayoutStore = defineStore('layout', () => {
  const sidebarCollapsed = ref<boolean>(
    safeLocalGetItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  )

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    safeLocalSetItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed.value))
  }

  function setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed
    safeLocalSetItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
  }

  return { sidebarCollapsed, toggleSidebar, setSidebarCollapsed }
})
