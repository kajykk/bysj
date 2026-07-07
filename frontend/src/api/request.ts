import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
// R-003 修复：基础文件 (请求层) 显式导入 ElMessage，避免依赖 unplugin-auto-import
// 隐式注入导致测试环境需 globalThis hack、生产环境配置失效时静默失败的可靠性问题。
// 页面/组件层仍可使用 auto-import，仅基础文件强制显式导入以保障运行时确定性。
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types/api'
import { normalizePageResult, type UnifiedPageResult } from '@/types/contracts'
import { clearStoredAuth, getStoredToken, setStoredAuth } from '@/utils/authStorage'
import { normalizeHttpErrorInfo } from '@/utils/httpError'
import { API_BASE_URL, buildApiUrl } from './base'
import i18n from '@/i18n'

const t = i18n.global.t.bind(i18n.global)

// H-FE-8 修复：扩展 config 类型，支持 bypassDedupe 选项（H-FE-2）
export type DedupeableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean
  bypassDedupe?: boolean
}

const AUTH_SYNC_EVENT = 'auth-sync'

export const DEFAULT_API_TIMEOUT_MS = 60000
export const LONG_RUNNING_API_TIMEOUT_MS = 420000

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: DEFAULT_API_TIMEOUT_MS
})

// H-15 修复：检查 _retry 标志跳过，避免覆盖 refresh 请求中清空的 Authorization 头
request.interceptors.request.use((config: InternalAxiosRequestConfig & { _retry?: boolean }) => {
  if (config._retry) {
    return config
  }
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
// FH-01 修复：为 pending 请求增加防御性超时。
// 即使 refreshAccessToken 出现未预期异常导致 Promise 永不 settle，
// pending 请求也会在 DEFENSIVE_PENDING_TIMEOUT_MS 后被拒绝，避免无限挂起。
// C-FE-3 修复：原值 15000 短于 DEFAULT_API_TIMEOUT_MS(60s)/LONG_RUNNING_API_TIMEOUT_MS(420s)，
// 导致长超时任务在 15s 后被拒绝但 refresh 仍在进行，后续重试永远无法完成。设为 65000 对齐默认超时。
const DEFENSIVE_PENDING_TIMEOUT_MS = 65000
type PendingEntry = {
  resolve: (value: unknown) => void
  reject: (reason?: unknown) => void
  request: InternalAxiosRequestConfig & { _retry?: boolean }
  timer: ReturnType<typeof setTimeout> | null
}
let pendingRequests: PendingEntry[] = []

function broadcastAuthSync(payload: { token?: string; refreshToken?: string; user?: unknown }) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(AUTH_SYNC_EVENT, { detail: payload }))
}

export async function refreshAccessToken(): Promise<string | null> {
  // 安全修复：refresh_token 由后端 HttpOnly Cookie 管理，不再从 localStorage 读取
  // 浏览器会自动随请求发送 Cookie（withCredentials 或同源场景）
  // 后端 /auth/refresh 端点优先从 Cookie 读取 refresh_token

  try {
    // P1-E 修复：使用封装的 request 实例替代裸 axios.post，
    // 确保统一 baseURL/timeout/拦截器配置；通过 _retry=true 避免 401 重试递归
    // token 刷新需要独立超时，避免在全局 60s 超时下卡住后续请求
    // C-FE-2 修复：删除 headers: { Authorization: '' }。
    // 原实现发送空字符串 Authorization 头，部分后端将空值视为非法 token 返回 401，
    // 导致刷新永远失败。_retry=true 已让请求拦截器跳过 token 注入（见上方 if (config._retry) return config），
    // 无需再手动清空头。refresh_token 仅通过 HttpOnly Cookie 传递。
    const { data } = await request.post(buildApiUrl('/auth/refresh'), {}, {
      _retry: true,
      timeout: 10000,
      withCredentials: true, // 确保发送 HttpOnly Cookie
    } as InternalAxiosRequestConfig & { _retry?: boolean })
    const newToken = data?.data?.access_token
    const newUser = data?.data?.user
    if (!newToken) return null

    // refresh_token 由后端通过 Set-Cookie 响应头更新，前端无需存储
    setStoredAuth({ token: newToken, user: newUser })
    broadcastAuthSync({ token: newToken, user: newUser })
    return newToken
  } catch (error) {
    // P2-C 修复：记录 token 刷新失败原因，便于排查网络/服务异常（不改变返回 null 的行为）
    console.warn('[refreshAccessToken] token refresh failed:', error)
    return null
  }
}

function flushPendingRequests(token: string) {
  pendingRequests.forEach(({ resolve, request: originalRequest, timer }) => {
    if (timer) clearTimeout(timer)
    originalRequest.headers.Authorization = `Bearer ${token}`
    resolve(request(originalRequest))
  })
  pendingRequests = []
}

