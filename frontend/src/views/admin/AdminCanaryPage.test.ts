// frontend/src/views/admin/AdminCanaryPage.test.ts
import { describe, it, expect } from 'vitest'

export function availableActions(status: string): string[] {
  switch (status) {
    case 'running': return ['adjust', 'pause', 'rollback', 'complete']
    case 'paused': return ['adjust', 'resume', 'rollback']
    case 'completed': return []
    case 'rolled_back': return []
    default: return []
  }
}
export function validateTraffic(percent: number): { ok: boolean; error?: string } {
  if (!Number.isInteger(percent)) return { ok: false, error: '必须为整数' }
  if (percent < 1 || percent > 100) return { ok: false, error: '范围 1-100' }
  return { ok: true }
}
export function validateRollbackReason(reason: string): { ok: boolean; error?: string } {
  if (reason.trim().length < 1) return { ok: false, error: '原因必填' }
  if (reason.length > 500) return { ok: false, error: '最多 500 字' }
  return { ok: true }
}

describe('AdminCanaryPage 逻辑', () => {
  it('running 可 pause/rollback/complete/adjust', () => {
    expect(availableActions('running')).toEqual(['adjust', 'pause', 'rollback', 'complete'])
  })
  it('paused 可 resume/rollback/adjust', () => {
    expect(availableActions('paused')).toEqual(['adjust', 'resume', 'rollback'])
  })
  it('completed 无操作', () => {
    expect(availableActions('completed')).toEqual([])
  })
  it('validateTraffic 边界', () => {
    expect(validateTraffic(1).ok).toBe(true)
    expect(validateTraffic(100).ok).toBe(true)
    expect(validateTraffic(0).ok).toBe(false)
    expect(validateTraffic(101).ok).toBe(false)
  })
  it('validateRollbackReason 必填', () => {
    expect(validateRollbackReason('').ok).toBe(false)
    expect(validateRollbackReason('error rate').ok).toBe(true)
  })
})
