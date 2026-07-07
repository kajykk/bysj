import { beforeEach, describe, expect, it, vi } from 'vitest'
import { showHttpFeedback } from './httpFeedback'

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: vi.fn(),
    error: vi.fn()
  }
}))

describe('showHttpFeedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns normalized warning for 403', () => {
    const result = showHttpFeedback({ response: { status: 403, data: { detail: '无权限' } } }, 'fallback')
    expect(result.status).toBe(403)
    expect(result.detail).toBe('无权限')
  })

  // ===== 新增测试：覆盖 401 / 404 / 422 / 500 / 默认分支 =====

  it('401 状态应直接返回 normalized 且不调用 ElMessage', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 401, data: { detail: 'token expired' } } },
      'fallback'
    )

    expect(result.status).toBe(401)
    expect(result.detail).toBe('token expired')
    // 401 分支不调用 ElMessage（由路由守卫统一处理跳转）
    expect(ElMessage.warning).not.toHaveBeenCalled()
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('401 状态在 detail 缺失时应使用默认提示文案', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 401 } },
      ''
    )

    expect(result.status).toBe(401)
    expect(result.detail).toBe('登录状态失效，请重新登录')
    expect(ElMessage.warning).not.toHaveBeenCalled()
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('403 状态应调用 ElMessage.warning 并返回 normalized', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 403, data: { detail: 'forbidden' } } },
      'fallback'
    )

    expect(result.status).toBe(403)
    expect(ElMessage.warning).toHaveBeenCalledWith('forbidden')
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('404 状态（warning level）应调用 ElMessage.warning', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 404, data: { detail: 'not found' } } },
      'fallback'
    )

    expect(result.status).toBe(404)
    expect(result.level).toBe('warning')
    expect(ElMessage.warning).toHaveBeenCalledWith('not found')
  })

  it('422 状态（warning level）应调用 ElMessage.warning', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 422, data: { detail: 'validation failed' } } },
      'fallback'
    )

    expect(result.status).toBe(422)
    expect(result.level).toBe('warning')
    expect(ElMessage.warning).toHaveBeenCalledWith('validation failed')
  })

  it('500 状态（error level）应调用 ElMessage.error', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 500, data: { detail: 'server error' } } },
      'fallback'
    )

    expect(result.status).toBe(500)
    expect(result.level).toBe('error')
    expect(ElMessage.error).toHaveBeenCalledWith('server error')
    expect(ElMessage.warning).not.toHaveBeenCalled()
  })

  it('502 状态（error level）应调用 ElMessage.error', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 502, data: { detail: 'bad gateway' } } },
      'fallback'
    )

    expect(result.status).toBe(502)
    expect(result.level).toBe('error')
    expect(ElMessage.error).toHaveBeenCalledWith('bad gateway')
  })

  it('无 response 的错误（status=0）应走默认 error 分支并调用 ElMessage.error', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(new Error('network failure'), '网络异常')

    expect(result.status).toBe(0)
    expect(result.level).toBe('error')
    // detail 应为 error.message（非空字符串）而非 fallback
    expect(ElMessage.error).toHaveBeenCalledWith('network failure')
  })

  it('无 response 且无 message 的错误应使用 fallback 文案', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback({}, '默认错误提示')

    expect(result.status).toBe(0)
    expect(result.level).toBe('error')
    expect(ElMessage.error).toHaveBeenCalledWith('默认错误提示')
  })

  it('500 状态在 detail 缺失时应使用默认服务异常提示', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 500 } },
      ''
    )

    expect(result.detail).toBe('服务异常，请稍后重试')
    expect(ElMessage.error).toHaveBeenCalledWith('服务异常，请稍后重试')
  })

  it('404 状态在 detail 缺失时应使用默认资源不存在提示', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 404 } },
      ''
    )

    expect(result.detail).toBe('请求资源不存在')
    expect(ElMessage.warning).toHaveBeenCalledWith('请求资源不存在')
  })

  it('422 状态在 detail 缺失时应使用默认参数校验失败提示', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 422 } },
      ''
    )

    expect(result.detail).toBe('请求参数校验失败')
    expect(ElMessage.warning).toHaveBeenCalledWith('请求参数校验失败')
  })

  it('403 状态在 detail 缺失时应使用默认无权限提示', async () => {
    const { ElMessage } = await import('element-plus')

    const result = showHttpFeedback(
      { response: { status: 403 } },
      ''
    )

    expect(result.detail).toBe('无权限执行该操作')
    expect(ElMessage.warning).toHaveBeenCalledWith('无权限执行该操作')
  })

  it('showRetry 属性应正确反映不同状态码的重试策略', () => {
    const r401 = showHttpFeedback({ response: { status: 401 } }, 'f')
    const r403 = showHttpFeedback({ response: { status: 403 } }, 'f')
    const r404 = showHttpFeedback({ response: { status: 404 } }, 'f')
    const r422 = showHttpFeedback({ response: { status: 422 } }, 'f')
    const r500 = showHttpFeedback({ response: { status: 500 } }, 'f')

    expect(r401.showRetry).toBe(false)
    expect(r403.showRetry).toBe(false)
    expect(r404.showRetry).toBe(true)
    expect(r422.showRetry).toBe(false)
    expect(r500.showRetry).toBe(true)
  })
})