function rejectPendingRequests(error: unknown) {
  pendingRequests.forEach(({ reject, timer }) => {
    if (timer) clearTimeout(timer)
    reject(error)
  })
  pendingRequests = []
}

let isUnauthorizedRedirecting = false

// 循环依赖治理：通过回调注入 router.replace，取代原先的动态 import('@/router')。
// 原动态 import 与 router/index.ts -> @/api/request 的静态 import 形成循环依赖
// （madge 报告 22 条相关循环）。改由 main.ts 在启动时注入回调，request.ts 不再静态或动态依赖 @/router，
// 所有以 request.ts -> router 为枢纽的循环均被打破。
type RedirectHandler = () => void
let redirectHandler: RedirectHandler | null = null

export function setRedirectToLogin(handler: RedirectHandler | null): void {
  redirectHandler = handler
}

// M-FE-4 修复：导出复位函数，供 router.afterEach 在导航完成后复位标志，
// 避免标志永久置位导致后续合法 401 跳转被抑制
export function resetUnauthorizedRedirecting() {
  isUnauthorizedRedirecting = false
}

function clearAuthState() {
  clearStoredAuth()
  broadcastAuthSync({ token: '', refreshToken: '', user: null })
}

function redirectToLogin(message = t('errorPolicy.loginExpired')) {
  if (!isUnauthorizedRedirecting && window.location.pathname !== '/login') {
    isUnauthorizedRedirecting = true
    ElMessage.warning(message)
    // 通过注入的回调执行跳转，避免直接依赖 @/router 形成循环依赖
    if (redirectHandler) {
      redirectHandler()
    } else {
      // 兜底：尚未注入回调时（理论上 main.ts 已在 mount 前注入），回退到硬跳转以避免卡死
      // R-002 修复：保留完整 URL（pathname + search + hash），登录后可恢复 query/hash 上下文。
      const { pathname, search, hash } = window.location
      window.location.assign(`/login?redirect=${encodeURIComponent(pathname + search + hash)}`)
    }
  }
}

request.interceptors.response.use(
  (response) => {
    isUnauthorizedRedirecting = false
    return response
  },
  async (error: AxiosError<{ detail?: string; message?: string }>) => {
    // BUG-005 修复：传空 fallback，让 detail 在后端未返回具体错误时为空字符串，
    // 这样下方状态码特定提示（'无权限执行该操作' 等）才能通过 `detail || '...'` 生效。
    // 原实现传 '请求失败' 作为 fallback，detail 永远非空，状态码特定提示变为死代码。
    const { status, detail } = normalizeHttpErrorInfo(error, '')
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (status === 401 && originalRequest && !originalRequest._retry) {
      if (isRefreshing) {
        // 修复：为 pending 请求设置 _retry 标志，防止重试后再次 401 时触发重复刷新循环
        originalRequest._retry = true
        return new Promise((resolve, reject) => {
          // FH-01 修复：防御性超时，避免 refreshAccessToken 异常导致 pending 请求永久挂起
          const timer = setTimeout(() => {
            // 超时后从队列移除（若仍在队列中），避免 flush/reject 重复处理
            const idx = pendingRequests.findIndex((entry) => entry.timer === timer)
            if (idx >= 0) pendingRequests.splice(idx, 1)
            reject(new Error(t('errorPolicy.tokenRefreshTimeout')))
          }, DEFENSIVE_PENDING_TIMEOUT_MS)
          pendingRequests.push({ resolve, reject, request: originalRequest, timer })
        })
      }

      originalRequest._retry = true
      isRefreshing = true
      try {
        const newToken = await refreshAccessToken()
        if (newToken) {
          flushPendingRequests(newToken)
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return request(originalRequest)
        }
      } finally {
        isRefreshing = false
      }

      rejectPendingRequests(error)
      clearAuthState()
      redirectToLogin()
      return Promise.reject(error)
    }

    if (status === 401) {
      clearAuthState()
      redirectToLogin(detail || t('errorPolicy.loginExpired'))
      return Promise.reject(error)
    }

    if (status === 403) {
      ElMessage.warning(detail || t('errorPolicy.noPermission'))
      return Promise.reject(error)
    }

    if (status === 404) {
      ElMessage.warning(detail || t('errorPolicy.notFound'))
      return Promise.reject(error)
    }

    if (status === 422) {
      ElMessage.warning(detail || t('errorPolicy.validationFailed'))
      return Promise.reject(error)
    }

    if (status >= 500) {
      ElMessage.error(detail || t('errorPolicy.serverError'))
      return Promise.reject(error)
    }

    ElMessage.error(detail || t('errorPolicy.requestFailed'))
    return Promise.reject(error)
  }
)

