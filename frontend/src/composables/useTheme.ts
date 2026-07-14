import { onScopeDispose, ref } from 'vue'

export type Theme = 'light' | 'dark' | 'auto'

// M-FE-20 修复：封装 localStorage 访问，添加异常保护，
// 避免隐私模式/存储被禁用/配额超限时抛出未捕获异常
// L-FE-3 修复：补充 SSR 安全检查，访问 localStorage 前确认 window 可用
function safeGetTheme(): Theme {
  if (typeof window === 'undefined') return 'auto'
  try {
    return (localStorage.getItem('theme') as Theme) || 'auto'
  } catch {
    return 'auto'
  }
}

function safeSetTheme(theme: Theme) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem('theme', theme)
  } catch {
    // 存储不可用时静默失败，主题切换在当前会话仍生效
  }
}

// WF-1 性能优化：暗色主题 CSS 移出首屏关键路径，按需异步加载
let darkCssPromise: Promise<unknown> | null = null

export function useTheme() {
  const theme = ref<Theme>(safeGetTheme())
  const isDark = ref(false)

  const applyTheme = () => {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    isDark.value = theme.value === 'dark' || (theme.value === 'auto' && prefersDark)

    // Element Plus 标准：使用 html.dark 类名
    document.documentElement.classList.toggle('dark', isDark.value)

    // 仅当实际需要暗色时才加载暗色变量 CSS（首次加载默认浅色不阻塞首屏）
    if (isDark.value && !darkCssPromise) {
      darkCssPromise = import('element-plus/theme-chalk/dark/css-vars.css').catch(() => {})
    }
  }

  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme
    safeSetTheme(newTheme)
    applyTheme()
  }

  // P1-D-9 修复：监听系统主题变化，并在作用域销毁时移除监听器防止内存泄漏
  // L-FE-3 修复：SSR 环境下跳过 matchMedia 监听注册
  if (typeof window !== 'undefined') {
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
  }

  // 初始化
  applyTheme()

  return {
    theme,
    isDark,
    setTheme,
    applyTheme
  }
}
