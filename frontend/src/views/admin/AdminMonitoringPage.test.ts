// frontend/src/views/admin/AdminMonitoringPage.test.ts
import { describe, it, expect } from 'vitest'

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

describe('AdminMonitoringPage 逻辑', () => {
  it('maskSensitive 截断长文本', () => {
    expect(maskSensitive('x'.repeat(100), 10)).toBe('xxxxxxxxxx…')
    expect(maskSensitive('short', 10)).toBe('short')
  })
  it('statusTagType 映射', () => {
    expect(statusTagType('success')).toBe('success')
    expect(statusTagType('fallback')).toBe('warning')
    expect(statusTagType('failed')).toBe('danger')
  })
  it('computePage 分页计算', () => {
    expect(computePage(0, 20)).toBe(1)
    expect(computePage(20, 20)).toBe(2)
    expect(computePage(40, 20)).toBe(3)
  })
})
