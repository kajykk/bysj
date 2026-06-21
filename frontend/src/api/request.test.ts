import { beforeEach, describe, expect, it, vi } from 'vitest'
import request from './request'
import router from '@/router'
import { clearStoredAuth, setStoredAuth } from '@/utils/authStorage'
import { ElMessage } from 'element-plus'

vi.mock('@/router', () => ({
  default: { replace: vi.fn() }
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: vi.fn(),
    error: vi.fn()
  }
}))

describe('request interceptor auth handling', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    clearStoredAuth()
  })

  it('attaches bearer token when present', async () => {
    setStoredAuth({ token: 'abc123' })
    const interceptor = (request.interceptors.request as any).handlers[0].fulfilled
    const config = await interceptor({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer abc123')
  })

  it('exposes router mock for redirect assertions', () => {
    expect(router.replace).toBeDefined()
  })

  it('reads refresh token through the shared storage helper', async () => {
    setStoredAuth({ refreshToken: 'refresh-xyz' })
    expect(localStorage.getItem('refreshToken')).toBe('refresh-xyz')
  })

  it('exposes warning message handler mock', () => {
    expect(ElMessage.warning).toBeDefined()
  })
})
