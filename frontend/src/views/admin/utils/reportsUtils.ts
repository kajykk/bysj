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
