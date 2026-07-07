import { translate } from '@/i18n'
import { normalizeHttpErrorInfo } from '@/utils/httpError'

export type ErrorLevel = 'warning' | 'error'

export interface NormalizedError {
  status: number
  detail: string
  level: ErrorLevel
  showRetry: boolean
}

const t = translate

function tr(key: string, fallback: string): string {
  const translated = t(key)
  return translated === key ? fallback : translated
}

export const normalizeHttpError = (error: unknown, fallback: string): NormalizedError => {
  const { status, detail } = normalizeHttpErrorInfo(error, fallback)

  if (status === 401) return { status, detail: detail || tr('errorPolicy.sessionExpired', '登录状态失效，请重新登录'), level: 'warning', showRetry: false }
  if (status === 403) return { status, detail: detail || tr('errorPolicy.noPermission', '无权限执行该操作'), level: 'warning', showRetry: false }
  if (status === 404) return { status, detail: detail || tr('errorPolicy.notFound', '请求资源不存在'), level: 'warning', showRetry: true }
  if (status === 422) return { status, detail: detail || tr('errorPolicy.validationFailed', '请求参数校验失败'), level: 'warning', showRetry: false }
  if (status >= 500) return { status, detail: detail || tr('errorPolicy.serverError', '服务异常，请稍后重试'), level: 'error', showRetry: true }

  return { status, detail, level: 'error', showRetry: true }
}
