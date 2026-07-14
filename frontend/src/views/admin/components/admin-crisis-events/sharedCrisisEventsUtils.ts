/**
 * AdminCrisisEvents 共享工具：常量、类型、纯函数。
 * 从原 AdminCrisisEventsPage.vue 提取，保持行为一致。
 */
// ISS-012 修复：复用 riskFormatters 中的 getRiskScoreColor，统一阈值，避免硬编码颜色
import { getRiskScoreColor } from '@/utils/riskFormatters'

/** 触发来源 → el-tag type 映射 */
export const TRIGGER_SOURCE_TAG_MAP: Record<string, 'success' | 'warning' | 'info'> = {
  text: 'warning',
  fusion: 'info',
  manual: 'success'
}

/** 状态 → el-tag type 映射 */
export const STATUS_TAG_MAP: Record<string, 'danger' | 'warning' | 'info' | 'success'> = {
  detected: 'danger',
  reviewed: 'warning',
  escalated: 'danger',
  resolved: 'success'
}

/** 触发来源 → i18n key 后缀映射 */
export const TRIGGER_SOURCE_LABEL_KEYS: Record<string, string> = {
  text: 'triggerSource.text',
  fusion: 'triggerSource.fusion',
  manual: 'triggerSource.manual'
}

/** 状态 → i18n key 后缀映射 */
export const STATUS_LABEL_KEYS: Record<string, string> = {
  detected: 'status.detected',
  reviewed: 'status.reviewed',
  escalated: 'status.escalated',
  resolved: 'status.resolved'
}

// ISS-040 修复：根据危机分数返回风险等级文字标签
// 阈值与 getRiskScoreColor 保持一致，确保颜色与文字语义对齐
/** 危机分数 → 风险等级 i18n key 后缀映射（空串表示无分数） */
export const getScoreLevelKey = (score: number | null): string => {
  if (score == null) return ''
  if (score <= 20) return 'riskLevel.low'
  if (score <= 40) return 'riskLevel.mild'
  if (score <= 60) return 'riskLevel.moderate'
  return 'riskLevel.high'
}

/** 用户 ID 脱敏 */
export const maskUserId = (userId: number | string): string => {
  const s = String(userId)
  if (s.length <= 2) return s + '****'
  return s.slice(0, 2) + '****'
}

// ISS-012 修复：复用 riskFormatters.getRiskScoreColor，统一风险分数阈值与配色
// 本地仅保留对 null 的适配（getRiskScoreColor 入参为 number）
/** 危机分数颜色（复用 riskFormatters，仅适配 null） */
export const getScoreColor = (score: number | null): string => {
  if (score == null) return '#999'
  return getRiskScoreColor(score)
}

// ISS-055 修复：默认日期范围改为 getter 函数，每次查询/重置时重新计算，避免跨午夜后默认值过期
/** 默认日期范围：最近 30 天 */
export const getDefaultDateRange = (): string[] => {
  const now = new Date()
  const start = new Date(now.getTime() - 30 * 24 * 3600 * 1000)
  return [start.toISOString().slice(0, 10), now.toISOString().slice(0, 10)]
}

// ISS-072 修复：状态流转操作列 + 对话框逻辑
// 状态机：detected → reviewed → escalated → resolved
/** 状态机：是否可处理 */
export const canHandle = (status: string): boolean => ['detected', 'reviewed', 'escalated'].includes(status)

/** 状态机：是否可升级 */
export const canEscalate = (status: string): boolean => ['detected', 'reviewed'].includes(status)

/** 状态机：是否可关闭 */
export const canClose = (status: string): boolean => ['detected', 'reviewed', 'escalated'].includes(status)
