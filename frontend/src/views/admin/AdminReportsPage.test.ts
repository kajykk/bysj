// frontend/src/views/admin/AdminReportsPage.test.ts
import { describe, it, expect } from 'vitest'

export function isTerminalStatus(status: string): boolean {
  return status === 'completed' || status === 'failed'
}
export function validateBatchExcelInput(raw: string): { ok: boolean; data?: unknown[]; error?: string } {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'JSON 解析失败' }
  }
  if (!Array.isArray(parsed)) return { ok: false, error: 'data 必须为数组' }
  if (parsed.length > 1000) return { ok: false, error: 'data 最多 1000 行' }
  return { ok: true, data: parsed as unknown[] }
}
export function defaultPdfForm() {
  return { user_id: 0, user_name: '', risk_level: 1, risk_trend: 'stable', recommendations: [] as string[] }
}

describe('AdminReportsPage 逻辑', () => {
  it('isTerminalStatus 终态判定', () => {
    expect(isTerminalStatus('completed')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('running')).toBe(false)
    expect(isTerminalStatus('queued')).toBe(false)
  })
  it('validateBatchExcelInput 合法数组', () => {
    const r = validateBatchExcelInput('[{"a":1}]')
    expect(r.ok).toBe(true)
    expect(r.data).toHaveLength(1)
  })
  it('validateBatchExcelInput 非数组拒绝', () => {
    expect(validateBatchExcelInput('{}').ok).toBe(false)
  })
  it('validateBatchExcelInput 超 1000 行拒绝', () => {
    const big = JSON.stringify(Array(1001).fill({ a: 1 }))
    expect(validateBatchExcelInput(big).ok).toBe(false)
  })
  it('validateBatchExcelInput 非法 JSON 拒绝', () => {
    expect(validateBatchExcelInput('not json').ok).toBe(false)
  })
  it('defaultPdfForm 含必填 user_id', () => {
    const f = defaultPdfForm()
    expect(f).toHaveProperty('user_id')
    expect(f).toHaveProperty('recommendations')
  })
})
