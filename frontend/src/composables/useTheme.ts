import { onScopeDispose, ref, watch } from 'vue'

export type Theme = 'light' | 'dark' | 'auto'

export function useTheme() {
  const theme = ref<Theme>((localStorage.getItem('theme') as Theme) || 'auto')
  const isDark = ref(false)

  const applyTheme = () => {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    isDark.value = theme.value === 'dark' || (theme.value === 'auto' && prefersDark)

    // Element Plus 标准：使用 html.dark 类名
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme
    localStorage.setItem('theme', newTheme)
    applyTheme()
  }

  // P1-D-9 修复：监听系统主题变化，并在作用域销毁时移除监听器防止内存泄漏
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const onMediaChange = () => {
    if (theme.value === 'auto') {
      applyTheme()
    }
  }
  mediaQuery.addEventListener('change', onMediaChange)
  onScopeDispose(() => {
    mediaQuery.removeEventListener('change', onMediaChange)
  })

  // 初始化
  applyTheme()

  return {
    theme,
    isDark,
    setTheme,
    applyTheme
  }
}
