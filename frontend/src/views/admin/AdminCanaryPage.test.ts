// frontend/src/views/admin/AdminCanaryPage.test.ts
import { describe, it, expect } from 'vitest'
import { availableActions, validateTraffic, validateRollbackReason } from './utils/canaryUtils'

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
