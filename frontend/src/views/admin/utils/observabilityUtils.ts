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
