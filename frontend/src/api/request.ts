import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types/api'
import router from '@/router'
import { normalizePageResult, type UnifiedPageResult } from '@/types/contracts'
import { clearStoredAuth, getStoredToken, setStoredAuth } from '@/utils/authStorage'
import { normalizeHttpErrorInfo } from '@/utils/httpError'
import { API_BASE_URL, buildApiUrl } from './base'

const AUTH_SYNC_EVENT = 'auth-sync'

export const DEFAULT_API_TIMEOUT_MS = 60000
export const LONG_RUNNING_API_TIMEOUT_MS = 420000

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: DEFAULT_API_TIMEOUT_MS
})

request.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
let pendingRequests: Array<{ resolve: (value: unknown) => void; reject: (reason?: unknown) => void; request: InternalAxiosRequestConfig & { _retry?: boolean } }> = []

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
  } catch {
    return null
  }
}

function flushPendingRequests(token: string) {
  pendingRequests.forEach(({ resolve, request: originalRequest }) => {
    originalRequest.headers.Authorization = `Bearer ${token}`
    resolve(request(originalRequest))
  })
  pendingRequests = []
}

function rejectPendingRequests(error: unknown) {
  pendingRequests.forEach(({ reject }) => reject(error))
  pendingRequests = []
}

let isUnauthorizedRedirecting = false

function clearAuthState() {
  clearStoredAuth()
  broadcastAuthSync({ token: '', refreshToken: '', user: null })
}

function redirectToLogin(message = '登录已失效，请重新登录') {
  if (!isUnauthorizedRedirecting && window.location.pathname !== '/login') {
    isUnauthorizedRedirecting = true
    ElMessage.warning(message)
    router.replace({ path: '/login', query: { redirect: window.location.pathname } })
  }
}

request.interceptors.response.use(
  (response) => {
    isUnauthorizedRedirecting = false
    return response
  },
  async (error: AxiosError<{ detail?: string; message?: string }>) => {
    const { status, detail } = normalizeHttpErrorInfo(error, '请求失败')
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (status === 401 && originalRequest && !originalRequest._retry) {
      if (isRefreshing) {
        // 修复：为 pending 请求设置 _retry 标志，防止重试后再次 401 时触发重复刷新循环
        originalRequest._retry = true
        return new Promise((resolve, reject) => {
          pendingRequests.push({ resolve, reject, request: originalRequest })
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
      redirectToLogin(detail || '登录已失效，请重新登录')
      return Promise.reject(error)
    }

    if (status === 403) {
      ElMessage.warning(detail || '无权限执行该操作')
      return Promise.reject(error)
    }

    if (status === 404) {
      ElMessage.warning(detail || '请求资源不存在')
      return Promise.reject(error)
    }

    if (status === 422) {
      ElMessage.warning(detail || '请求参数校验失败')
      return Promise.reject(error)
    }

    if (status >= 500) {
      ElMessage.error(detail || '服务异常，请稍后重试')
      return Promise.reject(error)
    }

    ElMessage.error(detail || '请求失败')
    return Promise.reject(error)
  }
)

export async function requestData<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const res = await promise
  return res.data.data
}

export async function requestPageData<T>(promise: Promise<{ data: ApiResponse<unknown> }>): Promise<UnifiedPageResult<T>> {
  const res = await promise
  return normalizePageResult<T>(res.data.data)
}

export default request
