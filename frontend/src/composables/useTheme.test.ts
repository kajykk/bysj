import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
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

  // ===== 新增测试：覆盖 auto 主题、matchMedia 监听、SSR 安全、异常处理 =====

  it('auto 主题在 prefers-color-scheme: dark 时应启用 dark', () => {
    // mock matchMedia 返回 prefers dark
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)

    const { theme, isDark } = useTheme()
    expect(theme.value).toBe('auto')
    expect(isDark.value).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('auto 主题在 prefers-color-scheme: light 时应禁用 dark', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)

    const { theme, isDark } = useTheme()
    expect(theme.value).toBe('auto')
    expect(isDark.value).toBe(false)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('setTheme 应将主题持久化到 localStorage', () => {
    const { setTheme } = useTheme()
    setTheme('dark')
    expect(localStorage.getItem('theme')).toBe('dark')

    setTheme('light')
    expect(localStorage.getItem('theme')).toBe('light')

    setTheme('auto')
    expect(localStorage.getItem('theme')).toBe('auto')
  })

  it('applyTheme 应根据当前主题重新计算 isDark', () => {
    const { theme, isDark, applyTheme, setTheme } = useTheme()

    // 初始 auto，prefersDark = false
    expect(isDark.value).toBe(false)

    setTheme('dark')
    expect(isDark.value).toBe(true)

    // 手动改 theme ref 并调用 applyTheme
    theme.value = 'light'
    applyTheme()
    expect(isDark.value).toBe(false)
  })

  it('matchMedia change 事件在 auto 主题时应触发 applyTheme', () => {
    let mediaChangeHandler: (() => void) | null = null
    let currentMatches = false

    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => {
      const mql = {
        matches: currentMatches,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: (_: string, cb: () => void) => {
          mediaChangeHandler = cb
        },
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }
      return mql as unknown as MediaQueryList
    })

    const scope = effectScope()
    scope.run(() => {
      const { isDark } = useTheme()
      expect(isDark.value).toBe(false)

      // 模拟系统主题变为 dark
      currentMatches = true
      mediaChangeHandler?.()

      expect(isDark.value).toBe(true)
      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })
    scope.stop()
  })

  it('matchMedia change 事件在非 auto 主题时不应触发 applyTheme', () => {
    let mediaChangeHandler: (() => void) | null = null
    let currentMatches = false

    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => {
      const mql = {
        matches: currentMatches,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: (_: string, cb: () => void) => {
          mediaChangeHandler = cb
        },
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }
      return mql as unknown as MediaQueryList
    })

    const scope = effectScope()
    scope.run(() => {
      const { isDark, setTheme } = useTheme()
      // 设置为 light 主题（非 auto）
      setTheme('light')
      expect(isDark.value).toBe(false)

      // 模拟系统主题变为 dark
      currentMatches = true
      mediaChangeHandler?.()

      // 因为不是 auto 主题，isDark 不应变化
      expect(isDark.value).toBe(false)
    })
    scope.stop()
  })

  it('onScopeDispose 应在 scope 销毁时移除 matchMedia 监听器', () => {
    const removeEventListenerSpy = vi.fn()
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: removeEventListenerSpy,
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)

    const scope = effectScope()
    scope.run(() => {
      useTheme()
    })

    scope.stop()

    expect(removeEventListenerSpy).toHaveBeenCalledWith('change', expect.any(Function))
  })

  it('localStorage 读取异常时应回退到 auto 主题', () => {
    // 模拟 localStorage.getItem 抛错
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })

    const { theme } = useTheme()
    expect(theme.value).toBe('auto')
  })

  it('localStorage 写入异常时不应抛错（静默失败）', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage quota exceeded')
    })

    const { setTheme } = useTheme()
    // 不应抛错
    expect(() => setTheme('dark')).not.toThrow()
  })

  it('多次切换主题应正确更新 dark 类', () => {
    const { setTheme } = useTheme()

    setTheme('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    setTheme('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    setTheme('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    setTheme('auto')
    // prefersDark = false (default mock)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('主题切换后 theme ref 应反映新值', () => {
    const { theme, setTheme } = useTheme()

    setTheme('dark')
    expect(theme.value).toBe('dark')

    setTheme('auto')
    expect(theme.value).toBe('auto')

    setTheme('light')
    expect(theme.value).toBe('light')
  })
})
