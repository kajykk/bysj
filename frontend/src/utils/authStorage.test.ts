import { beforeEach, describe, expect, it } from 'vitest'
import { clearStoredAuth, getStoredRefreshToken, getStoredToken, getStoredUser, setStoredAuth } from './authStorage'

describe('authStorage', () => {
  beforeEach(() => {
    // ISS-008 修复：token 现存于 sessionStorage，user 仍存于 localStorage
    localStorage.clear()
    sessionStorage.clear()
  })

  it('reads and writes token state consistently', () => {
    setStoredAuth({ token: 'access-1', refreshToken: 'refresh-1', user: { id: 1, username: 'alice', role: 'user' } })

    expect(getStoredToken()).toBe('access-1')
    // 安全修复：refresh_token 由后端 HttpOnly Cookie 管理，不再存入 localStorage
    expect(getStoredRefreshToken()).toBe('')
    expect(localStorage.getItem('refreshToken')).toBeNull()
    expect(getStoredUser()).toEqual({ id: 1, username: 'alice', role: 'user' })
  })

  it('clears all auth state', () => {
    setStoredAuth({ token: 'access-1', refreshToken: 'refresh-1', user: { id: 1, username: 'alice', role: 'user' } })
    clearStoredAuth()

    expect(getStoredToken()).toBe('')
    expect(getStoredRefreshToken()).toBe('')
    expect(getStoredUser()).toBeNull()
  })

  it('returns null for invalid stored user payloads', () => {
    localStorage.setItem('user', '{invalid json')
    expect(getStoredUser()).toBeNull()
  })

  // ===== ISS-008 修复：token 现存于 sessionStorage =====

  it('token 未过期时 getStoredToken 应返回存储的 token', () => {
    setStoredAuth({ token: 'valid-token', expiresIn: 3600 })
    expect(getStoredToken()).toBe('valid-token')
    // ISS-008: token_expiry 应写入 sessionStorage（非 localStorage）
    expect(sessionStorage.getItem('token_expiry')).not.toBeNull()
  })

  it('token 过期时 getStoredToken 应清除 token 并返回空字符串', () => {
    // 设置已过期的 token_expiry（1 秒前过期）— 存于 sessionStorage
    sessionStorage.setItem('token', 'expired-token')
    sessionStorage.setItem('token_expiry', String(Date.now() - 1000))

    expect(getStoredToken()).toBe('')
    // 过期后应清除 sessionStorage 中的 token 和 token_expiry
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('token_expiry')).toBeNull()
  })

  it('token_expiry 不存在时 getStoredToken 应正常返回 token（不过期检查）', () => {
    sessionStorage.setItem('token', 'no-expiry-token')
    // 不设置 token_expiry
    expect(getStoredToken()).toBe('no-expiry-token')
  })

  it('setStoredAuth 设置 expiresIn 应正确计算 token_expiry（存于 sessionStorage）', () => {
    const before = Date.now()
    setStoredAuth({ token: 'tok', expiresIn: 1800 })
    const after = Date.now()

    // ISS-008: token_expiry 应存于 sessionStorage
    const expiry = parseInt(sessionStorage.getItem('token_expiry')!, 10)
    expect(expiry).toBeGreaterThanOrEqual(before + 1800 * 1000)
    expect(expiry).toBeLessThanOrEqual(after + 1800 * 1000)
    // token 也应存于 sessionStorage
    expect(sessionStorage.getItem('token')).toBe('tok')
    // localStorage 不应包含 token
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('setStoredAuth 不传 expiresIn 时不应设置 token_expiry', () => {
    setStoredAuth({ token: 'tok' })
    expect(sessionStorage.getItem('token_expiry')).toBeNull()
  })

  it('setStoredAuth 传入 falsy token 时应清除 token 和 token_expiry', () => {
    sessionStorage.setItem('token', 'old-token')
    sessionStorage.setItem('token_expiry', '9999999999999')

    setStoredAuth({ token: '' })

    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('token_expiry')).toBeNull()
  })

  it('setStoredAuth 传入 refreshToken 时应清理旧的 refresh_token 残留', () => {
    localStorage.setItem('refreshToken', 'old-refresh-token')

    setStoredAuth({ refreshToken: 'new-refresh' })

    // 安全修复：refresh_token 不再存储在 localStorage
    expect(localStorage.getItem('refreshToken')).toBeNull()
  })

  it('setStoredAuth 不传 refreshToken 时不应影响已存储的 refresh_token', () => {
    localStorage.setItem('refreshToken', 'existing-refresh')

    setStoredAuth({ token: 'tok' })

    // 不传 refreshToken 字段时不应清理
    expect(localStorage.getItem('refreshToken')).toBe('existing-refresh')
  })

  it('setStoredAuth 传入 user=null 时应清除 user', () => {
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'a', role: 'user' }))

    setStoredAuth({ user: null })

    expect(localStorage.getItem('user')).toBeNull()
  })

  it('setStoredAuth 传入有效 user 时应写入 JSON 序列化后的值（剥离 email）', () => {
    const user = { id: 5, username: 'bob', role: 'counselor' as const, nickname: 'Bob', email: 'bob@example.com' }

    setStoredAuth({ user })

    const stored = localStorage.getItem('user')
    expect(stored).not.toBeNull()
    // ISS-009: email 字段应被剥离
    const parsed = JSON.parse(stored!) as Record<string, unknown>
    expect(parsed).not.toHaveProperty('email')
    // 其他字段应保留
    expect(parsed.id).toBe(5)
    expect(parsed.username).toBe('bob')
    expect(parsed.role).toBe('counselor')
    expect(parsed.nickname).toBe('Bob')
  })

  it('setStoredAuth 不传 token 字段时不应影响已存储的 token', () => {
    sessionStorage.setItem('token', 'existing-token')

    setStoredAuth({ user: { id: 1, username: 'a', role: 'user' } })

    expect(sessionStorage.getItem('token')).toBe('existing-token')
  })

  it('setStoredAuth 不传 user 字段时不应影响已存储的 user', () => {
    const existingUser = JSON.stringify({ id: 1, username: 'a', role: 'user' })
    localStorage.setItem('user', existingUser)

    setStoredAuth({ token: 'new-tok' })

    expect(localStorage.getItem('user')).toBe(existingUser)
  })

  it('getStoredRefreshToken 应清理旧 refresh_token 残留并返回空字符串', () => {
    localStorage.setItem('refreshToken', 'stale-refresh-token')

    const result = getStoredRefreshToken()

    expect(result).toBe('')
    expect(localStorage.getItem('refreshToken')).toBeNull()
  })

  it('getStoredUser 在无 user 存储时应返回 null', () => {
    expect(getStoredUser()).toBeNull()
  })

  it('getStoredToken 在无 token 存储时应返回空字符串', () => {
    expect(getStoredToken()).toBe('')
  })

  it('clearStoredAuth 应清除所有 auth 相关 key（含 sessionStorage 和 localStorage）', () => {
    sessionStorage.setItem('token', 'tok')
    localStorage.setItem('refreshToken', 'rt')
    localStorage.setItem('user', '{"id":1}')
    sessionStorage.setItem('token_expiry', '9999')

    clearStoredAuth()

    // sessionStorage 中的 token 应被清除
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('token_expiry')).toBeNull()
    // localStorage 中的旧数据也应被清除
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('refreshToken')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(localStorage.getItem('token_expiry')).toBeNull()
  })

  it('完整流程：登录→读取→过期→清除', () => {
    // 模拟登录
    setStoredAuth({
      token: 'access-token',
      expiresIn: 1, // 1 秒后过期
      user: { id: 1, username: 'alice', role: 'user' },
    })

    // 立即读取应正常
    expect(getStoredToken()).toBe('access-token')
    expect(getStoredUser()?.username).toBe('alice')

    // 模拟 token 过期（sessionStorage）
    sessionStorage.setItem('token_expiry', String(Date.now() - 1))

    // 过期后读取应返回空并清除
    expect(getStoredToken()).toBe('')
    expect(sessionStorage.getItem('token')).toBeNull()

    // M-26 修复：token 过期后 user 信息应保留
    expect(getStoredUser()?.username).toBe('alice')
  })

  // ===== ISS-008 回归测试：token 必须存于 sessionStorage 而非 localStorage =====

  it('ISS-008: setStoredAuth 写入 token 时应存入 sessionStorage 而非 localStorage', () => {
    setStoredAuth({ token: 'session-only-token' })

    expect(sessionStorage.getItem('token')).toBe('session-only-token')
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('ISS-008: getStoredToken 应优先从 sessionStorage 读取', () => {
    sessionStorage.setItem('token', 'session-token')

    expect(getStoredToken()).toBe('session-token')
  })

  it('ISS-008: getStoredToken 应清理 localStorage 中残留的旧 token', () => {
    // 模拟旧版本数据残留在 localStorage
    localStorage.setItem('token', 'legacy-local-token')
    localStorage.setItem('token_expiry', String(Date.now() + 999999))

    // getStoredToken 应清理 localStorage 旧数据并返回空字符串
    const result = getStoredToken()

    expect(result).toBe('')
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('token_expiry')).toBeNull()
  })

  it('ISS-008: 关闭标签页时 sessionStorage 自动清除（模拟）', () => {
    setStoredAuth({
      token: 'ephemeral-token',
      user: { id: 1, username: 'alice', role: 'user' },
    })
    expect(sessionStorage.getItem('token')).toBe('ephemeral-token')

    // 模拟关闭标签页：sessionStorage 被清空，localStorage 保留
    sessionStorage.clear()

    expect(getStoredToken()).toBe('')
    // user 仍应保留在 localStorage
    expect(localStorage.getItem('user')).not.toBeNull()
  })

  // ===== ISS-009 回归测试：email 字段必须从存储中剥离 =====

  it('ISS-009: setStoredAuth 存储 user 时应剥离 email 字段', () => {
    const user = {
      id: 10,
      username: 'alice',
      role: 'user' as const,
      email: 'alice@example.com',
      nickname: 'Alice',
    }

    setStoredAuth({ user })

    const stored = localStorage.getItem('user')
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored!) as Record<string, unknown>
    expect(parsed).not.toHaveProperty('email')
    expect(parsed.username).toBe('alice')
  })

  it('ISS-009: getStoredUser 读取的 user 数据不应包含 email 字段', () => {
    const user = {
      id: 11,
      username: 'bob',
      role: 'counselor' as const,
      email: 'bob@example.com',
    }

    setStoredAuth({ user })
    const stored = getStoredUser()

    expect(stored).not.toBeNull()
    expect(stored).not.toHaveProperty('email')
    expect(stored?.username).toBe('bob')
  })

  it('ISS-009: user 不含 email 时存储应正常工作', () => {
    const user = { id: 12, username: 'no-email', role: 'user' as const }

    setStoredAuth({ user })

    const stored = getStoredUser()
    expect(stored).toEqual(user)
    expect(stored).not.toHaveProperty('email')
  })
})
