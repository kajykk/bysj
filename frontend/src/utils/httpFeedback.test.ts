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
})
