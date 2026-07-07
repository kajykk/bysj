// 类型下沉：从 @/types/auth 引用 UserInfo，避免通过 @/api/auth 引入类型-only 循环依赖
// （api/auth.ts -> api/request.ts -> utils/authStorage.ts 形成运行时链路）
import type { UserInfo } from '@/types/auth'

const TOKEN_KEY = 'token'
const REFRESH_TOKEN_KEY = 'refreshToken' // 保留常量用于清理旧数据，不再存储新 token
const USER_KEY = 'user'
const TOKEN_EXPIRY_KEY = 'token_expiry'

function _isStorageAvailable(storage: Storage): boolean {
  try {
    const testKey = '__storage_test__'
    storage.setItem(testKey, '1')
    storage.removeItem(testKey)
    return true
  } catch {
    return false
  }
}

const _localStorageAvailable = typeof window !== 'undefined' && _isStorageAvailable(window.localStorage)
const _sessionStorageAvailable = typeof window !== 'undefined' && _isStorageAvailable(window.sessionStorage)

// ISS-008 修复：access_token 改用 sessionStorage，关闭标签页即清除，缩小 XSS 攻击窗口
function _safeGetItem(key: string, useSession: boolean = false): string | null {
  const storage = useSession ? window.sessionStorage : window.localStorage
  const available = useSession ? _sessionStorageAvailable : _localStorageAvailable
  if (!available) return null
  return storage.getItem(key)
}

function _safeSetItem(key: string, value: string, useSession: boolean = false): void {
  const storage = useSession ? window.sessionStorage : window.localStorage
  const available = useSession ? _sessionStorageAvailable : _localStorageAvailable
  if (!available) return
  storage.setItem(key, value)
}

function _safeRemoveItem(key: string, useSession: boolean = false): void {
  const storage = useSession ? window.sessionStorage : window.localStorage
  const available = useSession ? _sessionStorageAvailable : _localStorageAvailable
  if (!available) return
  storage.removeItem(key)
}

function _isTokenExpired(): boolean {
  // ISS-008: token_expiry 也存入 sessionStorage
  const expiry = _safeGetItem(TOKEN_EXPIRY_KEY, true)
  if (!expiry) return false
  return Date.now() > parseInt(expiry, 10)
}

/**
 * M-26 修复：仅清除 token 相关数据，保留 user 信息。
 * token 过期时 user 信息仍有用（如显示用户名），不应一并清除。
 */
function _clearStoredToken(): void {
  _safeRemoveItem(TOKEN_KEY, true)
  _safeRemoveItem(TOKEN_EXPIRY_KEY, true)
  // ISS-008: 清理旧版本可能残留在 localStorage 中的 token
  _safeRemoveItem(TOKEN_KEY, false)
  _safeRemoveItem(TOKEN_EXPIRY_KEY, false)
}

export function getStoredToken(): string {
  if (_isTokenExpired()) {
    // M-26 修复：token 过期时只清除 token 相关数据，保留 user 信息
    _clearStoredToken()
    return ''
  }
  // ISS-008: 优先从 sessionStorage 读取，回退清理 localStorage 旧数据
  const token = _safeGetItem(TOKEN_KEY, true)
  if (token) return token
  // 清理旧版本可能残留在 localStorage 中的 token
  const legacyToken = _safeGetItem(TOKEN_KEY, false)
  if (legacyToken) {
    _safeRemoveItem(TOKEN_KEY, false)
    _safeRemoveItem(TOKEN_EXPIRY_KEY, false)
  }
  return ''
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
  _safeRemoveItem(REFRESH_TOKEN_KEY, false)
  return ''
}

/**
 * ISS-009 修复：从 UserInfo 中剥离 email 等敏感 PII 字段后再存储。
 * localStorage 中仅保留 UI 渲染所需的最小信息集（id/username/role/nickname）。
 */
function _sanitizeUserForStorage(user: UserInfo): Record<string, unknown> {
  const { email: _email, ...safeFields } = user
  return safeFields
}

export function getStoredUser(): UserInfo | null {
  const userRaw = _safeGetItem(USER_KEY, false)
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
      // ISS-008: token 存入 sessionStorage 而非 localStorage
      _safeSetItem(TOKEN_KEY, payload.token, true)
      if (payload.expiresIn) {
        _safeSetItem(TOKEN_EXPIRY_KEY, String(Date.now() + payload.expiresIn * 1000), true)
      }
    } else {
      _safeRemoveItem(TOKEN_KEY, true)
      _safeRemoveItem(TOKEN_EXPIRY_KEY, true)
      // ISS-008: 同时清理 localStorage 旧数据
      _safeRemoveItem(TOKEN_KEY, false)
      _safeRemoveItem(TOKEN_EXPIRY_KEY, false)
    }
  }

  // 安全修复：refresh_token 由后端 HttpOnly Cookie 管理，不再存入 localStorage
  // 清理旧版本可能残留的 refresh_token
  if (payload.refreshToken !== undefined) {
    _safeRemoveItem(REFRESH_TOKEN_KEY, false)
  }

  if (payload.user !== undefined) {
    if (payload.user) {
      // ISS-009: 剥离 email 等敏感 PII 后再存储
      _safeSetItem(USER_KEY, JSON.stringify(_sanitizeUserForStorage(payload.user)), false)
    } else {
      _safeRemoveItem(USER_KEY, false)
    }
  }
}

export function clearStoredAuth() {
  // ISS-008: 清理 sessionStorage 中的 token
  _safeRemoveItem(TOKEN_KEY, true)
  _safeRemoveItem(TOKEN_EXPIRY_KEY, true)
  // 同时清理 localStorage 中的旧数据
  _safeRemoveItem(TOKEN_KEY, false)
  _safeRemoveItem(REFRESH_TOKEN_KEY, false)
  _safeRemoveItem(USER_KEY, false)
  _safeRemoveItem(TOKEN_EXPIRY_KEY, false)
}
