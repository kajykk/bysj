import { isAxiosError } from 'axios'

export const getErrorDetail = (error: unknown, fallback: string): string => {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail
    const message = error.response?.data?.message
    if (typeof detail === 'string' && detail.trim()) return detail
    if (typeof message === 'string' && message.trim()) return message
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message
  }

  return fallback
}
