import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTheme } from './useTheme'

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('应默认使用 auto 主题', () => {
    const { theme } = useTheme()
    expect(theme.value).toBe('auto')
  })

  it('应从 localStorage 读取主题', () => {
    localStorage.setItem('theme', 'dark')
    const { theme } = useTheme()
    expect(theme.value).toBe('dark')
  })

  it('设置 dark 主题应添加 dark 类', () => {
    const { setTheme } = useTheme()
    setTheme('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('设置 light 主题应移除 dark 类', () => {
    document.documentElement.classList.add('dark')
    const { setTheme } = useTheme()
    setTheme('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('isDark 应反映当前主题', () => {
    const { isDark, setTheme } = useTheme()
    setTheme('dark')
    expect(isDark.value).toBe(true)
    setTheme('light')
    expect(isDark.value).toBe(false)
  })
})
