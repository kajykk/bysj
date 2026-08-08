import type { WarningItem } from '@/api/userTypes'
import i18n from '@/i18n'

export const WARNING_RISK_LEVELS = [0, 1, 2, 3, 4] as const
export type WarningRiskLevel = (typeof WARNING_RISK_LEVELS)[number]

export const WARNING_STATUS = ['pending', 'handled', 'ignored', 'escalated'] as const
export type WarningStatus = (typeof WARNING_STATUS)[number]

const RISK_LEVEL_TAG_TYPES: Record<number, 'success' | 'warning' | 'danger' | 'info'> = {
  0: 'info',
  1: 'success',
  2: 'warning',
  3: 'danger',
  4: 'danger'
}

// 后端 normalize_risk_level 的字符串标签 → 数值等级映射
const RISK_LEVEL_STRING_MAP: Record<string, number> = {
  none: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4
}

// 兼容后端实际返回的两种形态（用户/咨询师预警接口均返回字符串标签）：
// - 数值（旧契约 / 部分服务端）
// - 字符串标签（normalize_risk_level: none/low/medium/high/critical/unknown）
export function normalizeWarningRiskLevel(level: unknown): number {
  if (typeof level === 'number' && Number.isFinite(level)) {
    return Math.max(-1, Math.min(4, Math.round(level)))
  }
  if (typeof level === 'string') {
    const key = level.trim().toLowerCase()
    if (key in RISK_LEVEL_STRING_MAP) return RISK_LEVEL_STRING_MAP[key]
  }
  return -1
}

const WARNING_STATUS_TAG_TYPES: Record<WarningStatus, 'success' | 'warning' | 'info' | 'danger'> = {
  pending: 'warning',
  handled: 'success',
  ignored: 'info',
  // ISS-058: 升级状态用 danger 突出显示
  escalated: 'danger'
}

// ISS-i18n: 风险等级与状态标签改用 i18n 全局实例，支持多语言切换
const t = i18n.global.t.bind(i18n.global)

const RISK_LEVEL_LABEL_KEYS: Record<number, string> = {
  0: 'warning.riskLevelNone',
  1: 'warning.riskLevelLow',
  2: 'warning.riskLevelMedium',
  3: 'warning.riskLevelHigh',
  4: 'warning.riskLevelCritical'
}

const WARNING_STATUS_LABEL_KEYS: Record<WarningStatus, string> = {
  pending: 'warning.statusPending',
  handled: 'warning.statusHandled',
  ignored: 'warning.statusIgnored',
  // ISS-058: 升级状态
  escalated: 'warning.statusEscalated'
}

export function getWarningRiskLevelLabel(level: number | string) {
  const normalized = normalizeWarningRiskLevel(level)
  const key = RISK_LEVEL_LABEL_KEYS[normalized]
  return key ? t(key) : t('warning.riskLevelUnknown', { level })
}

export function getWarningRiskLevelTagType(level: number | string) {
  return RISK_LEVEL_TAG_TYPES[normalizeWarningRiskLevel(level)] || 'info'
}

export function getWarningStatusLabel(status: string) {
  const key = WARNING_STATUS_LABEL_KEYS[status as WarningStatus]
  return key ? t(key) : status
}

export function getWarningStatusTagType(status: string) {
  return WARNING_STATUS_TAG_TYPES[status as WarningStatus] || 'info'
}

export function formatWarningDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

export function isWarningHandled(row: Pick<WarningItem, 'status'>) {
  // ISS-058: escalated 也属于已处理状态，禁止重复操作
  return ['handled', 'ignored', 'escalated'].includes(String(row.status || '').toLowerCase())
}

// M-FIX-007: 处理人展示归一化.
// 用户端 /user/warnings 返回数值 counselor_id；咨询师端 /counselor/warnings
// 返回 "counselor#<id>" 字符串。统一剥离前缀返回数字，保证两处展示一致。
export function formatHandledBy(handled_by: number | string | null | undefined, fallback = '—'): string {
  if (handled_by === null || handled_by === undefined || handled_by === '') return fallback
  if (typeof handled_by === 'number') return String(handled_by)
  const m = /^counselor#(\d+)$/.exec(handled_by.trim())
  return m ? m[1] : handled_by
}
