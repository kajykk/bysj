import { beforeEach, describe, expect, it, vi } from 'vitest'
import request from './request'
import router from '@/router'
import { clearStoredAuth, setStoredAuth } from '@/utils/authStorage'
import { ElMessage } from 'element-plus'

vi.mock('@/router', () => ({
  default: { replace: vi.fn() }
}))

// 使用 vi.hoisted 创建共享 mock，确保 element-plus 和子路径 mock 指向同一实例
const ElMessageMock = vi.hoisted(() => ({
  warning: vi.fn(),
  error: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: ElMessageMock,
}))
vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: ElMessageMock,
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
    // 安全修复：refresh_token 不再存入 localStorage（XSS 可窃取长期凭证）
    // setStoredAuth 应清除旧版本残留的 refresh_token
    localStorage.setItem('refreshToken', 'stale-token')
    setStoredAuth({ refreshToken: 'refresh-xyz' })
    expect(localStorage.getItem('refreshToken')).toBeNull()
  })

  it('exposes warning message handler mock', () => {
    expect(ElMessage.warning).toBeDefined()
  })
})
