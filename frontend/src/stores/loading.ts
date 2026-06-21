import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useLoadingStore = defineStore('loading', () => {
  const globalLoading = ref(false)
  const loadingText = ref('加载中...')
  const loadingCount = ref(0)

  const isLoading = computed(() => globalLoading.value || loadingCount.value > 0)

  function startLoading(text?: string) {
    loadingCount.value++
    if (text) {
      loadingText.value = text
    }
    globalLoading.value = true
  }

  function stopLoading() {
    loadingCount.value = Math.max(0, loadingCount.value - 1)
    if (loadingCount.value === 0) {
      globalLoading.value = false
      loadingText.value = '加载中...'
    }
  }

  function setGlobalLoading(loading: boolean, text?: string) {
    globalLoading.value = loading
    if (text) {
      loadingText.value = text
    }
  }

  return {
    globalLoading,
    loadingText,
    loadingCount,
    isLoading,
    startLoading,
    stopLoading,
    setGlobalLoading,
  }
})
