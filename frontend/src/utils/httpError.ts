import { isAxiosError } from 'axios'

export interface HttpErrorInfo {
  status: number
  detail: string
}

// ISS-106 修复：网络层错误（无 HTTP 响应）中文映射表，
// 避免把 axios 英文原文（timeout / Network Error / ECONNABORTED 等）直接暴露给用户
const NETWORK_ERROR_MAPPING: ReadonlyArray<{
  code: ReadonlyArray<string>
  pattern?: RegExp
  message: string
}> = [
  {
    code: ['ECONNABORTED'],
    pattern: /timeout/i,
    message: '请求超时，请重试',
  },
  {
    code: ['ERR_NETWORK', 'ERR_NETWORK_UNKNOWN'],
    pattern: /network error|failed to fetch|load failed/i,
    message: '网络连接失败，请检查网络设置',
  },
  {
    code: ['ECONNREFUSED', 'ECONNRESET', 'ENETUNREACH', 'ERR_CONNECTION_REFUSED', 'ERR_CONNECTION_RESET', 'ERR_CONNECTION_TIMED_OUT'],
    pattern: /connect econnrefused|connect econnreset|enetunreach/i,
    message: '网络连接异常，请稍后重试',
  },
]

export const getNetworkErrorMessage = (error: unknown): string | null => {
  const raw = error as { code?: unknown; message?: unknown } | null | undefined
  const code = typeof raw?.code === 'string' ? raw.code : ''
  const message = typeof raw?.message === 'string' ? raw.message : ''

  for (const entry of NETWORK_ERROR_MAPPING) {
    if (entry.code.includes(code)) return entry.message
    if (entry.pattern && entry.pattern.test(message)) return entry.message
  }
  return null
}

export const normalizeHttpErrorInfo = (error: unknown, fallback: string): HttpErrorInfo => {
  const raw = error as { response?: { status?: unknown; data?: { detail?: unknown; message?: unknown; error?: { message?: unknown } } }; message?: unknown } | null | undefined
  const response = raw?.response ?? (isAxiosError(error) ? error.response : undefined)
  const status = Number(response?.status ?? 0) || Number(raw?.response?.status ?? 0) || 0
  const detailRaw = response?.data?.detail ?? response?.data?.message ?? response?.data?.error?.message
  const errorMessage = raw?.message ?? (isAxiosError(error) ? error.message : undefined)
  const detail = typeof detailRaw === 'string' && detailRaw.trim()
    ? detailRaw
    : typeof errorMessage === 'string' && errorMessage.trim()
      ? errorMessage
      : fallback

  return { status, detail }
}
