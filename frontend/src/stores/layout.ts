import { ref } from 'vue'
import { defineStore } from 'pinia'

const SIDEBAR_COLLAPSED_KEY = 'dws_sidebar_collapsed'

export const useLayoutStore = defineStore('layout', () => {
  const sidebarCollapsed = ref<boolean>(
    localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  )

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed.value))
  }

  function setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
  }

  return { sidebarCollapsed, toggleSidebar, setSidebarCollapsed }
})
