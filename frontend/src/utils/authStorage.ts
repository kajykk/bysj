// 类型下沉：从 @/types/auth 引用 UserInfo，避免通过 @/api/auth 引入类型-only 循环依赖
// （api/auth.ts -> api/request.ts -> utils/authStorage.ts 形成运行时链路）
import type { UserInfo } from '@/types/auth'
import { isKnownRole, type UserRole } from '@/utils/roles'

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

// ISS-097 修复：解析 JWT 的 exp 字段（Unix 秒 → 毫秒时间戳）。
// 兼容非标准 base64url 编码：缺失 padding、-/_ 与 +// 混用，以及 "Bearer x.y.z" 前缀。
// 非 JWT 或解析失败返回 null（交由 token_expiry / 调用方判定）。
/**
 * 解码 JWT payload 段（不做签名校验——签名校验只在后端做）。
 *
 * 兼容非标准 base64url 编码：缺失 padding、-/_ 与 +// 混用，以及
 * "Bearer x.y.z" 前缀。任何一步失败返回 null。
 */
function _decodeJwtPayload(token: string): Record<string, unknown> | null {
  const compact = token.trim().replace(/^Bearer\s+/i, '')
  const parts = compact.split('.')
  if (parts.length < 3) return null

  let raw = parts[1].replace(/-/g, '+').replace(/_/g, '/')
  raw += '='.repeat((4 - (raw.length % 4)) % 4)

  let decoded: string | null = null
  try {
    decoded = typeof atob === 'function' ? atob(raw) : Buffer.from(raw, 'base64').toString('utf-8')
  } catch {
    return null
  }
  if (!decoded) return null

  try {
    const payload: unknown = JSON.parse(decoded)
    return payload && typeof payload === 'object'
      ? (payload as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

export function parseJwtExpiry(token: string): number | null {
  const payload = _decodeJwtPayload(token)
  if (!payload) return null
  return typeof payload.exp === 'number' && Number.isFinite(payload.exp)
    ? payload.exp * 1000
    : null
}

/**
 * M26 修复（ROUND_23）：从 access_token 的 JWT claims 取角色。
 *
 * 为什么它是「已验证来源」：access_token 由后端签发（HS256，
 * `auth_service.py` 的 claims 含 `role`），前端改不动 payload——
 * 改了签名校验也必在后端失败。相对地，localStorage 里的 `user`
 * 是 DevTools 随手可改的**占位值**，不能单独支撑权限决策。
 *
 * 返回值经 `isKnownRole` 校验（未知角色视为无凭证，fail-closed）。
 */
export function parseJwtRole(token: string): UserRole | null {
  const payload = _decodeJwtPayload(token)
  if (!payload) return null
  const role: unknown = payload.role
  return isKnownRole(role) ? role : null
}

function _isTokenExpired(): boolean {
  // ISS-008: token_expiry 也存入 sessionStorage
  const expiry = _safeGetItem(TOKEN_EXPIRY_KEY, true)
  if (expiry && Date.now() > parseInt(expiry, 10)) return true

  // ISS-097 修复：token_expiry 缺失时（旧会话 / 后端未下发 expires_in），
  // 回退解析 JWT payload 的 exp，避免携带已过期 token
  const token = _safeGetItem(TOKEN_KEY, true) ?? _safeGetItem(TOKEN_KEY, false)
  if (!token) return false
  const jwtExpiry = parseJwtExpiry(token)
  return jwtExpiry !== null && Date.now() >= jwtExpiry
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

/**
 * M26 修复（ROUND_23）：存储的 user 经 schema 校验后才落地为 `UserInfo`。
 *
 * 修前是 `JSON.parse(userRaw) as UserInfo`——`as` 只是类型断言，**不做任何
 * 运行时校验**：DevTools 里把 localStorage 的 user 改成
 * `{"role":"super_admin"}` 就能让前端按超管渲染（后台结构暴露）。
 * 校验规则（任一条不过即丢弃并回落到 null，绝不抛异常）：
 *   1. 必须是对象；
 *   2. 字段白名单（id/username/role/nickname）——拒绝任何额外字段，
 *      顺带挡住被塞回的 email 等 PII；
 *   3. 必填字段类型与取值（id 正整数、username 非空串、role 须
 *      `isKnownRole` 命中）；
 *   4. nickname 若存在必须是字符串。
 *
 * 注意：这里的校验只是**前端 UI 层**的自保，真实数据仍由后端 403 拦截
 * （见 docs/P2_23B_FRONTEND_AUDIT.md 的边界声明）。
 */
const USER_ALLOWED_FIELDS: readonly string[] = ['id', 'username', 'role', 'nickname']

function _isValidStoredUser(value: unknown): value is UserInfo {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const obj = value as Record<string, unknown>
  for (const key of Object.keys(obj)) {
    if (!USER_ALLOWED_FIELDS.includes(key)) return false
  }
  if (typeof obj.id !== 'number' || !Number.isInteger(obj.id) || obj.id <= 0) return false
  if (typeof obj.username !== 'string' || obj.username === '') return false
  if (!isKnownRole(obj.role)) return false
  if (obj.nickname !== undefined && typeof obj.nickname !== 'string') return false
  return true
}

export function getStoredUser(): UserInfo | null {
  const userRaw = _safeGetItem(USER_KEY, false)
  if (!userRaw) return null

  try {
    const parsed: unknown = JSON.parse(userRaw)
    return _isValidStoredUser(parsed) ? parsed : null
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
