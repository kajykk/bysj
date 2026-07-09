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
