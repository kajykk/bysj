/**
 * AdminDashboard 共享工具：类型、常量、纯函数。
 * 从原 AdminDashboard.vue 提取，保持行为一致。
 */

/** 指标语义：容量增长不是好消息，风险上升才是坏消息，干预完成度越高越好 */
export type MetricKind = 'capacity' | 'risk' | 'intervention'

/** el-tag 支持的语义类型（primary 作为中性色） */
export type TrendTone = 'primary' | 'success' | 'warning' | 'danger'

/** 统计卡片数据结构 */
export interface StatCard {
  key: string
  label: string
  value: string | number
  tone: 'primary' | 'neutral' | 'warning' | 'danger' | 'success'
  trend: number
  trendType: TrendTone
  sub: string
  action?: () => void
  actionText?: string
  actionType?: 'primary' | 'warning' | 'success' | 'info'
}

const TREND_TONES: Record<MetricKind, { up: TrendTone; down: TrendTone }> = {
  capacity: { up: 'primary', down: 'primary' },
  risk: { up: 'danger', down: 'success' },
  intervention: { up: 'success', down: 'warning' },
}

/** 环比颜色按指标语义查表，而不是按数值正负一刀切 */
export function trendToneFor(kind: MetricKind, delta: number): TrendTone {
  if (delta > 0) return TREND_TONES[kind].up
  if (delta < 0) return TREND_TONES[kind].down
  return 'primary'
}

/** 系统组件状态项 */
export interface ComponentStatusItem {
  key: string
  healthy: boolean
}

/** 系统组件 key → i18n key 映射（稳定 key 作为后端映射标识，显示名通过 i18n 渲染） */
export const COMPONENT_NAME_KEYS: Record<string, string> = {
  api: 'adminDashboard.componentApi',
  database: 'adminDashboard.componentDatabase',
  redis: 'adminDashboard.componentRedis',
  celery_worker: 'adminDashboard.componentQueue',
  storage: 'adminDashboard.componentStorage',
}

/**
 * 环比趋势百分比计算：与原 AdminDashboard.vue 中 userTrend/warningTrend 等逻辑一致。
 * 昨日为 0 时返回 0，避免除零。
 */
export const calcTrend = (current: number, previous: number): number => {
  if (previous === 0) return 0
  return Math.round(((current - previous) / previous) * 100)
}
