import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * SEC-FIX (C2/M7): useAnalytics 安全行为测试
 *
 * 验证:
 * - 事件始终通过带 Authorization 头的 fetch 发送 (不再无条件走 sendBeacon,
 *   sendBeacon 无法携带 Authorization, 原实现导致所有埋点未认证)
 * - 登出重置同意缓存 (resetAnalyticsConsent), 防止跨用户状态泄漏
 */

const { tokenMock } = vi.hoisted(() => ({ tokenMock: vi.fn() }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get token() {
      return tokenMock()
    },
  }),
}))

import { useAnalytics, resetAnalyticsConsent } from './useAnalytics'

const fetchMock = vi.fn()

const eventsCalls = () =>
  fetchMock.mock.calls.filter(([url]) => String(url).includes('/events'))

describe('useAnalytics - sendEvents 鉴权行为', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tokenMock.mockReturnValue('test-token')
    fetchMock.mockResolvedValue({ ok: true } as Response)
    vi.stubGlobal('fetch', fetchMock)
    resetAnalyticsConsent()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('track 时使用带 Authorization 的 fetch, 不使用 sendBeacon', async () => {
    // 预置同意状态 (setConsent 会产生一次 PUT 请求, 之后清零)
    await useAnalytics().setConsent(true)
    fetchMock.mockClear()

    const { track } = useAnalytics()
    await track('assessment_start', { assessment_type: 'structured' })

    const calls = eventsCalls()
    expect(calls).toHaveLength(1)
    const [url, options] = calls[0]
    expect(url).toBe('/api/v1/analytics/events')
    expect(options.method).toBe('POST')
    expect(options.headers.Authorization).toBe('Bearer test-token')
    expect(options.keepalive).toBe(true)
  })

  it('未同意时静默跳过, 不发事件请求', async () => {
    await useAnalytics().setConsent(false)
    fetchMock.mockClear()

    const { track } = useAnalytics()
    await track('assessment_start')

    expect(eventsCalls()).toHaveLength(0)
  })

  it('未登录 (无 token) 时不发请求', async () => {
    tokenMock.mockReturnValue('')

    const { track } = useAnalytics()
    await track('assessment_start')

    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('useAnalytics - 同意缓存重置 (SEC-FIX C3/M7)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tokenMock.mockReturnValue('test-token')
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/consent')) {
        return { ok: true, json: async () => ({ data: { consented: true } }) } as Response
      }
      return { ok: true } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    resetAnalyticsConsent()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resetAnalyticsConsent 清除模块级缓存, 下次重新从后端加载', async () => {
    const a = useAnalytics()
    await a.refreshConsent()
    expect(a.consented.value).toBe(true)

    // 模拟登出: A 用户同意状态不应被 B 用户继承
    resetAnalyticsConsent()
    fetchMock.mockClear()
    fetchMock.mockImplementation(async () => {
      return { ok: true, json: async () => ({ data: { consented: false } }) } as Response
    })

    const b = useAnalytics()
    await b.refreshConsent()
    // 重新走了后端加载 (fetch 被再次调用), 而不是复用 A 的缓存
    expect(b.consented.value).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
