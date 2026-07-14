/**
 * AdminSilences 共享工具：常量、类型、纯函数。
 * 从原 AdminSilencesPage.vue 提取，保持行为一致。
 */
import type { SilenceItem } from '@/api/alertsApi'

/** 静默规则状态信息 */
export interface SilenceStatusInfo {
  type: 'success' | 'info' | 'warning'
  label: string
}

/** 默认 matcher JSON 模板 */
export const DEFAULT_MATCHER_JSON = '{\n  "alertname": ""\n}'

/** 计算静默规则状态标签（含 i18n 文案） */
export const getSilenceStatus = (
  row: SilenceItem,
  t: (key: string) => string
): SilenceStatusInfo => {
  if (!row.is_active) return { type: 'info', label: t('adminSilences.statusInactive') }
  const now = Date.now()
  const start = row.starts_at ? new Date(row.starts_at).getTime() : 0
  const end = row.ends_at ? new Date(row.ends_at).getTime() : 0
  if (now < start) return { type: 'warning', label: t('adminSilences.statusPending') }
  if (now > end) return { type: 'info', label: t('adminSilences.statusExpired') }
  return { type: 'success', label: t('adminSilences.statusActive') }
}
