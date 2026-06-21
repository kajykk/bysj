import type { WarningItem } from '@/api/userTypes'

export const WARNING_RISK_LEVELS = [1, 2, 3] as const
export type WarningRiskLevel = (typeof WARNING_RISK_LEVELS)[number]

export const WARNING_STATUS = ['pending', 'handled', 'ignored'] as const
export type WarningStatus = (typeof WARNING_STATUS)[number]

const RISK_LEVEL_LABELS: Record<number, string> = {
  1: '低',
  2: '中',
  3: '高'
}

const RISK_LEVEL_TAG_TYPES: Record<number, 'success' | 'warning' | 'danger' | 'info'> = {
  1: 'success',
  2: 'warning',
  3: 'danger'
}

const WARNING_STATUS_LABELS: Record<WarningStatus, string> = {
  pending: '待处理',
  handled: '已处理',
  ignored: '已忽略'
}

const WARNING_STATUS_TAG_TYPES: Record<WarningStatus, 'success' | 'warning' | 'info'> = {
  pending: 'warning',
  handled: 'success',
  ignored: 'info'
}

export function getWarningRiskLevelLabel(level: number) {
  return RISK_LEVEL_LABELS[level] || `等级 ${level}`
}

export function getWarningRiskLevelTagType(level: number) {
  return RISK_LEVEL_TAG_TYPES[level] || 'info'
}

export function getWarningStatusLabel(status: string) {
  return WARNING_STATUS_LABELS[status as WarningStatus] || status
}

export function getWarningStatusTagType(status: string) {
  return WARNING_STATUS_TAG_TYPES[status as WarningStatus] || 'info'
}

export function formatWarningDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

export function isWarningHandled(row: Pick<WarningItem, 'status'>) {
  return ['handled', 'ignored'].includes(String(row.status || '').toLowerCase())
}
