/**
 * 风险评估相关标签/格式化工具函数。
 *
 * TD-022 修复：从 UserRiskPage.vue 提取的纯函数和常量映射，
 * 便于单元测试和跨组件复用。
 *
 * i18n 化：所有用户可见的标签文案通过全局 i18n 实例翻译，
 * 支持运行时语言切换。
 */

import { translate } from '@/i18n'

/**
 * 在非组件文件中使用全局 i18n 实例翻译。
 * 如果 key 不存在则返回 fallback（保持与原 `|| key` 相同的降级行为）。
 */
const t = translate

function tr(key: string, fallback: string): string {
  const translated = t(key)
  // vue-i18n 对不存在的 key 返回 key 路径本身
  return translated === key ? fallback : translated
}

/**
 * 将后端 snake_case 名转为 camelCase 以匹配 i18n 键段命名规范。
 * 例如 `academic_pressure` → `academicPressure`，`anxiety_only_fallback` → `anxietyOnlyFallback`。
 */
function snakeToCamel(s: string): string {
  return s.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
}

/**
 * 风险分数阈值（与后端 RISK_LEVEL_THRESHOLDS 保持一致）。
 * P2-D 修复：消除前端魔法数字，集中管理阈值。
 */
export const RISK_SCORE_THRESHOLDS = {
  mild: 20,
  moderate: 40,
  high: 60,
} as const

/**
 * 风险等级对应的基础颜色。
 * P2-D 修复：消除前端魔法数字，集中管理颜色。
 */
export const RISK_SCORE_COLORS = {
  low: '#5a9e3a',      // 0-20: 绿色（低风险）
  mild: '#d4923a',     // 21-40: 橙色（轻度）
  moderate: '#d65a5a', // 41-60: 红色（中度）
  high: '#a82e28',     // 61+: 深红（较高）
} as const

/**
 * 根据风险分数返回对应的基础颜色。
 * P2-D 修复：消除 UserDashboard.vue 中的魔法数字。
 */
export function getRiskScoreColor(score: number): string {
  if (score <= RISK_SCORE_THRESHOLDS.mild) return RISK_SCORE_COLORS.low
  if (score <= RISK_SCORE_THRESHOLDS.moderate) return RISK_SCORE_COLORS.mild
  if (score <= RISK_SCORE_THRESHOLDS.high) return RISK_SCORE_COLORS.moderate
  return RISK_SCORE_COLORS.high
}

/** 特征字段标签查找（i18n 化，替代原 featureLabelMap 常量） */
export function featureLabel(key: string): string {
  return tr(`riskFormatter.features.${snakeToCamel(key)}`, key)
}

/** 严重程度标签查找（i18n 化，替代原 severityLabelMap 常量） */
export function severityLabel(key: string): string {
  return tr(`riskFormatter.severity.${key}`, key)
}

/** 模态标签查找（i18n 化，替代原 modalityLabelMap 常量） */
export function modalityLabel(key: string): string {
  return tr(`riskFormatter.modality.${key}`, key)
}

/** 根据数值等级返回严重程度标签 */
export function severityFromLevel(level: number): string {
  const keys = ['none', 'mild', 'moderate', 'high', 'critical']
  const key = keys[level]
  return key ? tr(`riskFormatter.severity.${key}`, 'Unknown') : tr('riskFormatter.severity.unknown', 'Unknown')
}

/** 路由族中文标签 */
export function routeFamilyLabel(family: string | null | undefined): string {
  if (!family) return tr('riskFormatter.routeFamily.unknown', 'Unknown route')
  return tr(`riskFormatter.routeFamily.${snakeToCamel(family)}`, family)
}

/** 路由族标签颜色类型 */
export function routeFamilyTagType(
  family: string | null | undefined
): 'success' | 'primary' | 'warning' | 'info' | 'danger' {
  if (!family) return 'info'
  switch (family) {
    case 'structured': return 'success'
    case 'lite': return 'primary'
    case 'anxiety_only': return 'warning'
    case 'insufficient': return 'danger'
    default: return 'info'
  }
}

/** 路由原因中文说明 */
export function routeReasonLabel(reason: string | null | undefined): string {
  if (!reason) return ''
  return tr(`riskFormatter.routeReason.${snakeToCamel(reason)}`, reason)
}

/** 置信度标签颜色类型 */
export function confidenceTagType(
  band: string | null | undefined
): 'success' | 'warning' | 'danger' | 'info' {
  if (!band) return 'info'
  switch (band) {
    case 'high': return 'success'
    case 'medium': return 'warning'
    case 'low': return 'danger'
    default: return 'info'
  }
}

/** 置信度中文标签 */
export function confidenceLabel(band: string | null | undefined): string {
  if (!band) return tr('riskFormatter.confidence.unknown', 'Unknown confidence')
  return tr(`riskFormatter.confidence.${band}`, band)
}

/** 因子方向中文标签 */
export function getFactorDirectionLabel(direction: string | undefined): string {
  if (!direction) return tr('riskFormatter.factorDirection.unknown', '未知')
  return tr(`riskFormatter.factorDirection.${snakeToCamel(direction)}`, direction)
}

/** 因子方向标签颜色类型 */
export function getFactorDirectionTagType(
  direction: string | undefined
): 'success' | 'warning' | 'danger' | 'info' {
  if (!direction) return 'info'
  if (direction === 'negative' || direction === 'score_down') return 'success'
  if (direction === 'positive' || direction === 'score_up') return 'danger'
  return 'warning'
}

/** 数组格式化为文本 */
export function formatArrayText(value: unknown, separator = ', '): string {
  if (!Array.isArray(value) || !value.length) return tr('riskFormatter.arrayEmpty', 'N/A')
  return value.map(item => String(item)).join(separator)
}
