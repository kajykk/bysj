/**
 * AdminDashboard 共享工具：类型、常量、纯函数。
 * 从原 AdminDashboard.vue 提取，保持行为一致。
 */

/** 统计卡片数据结构 */
export interface StatCard {
  key: string
  label: string
  value: string | number
  tone: 'primary' | 'warning' | 'danger' | 'success'
  trend: number
  trendType: 'success' | 'danger'
  sub: string
  action?: () => void
  actionText?: string
  actionType?: 'primary' | 'warning' | 'success' | 'info'
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
