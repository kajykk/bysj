import { beforeEach, describe, expect, it } from 'vitest'
import { clearStoredAuth, getStoredRefreshToken, getStoredToken, getStoredUser, setStoredAuth } from './authStorage'

describe('authStorage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('reads and writes token state consistently', () => {
    setStoredAuth({ token: 'access-1', refreshToken: 'refresh-1', user: { id: 1, username: 'alice', role: 'user' } })

    expect(getStoredToken()).toBe('access-1')
    expect(getStoredRefreshToken()).toBe('refresh-1')
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
})
