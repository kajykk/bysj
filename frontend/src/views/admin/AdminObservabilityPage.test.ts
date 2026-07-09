// frontend/src/views/admin/AdminObservabilityPage.test.ts
import { describe, it, expect } from 'vitest'
import { validateTimeRange, settleBlocks } from './utils/observabilityUtils'

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
