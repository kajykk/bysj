export function maskSensitive(text: unknown, maxLen = 80): string {
  if (text == null) return ''
  const s = String(text)
  if (s.length <= maxLen) return s
  return s.slice(0, maxLen) + '…'
}

export function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'success') return 'success'
  if (status === 'fallback') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

export function computePage(offset: number, limit: number): number {
  return Math.floor(offset / limit) + 1
}
