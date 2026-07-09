// frontend/src/views/admin/AdminObservabilityPage.test.ts
import { describe, it, expect } from 'vitest'

const MAX_RANGE_DAYS = 30

export function validateTimeRange(start: string, end: string): { ok: boolean; error?: string } {
  const s = new Date(start).getTime()
  const e = new Date(end).getTime()
  if (Number.isNaN(s) || Number.isNaN(e)) return { ok: false, error: '时间格式无效' }
  if (e < s) return { ok: false, error: '结束时间不能早于开始时间' }
  if ((e - s) / 86400000 > MAX_RANGE_DAYS) return { ok: false, error: '范围不能超过 30 天' }
  return { ok: true }
}

export function settleBlocks<T extends { key: string }>(results: PromiseSettledResult<T>[]): { fulfilled: T[]; rejected: string[] } {
  const fulfilled: T[] = []
  const rejected: string[] = []
  for (const r of results) {
    if (r.status === 'fulfilled') fulfilled.push(r.value)
    else rejected.push('block')
  }
  return { fulfilled, rejected }
}

describe('AdminObservabilityPage 逻辑', () => {
  it('validateTimeRange 合法', () => {
    expect(validateTimeRange('2026-07-01', '2026-07-08').ok).toBe(true)
  })
  it('validateTimeRange 超 30 天拒绝', () => {
    expect(validateTimeRange('2026-06-01', '2026-07-08').ok).toBe(false)
  })
  it('validateTimeRange 结束早于开始拒绝', () => {
    expect(validateTimeRange('2026-07-08', '2026-07-01').ok).toBe(false)
  })
  it('settleBlocks 分离成功与失败', () => {
    const r: PromiseSettledResult<{ key: string }>[] = [
      { status: 'fulfilled', value: { key: 'a' } },
      { status: 'rejected', reason: new Error('x') },
    ]
    const s = settleBlocks(r)
    expect(s.fulfilled).toHaveLength(1)
    expect(s.rejected).toHaveLength(1)
  })
})
