/**
 * UserDashboard 共享工具：常量、类型、纯函数。
 * 从原 UserDashboard.vue 提取，保持行为一致。
 */
import type { DataHistoryItem } from '@/api/userTypes'

/** 严重程度 → i18n key 后缀映射 */
export const SEVERITY_LABEL_KEYS: Record<string, string> = {
  none: 'severityNone',
  mild: 'severityMild',
  moderate: 'severityModerate',
  high: 'severityHigh',
  critical: 'severityCritical',
  unknown: 'severityUnknown'
}

/** 严重程度 → el-tag type 映射 */
export const SEVERITY_TAG_TYPE_MAP: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
  none: 'info',
  mild: 'success',
  moderate: 'warning',
  high: 'danger',
  critical: 'danger'
}

/** 测评类型 → i18n key 后缀映射 */
export const ASSESSMENT_TYPE_LABEL_KEYS: Record<string, string> = {
  structured: 'assessmentStructured',
  text: 'assessmentText',
  physiological: 'assessmentPhysiological',
  physio: 'assessmentPhysio',
  record: 'assessmentRecord'
}

/** 风险等级 → i18n key 后缀映射（图表 tooltip） */
export const CHART_RISK_LEVEL_KEYS: Record<number, string> = {
  0: 'chartRiskLevel0',
  1: 'chartRiskLevel1',
  2: 'chartRiskLevel2',
  3: 'chartRiskLevel3',
  4: 'chartRiskLevel4'
}

/** 趋势方向 → i18n key 后缀映射（图表 tooltip） */
export const CHART_TREND_KEYS: Record<string, string> = {
  up: 'chartTrendUp',
  down: 'chartTrendDown',
  stable: 'trendStable'
}

/** 下一步行动卡片数据结构 */
export interface NextAction {
  label: string
  title: string
  description: string
  primaryText: string
  secondaryText: string
  secondaryPath: string
  action: () => void
}

/** 从 DataHistoryItem 提取测评类型 */
export const getAssessmentType = (item: DataHistoryItem | null) => {
  return (item?.data as { assessment_type?: string } | undefined)?.assessment_type
}

/** HTML 转义（图表 tooltip 安全） */
export const escapeHtml = (value: unknown) => {
  if (value === null || value === undefined) return ''
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
