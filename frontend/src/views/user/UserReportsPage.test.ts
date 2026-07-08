// frontend/src/views/user/UserReportsPage.test.ts
import { describe, it, expect } from 'vitest'

// 提取的纯函数（与组件内一致）
export function parseFilename(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  const m = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
  return m ? decodeURIComponent(m[1]) : fallback
}
export function formatLabel(format: 'pdf' | 'csv' | 'json'): string {
  return { pdf: 'PDF 报告', csv: 'CSV 数据', json: 'JSON 数据' }[format]
}
export function buildJsonBlob(data: unknown): Blob {
  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
}

describe('UserReportsPage 逻辑', () => {
  it('parseFilename 从 Content-Disposition 解析', () => {
    expect(parseFilename('attachment; filename="risk.pdf"', 'fb.pdf')).toBe('risk.pdf')
    expect(parseFilename("attachment; filename*=UTF-8''r%C3%A9.csv", 'fb.csv')).toBe('ré.csv')
    expect(parseFilename(undefined, 'fb.pdf')).toBe('fb.pdf')
  })
  it('formatLabel 三格式映射', () => {
    expect(formatLabel('pdf')).toBe('PDF 报告')
    expect(formatLabel('csv')).toBe('CSV 数据')
    expect(formatLabel('json')).toBe('JSON 数据')
  })
  it('buildJsonBlob 生成 application/json', () => {
    const blob = buildJsonBlob({ a: 1 })
    expect(blob.type).toBe('application/json')
  })
})
