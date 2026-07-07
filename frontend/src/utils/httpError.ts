import { isAxiosError } from 'axios'

export interface HttpErrorInfo {
  status: number
  detail: string
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
