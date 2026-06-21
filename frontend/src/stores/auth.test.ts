import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { authApi } from '@/api/auth'
import { useAuthStore } from './auth'

vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    refresh: vi.fn(),
    logout: vi.fn(),
  },
}))

vi.mock('@/api/request', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/request')>()
  return {
    ...actual,
    refreshAccessToken: vi.fn(),
  }
})

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('login persists tokens and user', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      user: { id: 1, username: 'alice', role: 'user', nickname: 'Alice' },
    })

    const store = useAuthStore()
    await store.login('alice', 'secret')

    expect(store.token).toBe('access-1')
    expect(store.refreshToken).toBe('refresh-1')
    expect(store.user?.username).toBe('alice')
    expect(localStorage.getItem('token')).toBe('access-1')
    expect(localStorage.getItem('refreshToken')).toBe('refresh-1')
  })

  it('refreshSession updates tokens and preserves user', async () => {
    const { refreshAccessToken } = await import('@/api/request')
    localStorage.setItem('token', 'access-old')
    localStorage.setItem('refreshToken', 'refresh-old')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))

    vi.mocked(refreshAccessToken).mockResolvedValue('access-new')

    const store = useAuthStore()
    const ok = await store.refreshSession()

    expect(ok).toBe(true)
    expect(store.token).toBe('access-new')
    expect(store.user?.username).toBe('alice')
  })

  it('refreshSession logs out when refresh fails', async () => {
    const { refreshAccessToken } = await import('@/api/request')
    localStorage.setItem('token', 'access-old')
    localStorage.setItem('refreshToken', 'refresh-old')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))

    vi.mocked(refreshAccessToken).mockResolvedValue(null)
    vi.mocked(authApi.logout).mockResolvedValue({ message: 'ok', revoked_count: 1 })

    const store = useAuthStore()
    const ok = await store.refreshSession()

    expect(ok).toBe(false)
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(authApi.logout).toHaveBeenCalledWith({ refresh_token: 'refresh-old' })
  })

  it('logout clears state and revokes refresh token when present', async () => {
    localStorage.setItem('token', 'access-old')
    localStorage.setItem('refreshToken', 'refresh-old')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    vi.mocked(authApi.logout).mockResolvedValue({ message: 'ok', revoked_count: 1 })

    const store = useAuthStore()
    await store.logout()

    expect(authApi.logout).toHaveBeenCalledWith({ refresh_token: 'refresh-old' })
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('refreshToken')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })
})
