// frontend/src/views/user/UserReportsPage.test.ts
import { describe, it, expect } from 'vitest'
import { formatLabel, buildJsonBlob } from './utils/reportsUtils'

describe('UserReportsPage 逻辑', () => {
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