// L-28 修复：GET 请求去重，相同 URL+params 的并发 GET 请求复用同一个 Promise
// 仅对 GET 请求去重；POST/PUT/DELETE 等可能有副作用，不做去重
const inflightRequests = new Map<string, Promise<unknown>>()

/**
 * R-004 修复：稳定序列化 GET 去重 key
 *
 * 原实现 `JSON.stringify(params, sortedKeys)` 仅对顶层 key 排序，存在以下歧义风险：
 *   - 嵌套对象 key 顺序不同但语义相同：`{a: {x: 1, y: 2}}` 与 `{a: {y: 2, x: 1}}`
 *     会生成不同字符串，导致语义相同的请求被重复发送。
 *   - 数组顺序语义重要：`{tags: ['a', 'b']}` 与 `{tags: ['b', 'a']}` 应生成不同字符串。
 *
 * 本函数递归排序对象 key，保留数组顺序，与 JSON.stringify 边界行为对齐
 * （对象中的 undefined 值跳过该 key，数组中的 undefined 视为 null）。
 */
function stableSerialize(value: unknown): string {
  if (value === null) return 'null'
  if (value === undefined) return 'null'
  if (typeof value !== 'object') {
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    // 数组保留元素顺序（语义重要），仅递归处理每个元素
    return `[${value.map(stableSerialize).join(',')}]`
  }
  if (value instanceof Date) {
    return JSON.stringify(value.toISOString())
  }
  // 普通对象：递归排序 key，与 JSON.stringify 一致跳过 undefined 值
  const obj = value as Record<string, unknown>
  const pairs = Object.keys(obj)
    .sort()
    .filter((key) => obj[key] !== undefined)
    .map((key) => `${JSON.stringify(key)}:${stableSerialize(obj[key])}`)
  return `{${pairs.join(',')}}`
}

function getRequestKey(config: InternalAxiosRequestConfig | Record<string, unknown>): string {
  const method = String(config?.method || 'get').toLowerCase()
  if (method === 'get') {
    // R-004 修复：使用 stableSerialize 递归排序 key，支持复杂参数（嵌套对象/数组）的稳定去重。
    // 原 M-FE-3 修复仅排序顶层 key，复杂参数场景仍有歧义风险。
    const params = config?.params ?? {}
    return `${method}:${config?.url}:${stableSerialize(params)}`
  }
  return ''
}

// 包装 axios 实例的 request 方法以实现 GET 去重
// 拦截器（token 注入、401 刷新、错误提示）仍由原始 request 方法内部驱动
const originalRequestMethod = request.request.bind(request)
;(request as unknown as { request: (config: DedupeableRequestConfig) => Promise<unknown> }).request = function (config: DedupeableRequestConfig) {
  // _retry 请求（如 401 刷新后重试）跳过去重，确保重试真正执行，
  // 避免返回 inflight Promise 造成自引用导致永久挂起
  // H-FE-2 修复：bypassDedupe=true 时跳过去重，避免实时数据接口在 refresh 期间被阻塞
  const key = config?._retry || config?.bypassDedupe ? '' : getRequestKey(config || {})
  if (key) {
    const existing = inflightRequests.get(key)
    if (existing) {
      // 复用进行中的相同 GET 请求，避免重复发送
      return existing
    }
  }
  const promise = originalRequestMethod(config)
  if (key) {
    inflightRequests.set(key, promise)
    // 请求完成（成功或失败）后清除 inflight 记录，避免内存泄漏及后续相同请求被错误复用
    promise.finally(() => {
      inflightRequests.delete(key)
    })
  }
  return promise
}

// BUG-006 修复：axios 1.x 中 request.get()/delete()/head()/options() 等便捷方法
// 内部调用 Axios.prototype.request（原型方法），不经过实例上的 request.request override，
// 导致 GET 去重逻辑被绕过。显式重写 GET 类便捷方法，确保去重对所有调用方式生效。
// POST/PUT/PATCH 不去重，无需重写。
const DEDUPE_METHODS = ['get', 'delete', 'head', 'options'] as const
type DedupeMethod = (typeof DEDUPE_METHODS)[number]
type DedupeShortcutConfig = AxiosRequestConfig & {
  _retry?: boolean
  bypassDedupe?: boolean
}

const dedupeShortcuts = request as unknown as Record<DedupeMethod, (url: string, config?: DedupeShortcutConfig) => Promise<unknown>>

for (const method of DEDUPE_METHODS) {
  dedupeShortcuts[method] = function (
    url: string,
    config?: DedupeShortcutConfig,
  ) {
    return request.request({ ...(config || {}), method, url })
  }
}

export async function requestData<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const res = await promise
  return res.data.data
}

export async function requestPageData<T>(promise: Promise<{ data: ApiResponse<unknown> }>): Promise<UnifiedPageResult<T>> {
  const res = await promise
  return normalizePageResult<T>(res.data.data)
}

export default request
