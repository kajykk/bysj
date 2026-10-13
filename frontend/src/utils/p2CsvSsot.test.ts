import { describe, expect, it } from 'vitest'
import { csvEscape, sanitizeCellForExcel } from '@/utils/exportUtils'

describe('P2-32 remainder: csvEscape SSOT', () => {
  it('equals sanitize + quote chain', () => {
    for (const v of ['=SUM(A1)', 'hello', '+1+1', '@admin', 'a"b,c']) {
      expect(csvEscape(v)).toBe(`"${sanitizeCellForExcel(v).replace(/"/g, '""')}"`)
    }
  })
  it('neutralises formula injection (the MisclassifiedTable gap)', () => {
    expect(csvEscape('=SUM(A1)')).toBe(`"'=SUM(A1)"`)
  })
  it('accepts numbers (MisclassifiedTable score column)', () => {
    expect(csvEscape(0.92)).toBe('"0.92"')
    expect(csvEscape(0)).toBe('"0"')
  })
})
