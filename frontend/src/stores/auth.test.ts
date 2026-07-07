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
    // ISS-008 修复：token 现存于 sessionStorage，需同时清理两个 storage
    localStorage.clear()
    sessionStorage.clear()
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
    // 安全修复：refresh_token 由后端 HttpOnly Cookie 管理，前端不再存储
    expect(store.refreshToken).toBe('')
    expect(store.user?.username).toBe('alice')
    expect(sessionStorage.getItem('token')).toBe('access-1')
    expect(localStorage.getItem('refreshToken')).toBeNull()
  })

  it('refreshSession updates tokens and preserves user', async () => {
    const { refreshAccessToken } = await import('@/api/request')
    sessionStorage.setItem('token', 'access-old')
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
    sessionStorage.setItem('token', 'access-old')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))

    vi.mocked(refreshAccessToken).mockResolvedValue(null)
    vi.mocked(authApi.logout).mockResolvedValue({ message: 'ok', revoked_count: 1 })

    const store = useAuthStore()
    const ok = await store.refreshSession()

    expect(ok).toBe(false)
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    // 安全修复：refresh_token 不再存储在前端，logout 不携带 refresh_token
    expect(authApi.logout).toHaveBeenCalledWith({})
  })

  it('logout clears state and revokes refresh token when present', async () => {
    sessionStorage.setItem('token', 'access-old')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    vi.mocked(authApi.logout).mockResolvedValue({ message: 'ok', revoked_count: 1 })

    const store = useAuthStore()
    await store.logout()

    // 安全修复：refresh_token 不再存储在前端，logout 不携带 refresh_token
    expect(authApi.logout).toHaveBeenCalledWith({})
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('refreshToken')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })

  // ===== 新增测试：覆盖 register / restore / sync listener / persistAuth / broadcastAuthSync =====

  it('register 调用 authApi.register 并传递完整 payload', async () => {
    vi.mocked(authApi.register).mockResolvedValue({} as never)
    const store = useAuthStore()

    const payload = {
      username: 'bob',
      email: 'bob@example.com',
      password: 'secret',
      role: 'user' as const,
      nickname: 'Bob',
    }
    await store.register(payload)

    expect(authApi.register).toHaveBeenCalledWith(payload)
  })

  it('register 支持 counselor 角色', async () => {
    vi.mocked(authApi.register).mockResolvedValue({} as never)
    const store = useAuthStore()

    const payload = {
      username: 'counselor1',
      email: 'c@example.com',
      password: 'secret',
      role: 'counselor' as const,
    }
    await store.register(payload)

    expect(authApi.register).toHaveBeenCalledWith(payload)
  })

  it('restore 在 token 和 user 均有效时保留状态', () => {
    sessionStorage.setItem('token', 'valid-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))

    const store = useAuthStore()
    store.restore()

    expect(store.token).toBe('valid-token')
    expect(store.user?.username).toBe('alice')
  })

  it('restore 在 token 缺失时清除所有 auth 状态', () => {
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    // 不设置 token

    const store = useAuthStore()
    store.restore()

    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('restore 在 user 缺失时清除所有 auth 状态', () => {
    sessionStorage.setItem('token', 'valid-token')
    // 不设置 user

    const store = useAuthStore()
    store.restore()

    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
  })

  it('persistAuth 应同时写入 localStorage 并更新 store 状态', () => {
    const store = useAuthStore()

    store.persistAuth({
      token: 'persisted-token',
      user: { id: 2, username: 'bob', role: 'counselor' },
    })

    expect(store.token).toBe('persisted-token')
    expect(store.user?.username).toBe('bob')
    expect(sessionStorage.getItem('token')).toBe('persisted-token')
    expect(localStorage.getItem('user')).not.toBeNull()
  })

  it('persistAuth 设置 token 为空字符串时应清除 token', () => {
    sessionStorage.setItem('token', 'old-token')
    sessionStorage.setItem('token_expiry', '9999999999999')

    const store = useAuthStore()
    store.persistAuth({ token: '' })

    expect(store.token).toBe('')
    expect(sessionStorage.getItem('token')).toBeNull()
  })

  it('persistAuth 设置 user 为 null 时应清除 user', () => {
    localStorage.setItem('user', JSON.stringify({ id: 1 }))

    const store = useAuthStore()
    store.persistAuth({ user: null })

    expect(store.user).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('broadcastAuthSync 触发的 AUTH_SYNC_EVENT 应被同标签页监听器接收', () => {
    const store = useAuthStore()
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')

    store.broadcastAuthSync({ token: 'synced-token' })

    expect(dispatchSpy).toHaveBeenCalled()
    // 同标签页的 auth-sync listener 应已同步 token
    expect(store.token).toBe('synced-token')
  })

  it('broadcastAuthSync 设置 refreshToken 时应同步到 store', () => {
    const store = useAuthStore()

    store.broadcastAuthSync({ refreshToken: 'rt-value' })

    expect(store.refreshToken).toBe('rt-value')
  })

  it('broadcastAuthSync 设置 user 时应同步到 store', () => {
    const store = useAuthStore()
    const user = { id: 9, username: 'charlie', role: 'user' as const }

    store.broadcastAuthSync({ user })

    expect(store.user?.username).toBe('charlie')
  })

  it('storage 事件（key=null，模拟 localStorage.clear）应清空 auth 状态', () => {
    const store = useAuthStore()
    store.persistAuth({
      token: 'old-token',
      user: { id: 1, username: 'alice', role: 'user' },
    })

    // 触发 storage 事件，模拟其他标签页调用 localStorage.clear()
    window.dispatchEvent(
      new StorageEvent('storage', { key: null })
    )

    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
  })

  it('ISS-008: storage 事件（token key 变更）不应影响 store.token（token 已移至 sessionStorage）', () => {
    const store = useAuthStore()
    store.persistAuth({ token: 'original-token' })

    // 模拟其他标签页写入了新的 token 到 localStorage（旧版本残留）
    localStorage.setItem('token', 'legacy-token-from-other-tab')

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'token' })
    )

    // ISS-008: token 现存于 sessionStorage，storage 事件不处理 token key
    // store.token 应保持原值（由 BroadcastChannel 负责跨标签页同步）
    expect(store.token).toBe('original-token')
  })

  it('storage 事件（非 auth key 变更）不应影响 store 状态', () => {
    const store = useAuthStore()
    store.persistAuth({ token: 'my-token' })

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'unrelated-key' })
    )

    expect(store.token).toBe('my-token')
  })

  it('isLoggedIn 应反映 token 是否存在', () => {
    const store = useAuthStore()
    expect(store.isLoggedIn).toBe(false)

    store.persistAuth({ token: 'access-1' })
    expect(store.isLoggedIn).toBe(true)

    store.persistAuth({ token: '' })
    expect(store.isLoggedIn).toBe(false)
  })

  it('role 和 username 计算属性应基于 user 派生', () => {
    const store = useAuthStore()
    expect(store.role).toBe('')
    expect(store.username).toBe('')

    store.persistAuth({
      user: { id: 1, username: 'alice', role: 'counselor' },
    })
    expect(store.role).toBe('counselor')
    expect(store.username).toBe('alice')
  })

  // H-16 修复：测试跨标签页 storage 事件触发的认证同步
  // 注：onScopeDispose 由 Pinia 内部 effect scope 管理，不在测试 scope 中触发。
  // 此处通过直接调用 installAuthSyncListener 内部逻辑验证清理路径
  it('logout 在 authApi.logout 抛错时也应清除状态（finally 分支）', async () => {
    sessionStorage.setItem('token', 'access-old')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    vi.mocked(authApi.logout).mockRejectedValue(new Error('network error'))

    const store = useAuthStore()
    await expect(store.logout()).rejects.toThrow('network error')

    // 即使 logout API 失败，也应清除本地状态
    expect(store.token).toBe('')
    expect(store.refreshToken).toBe('')
    expect(store.user).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
  })

  // ===== 新增测试：覆盖 login 返回值/错误传播、register 错误传播、多字段同步 =====

  it('login 应返回 authApi.login 的响应数据', async () => {
    const mockResponse = {
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      user: { id: 1, username: 'alice', role: 'user' as const, nickname: 'Alice' },
    }
    vi.mocked(authApi.login).mockResolvedValue(mockResponse)

    const store = useAuthStore()
    const result = await store.login('alice', 'secret')

    expect(result).toEqual(mockResponse)
    expect(result.access_token).toBe('access-1')
    expect(result.user.username).toBe('alice')
  })

  it('login 在 authApi.login 抛错时应向上传播错误且不修改状态', async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error('invalid credentials'))

    const store = useAuthStore()
    // 初始状态应为空
    expect(store.token).toBe('')

    await expect(store.login('alice', 'wrong')).rejects.toThrow('invalid credentials')

    // 错误时不应修改 store 状态
    expect(store.token).toBe('')
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })

  it('login 在 authApi.login 抛出 HTTP 401 错误时应向上传播', async () => {
    const httpError = new Error('Unauthorized')
    vi.mocked(authApi.login).mockRejectedValue(httpError)

    const store = useAuthStore()
    await expect(store.login('alice', 'wrong')).rejects.toBe(httpError)
  })

  it('register 在 authApi.register 抛错时应向上传播错误', async () => {
    vi.mocked(authApi.register).mockRejectedValue(new Error('username already exists'))

    const store = useAuthStore()
    await expect(
      store.register({
        username: 'existing',
        email: 'e@example.com',
        password: 'secret',
        role: 'user',
      })
    ).rejects.toThrow('username already exists')
  })

  it('register 不传 nickname 时也应正常工作', async () => {
    vi.mocked(authApi.register).mockResolvedValue({} as never)
    const store = useAuthStore()

    const payload = {
      username: 'nonick',
      email: 'n@example.com',
      password: 'secret',
      role: 'user' as const,
    }
    await store.register(payload)

    expect(authApi.register).toHaveBeenCalledWith(payload)
  })

  it('persistAuth 同时设置 token、user 时应全部写入', () => {
    const store = useAuthStore()

    store.persistAuth({
      token: 'all-fields-token',
      user: { id: 10, username: 'multi', role: 'admin' },
    })

    expect(store.token).toBe('all-fields-token')
    expect(store.user?.username).toBe('multi')
    expect(store.user?.role).toBe('admin')
    expect(store.isLoggedIn).toBe(true)
    expect(store.role).toBe('admin')
  })

  it('persistAuth 同时设置 token、refreshToken、user 时应全部同步到 store', () => {
    const store = useAuthStore()

    store.persistAuth({
      token: 'tok',
      refreshToken: 'rt',
      user: { id: 1, username: 'u', role: 'user' },
    })

    expect(store.token).toBe('tok')
    // refreshToken 不存储在 localStorage，但同步到 store 内存
    expect(store.refreshToken).toBe('rt')
    expect(localStorage.getItem('refreshToken')).toBeNull()
  })

  it('broadcastAuthSync 同时设置 token、refreshToken、user 应全部同步', () => {
    const store = useAuthStore()

    store.broadcastAuthSync({
      token: 'sync-tok',
      refreshToken: 'sync-rt',
      user: { id: 7, username: 'synced', role: 'counselor' },
    })

    expect(store.token).toBe('sync-tok')
    expect(store.refreshToken).toBe('sync-rt')
    expect(store.user?.username).toBe('synced')
  })

  it('broadcastAuthSync 传入空对象时不应修改任何状态', () => {
    const store = useAuthStore()
    store.persistAuth({ token: 'original', user: { id: 1, username: 'orig', role: 'user' } })

    store.broadcastAuthSync({})

    expect(store.token).toBe('original')
    expect(store.user?.username).toBe('orig')
  })

  it('persistAuth 传入空对象时不应修改任何状态', () => {
    const store = useAuthStore()
    store.persistAuth({ token: 'original' })

    store.persistAuth({})

    expect(store.token).toBe('original')
  })

  it('storage 事件（user key 变更）应从 localStorage 重新读取 user', () => {
    const store = useAuthStore()

    localStorage.setItem('user', JSON.stringify({ id: 8, username: 'storage-user', role: 'user' }))

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'user' })
    )

    expect(store.user?.username).toBe('storage-user')
  })

  it('ISS-008: storage 事件（token_expiry key 变更）不应影响 store 状态', () => {
    const store = useAuthStore()
    store.persistAuth({ token: 'original-token' })

    sessionStorage.setItem('token_expiry', String(Date.now() + 999999))

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'token_expiry' })
    )

    // ISS-008: token_expiry 在 sessionStorage，storage 事件不处理此 key
    expect(store.token).toBe('original-token')
  })

  it('ISS-008: storage 事件（refreshToken key 变更）不应影响 store 状态', () => {
    const store = useAuthStore()
    store.persistAuth({ token: 'original-token' })

    localStorage.setItem('refreshToken', 'ignored')

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'refreshToken' })
    )

    // refreshToken 在 store 中始终为 ''（安全修复）
    expect(store.refreshToken).toBe('')
    // token 不应受影响
    expect(store.token).toBe('original-token')
  })

  it('多个 store 实例应通过 AUTH_SYNC_EVENT 同步状态', () => {
    const store1 = useAuthStore()

    // 创建第二个 store 实例（同 pinia，同 store id 应返回同一实例）
    const store2 = useAuthStore()

    // 通过 store1 广播变更
    store1.broadcastAuthSync({ token: 'shared-token' })

    // 两个 store 应共享状态（实际上是同一个实例）
    expect(store1.token).toBe('shared-token')
    expect(store2.token).toBe('shared-token')
  })

  it('restore 在 token 和 user 均有效时不应清除状态', () => {
    sessionStorage.setItem('token', 'valid-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))

    const store = useAuthStore()
    // store 初始化时已读取 storage
    expect(store.token).toBe('valid-token')

    // 再次调用 restore 应保持不变
    store.restore()
    expect(store.token).toBe('valid-token')
    expect(store.user?.username).toBe('alice')
  })

  it('login 应将 user 的 role 正确存入 store', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'tok',
      user: { id: 1, username: 'counselor1', role: 'counselor', nickname: 'C1' },
    })

    const store = useAuthStore()
    await store.login('counselor1', 'pass')

    expect(store.role).toBe('counselor')
    expect(store.username).toBe('counselor1')
  })

  it('login 应将 user 的 admin 角色正确存入 store', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'admin-tok',
      user: { id: 1, username: 'admin1', role: 'admin' },
    })

    const store = useAuthStore()
    await store.login('admin1', 'pass')

    expect(store.role).toBe('admin')
  })

  it('refreshSession 成功后 token 应更新但 user 应保留', async () => {
    const { refreshAccessToken } = await import('@/api/request')
    sessionStorage.setItem('token', 'old-token')
    localStorage.setItem('user', JSON.stringify({ id: 5, username: 'persist', role: 'user' }))

    vi.mocked(refreshAccessToken).mockResolvedValue('refreshed-token')

    const store = useAuthStore()
    const ok = await store.refreshSession()

    expect(ok).toBe(true)
    expect(store.token).toBe('refreshed-token')
    expect(store.user?.username).toBe('persist')
  })
})
