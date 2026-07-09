// frontend/src/views/admin/AdminReportsPage.test.ts
import { describe, it, expect } from 'vitest'
import { isTerminalStatus, validateBatchExcelInput, defaultPdfForm } from './utils/reportsUtils'

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
