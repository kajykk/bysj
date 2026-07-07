import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { translate } from '@/i18n'

const t = translate

function defaultLoadingText(): string {
  try {
    return t('common.loading')
  } catch {
    return '加载中...'
  }
}

export const useLoadingStore = defineStore('loading', () => {
  const globalLoading = ref(false)
  const loadingText = ref(defaultLoadingText())
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
      loadingText.value = defaultLoadingText()
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
