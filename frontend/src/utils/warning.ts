import type { WarningItem } from '@/api/userTypes'
import i18n from '@/i18n'

export const WARNING_RISK_LEVELS = [1, 2, 3] as const
export type WarningRiskLevel = (typeof WARNING_RISK_LEVELS)[number]

export const WARNING_STATUS = ['pending', 'handled', 'ignored', 'escalated'] as const
export type WarningStatus = (typeof WARNING_STATUS)[number]

const RISK_LEVEL_TAG_TYPES: Record<number, 'success' | 'warning' | 'danger' | 'info'> = {
  1: 'success',
  2: 'warning',
  3: 'danger'
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
  1: 'warning.riskLevelLow',
  2: 'warning.riskLevelMedium',
  3: 'warning.riskLevelHigh'
}

const WARNING_STATUS_LABEL_KEYS: Record<WarningStatus, string> = {
  pending: 'warning.statusPending',
  handled: 'warning.statusHandled',
  ignored: 'warning.statusIgnored',
  // ISS-058: 升级状态
  escalated: 'warning.statusEscalated'
}

export function getWarningRiskLevelLabel(level: number) {
  const key = RISK_LEVEL_LABEL_KEYS[level]
  return key ? t(key) : t('warning.riskLevelUnknown', { level })
}

export function getWarningRiskLevelTagType(level: number) {
  return RISK_LEVEL_TAG_TYPES[level] || 'info'
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
