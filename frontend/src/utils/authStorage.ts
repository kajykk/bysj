import type { UserInfo } from '@/api/auth'

const TOKEN_KEY = 'token'
const REFRESH_TOKEN_KEY = 'refreshToken' // 保留常量用于清理旧数据，不再存储新 token
const USER_KEY = 'user'
const TOKEN_EXPIRY_KEY = 'token_expiry'

function _isStorageAvailable(): boolean {
  try {
    const testKey = '__storage_test__'
    localStorage.setItem(testKey, '1')
    localStorage.removeItem(testKey)
    return true
  } catch {
    return false
  }
}

const _storageAvailable = _isStorageAvailable()

function _safeGetItem(key: string): string | null {
  if (!_storageAvailable) return null
  return localStorage.getItem(key)
}

function _safeSetItem(key: string, value: string): void {
  if (!_storageAvailable) return
  localStorage.setItem(key, value)
}

function _safeRemoveItem(key: string): void {
  if (!_storageAvailable) return
  localStorage.removeItem(key)
}

function _isTokenExpired(): boolean {
  const expiry = _safeGetItem(TOKEN_EXPIRY_KEY)
  if (!expiry) return false
  return Date.now() > parseInt(expiry, 10)
}

export function getStoredToken(): string {
  if (_isTokenExpired()) {
    clearStoredAuth()
    return ''
  }
  return _safeGetItem(TOKEN_KEY) || ''
}

/**
 * 获取存储的 refresh token。
 *
 * 安全修复：refresh_token 不再存储在 localStorage（XSS 可窃取长期凭证）。
 * 后端通过 HttpOnly+Secure+SameSite Cookie 设置 refresh_token，浏览器自动随请求发送。
 * 此函数仅用于清理旧数据，始终返回空字符串。
 */
export function getStoredRefreshToken(): string {
  // 清理旧版本可能残留的 refresh_token
  _safeRemoveItem(REFRESH_TOKEN_KEY)
  return ''
}

export function getStoredUser(): UserInfo | null {
  const userRaw = _safeGetItem(USER_KEY)
  if (!userRaw) return null

  try {
    return JSON.parse(userRaw) as UserInfo
  } catch {
    return null
  }
}

export function setStoredAuth(payload: {
  token?: string
  refreshToken?: string
  user?: UserInfo | null
  expiresIn?: number
}) {
  if (payload.token !== undefined) {
    if (payload.token) {
      _safeSetItem(TOKEN_KEY, payload.token)
      if (payload.expiresIn) {
        _safeSetItem(TOKEN_EXPIRY_KEY, String(Date.now() + payload.expiresIn * 1000))
      }
    } else {
      _safeRemoveItem(TOKEN_KEY)
      _safeRemoveItem(TOKEN_EXPIRY_KEY)
    }
  }

  // 安全修复：refresh_token 由后端 HttpOnly Cookie 管理，不再存入 localStorage
  // 清理旧版本可能残留的 refresh_token
  if (payload.refreshToken !== undefined) {
    _safeRemoveItem(REFRESH_TOKEN_KEY)
  }

  if (payload.user !== undefined) {
    if (payload.user) _safeSetItem(USER_KEY, JSON.stringify(payload.user))
    else _safeRemoveItem(USER_KEY)
  }
}

export function clearStoredAuth() {
  _safeRemoveItem(TOKEN_KEY)
  _safeRemoveItem(REFRESH_TOKEN_KEY)
  _safeRemoveItem(USER_KEY)
  _safeRemoveItem(TOKEN_EXPIRY_KEY)
}
