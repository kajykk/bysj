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
  // 后端会直接下发中文名称（如 持续焦虑/睡眠不足/数据质量）作为 feature/direction 值，
  // 此类键无需 i18n 查找，直接原样返回，避免 vue-i18n 大量 missing-key 警告。
  // I18N-01 修复：原实现检测的是拼接后的完整路径，中文键会连前缀整串返回，
  // 导致界面显示 riskFormatter.features.持续焦虑 之类的原始路径；改为检测原始键。
  if (/[\u4e00-\u9fff]/.test(fallback)) return fallback
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
 * 会作为 el-tag 的背景色传入，必须是具体色值；与浅色主题的
 * --risk-mild/moderate/high/critical 一一对应，改令牌时同步本表。
 */
export const RISK_SCORE_COLORS = {
  low: '#5a9e3a',      // 0-20: 绿色（低风险）
  mild: '#d4923a',     // 21-40: 橙色（轻度）
  moderate: '#d65a5a', // 41-60: 红色（中度）
  high: '#a82e28',     // 61+: 深红（较高）
} as const

/**
 * 结构化模态的本地回退阈值。
 *
 * 主路径应从后端预测响应的 `thresholds` 读取；本常量只在服务端未下发时兜底，
 * 且调用方必须在文案中显式标注「本地口径，服务端未下发」，不得静默混用。
 * 数值与 backend/app/core/risk_thresholds.py 的
 * `MODALITY_RISK_THRESHOLDS["structured"]` 保持一致（v1.23 校准分位点 20/70/93/97）。
 */
export const STRUCTURED_RISK_THRESHOLDS = {
  mild: 20,
  moderate: 70,
  high: 93,
  critical: 97,
} as const

export interface StructuredThresholds {
  mild: number
  moderate: number
  high: number
  critical: number
}

/**
 * 返回某个结构化风险等级对应的分数区间文案（含上下界）。
 * `thresholds` 应优先传入服务端下发值；缺省时才回退到本地常量。
 * `null` / 未判定返回空串，由调用方展示「待复核」文案。
 */
export function structuredScoreBand(
  level: number | null | undefined,
  thresholds: StructuredThresholds = STRUCTURED_RISK_THRESHOLDS
): string {
  if (level == null || !Number.isFinite(level)) return ''
  if (level <= 0) return `0–${thresholds.mild - 1}`
  if (level === 1) return `${thresholds.mild}–${thresholds.moderate - 1}`
  if (level === 2) return `${thresholds.moderate}–${thresholds.high - 1}`
  if (level === 3) return `${thresholds.high}–${thresholds.critical - 1}`
  return `≥${thresholds.critical}`
}

/** 中文顿号/斜杠风格的阈值串，用于界面解释文案。 */
export function formatThresholdValues(thresholds: StructuredThresholds): string {
  return `${thresholds.mild} / ${thresholds.moderate} / ${thresholds.high} / ${thresholds.critical}`
}

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
  const camel = snakeToCamel(key)
  // 归一化动态复核触发词：model_disagreement_43_points → modelDisagreement，
  // low_confidence_high_risk_text → lowConfidenceHighRisk，避免为数字/模态后缀枚举 key
  const normalized = camel
    .replace(/^modelDisagreement_\d+Points$/, 'modelDisagreement')
    .replace(/^lowConfidenceHighRisk.+$/, 'lowConfidenceHighRisk')
  return tr(`riskFormatter.features.${normalized}`, key)
}

/** 严重程度标签查找（i18n 化，替代原 severityLabelMap 常量） */
export function severityLabel(key: string | null | undefined): string {
  if (!key) return tr('riskFormatter.severity.unknown', 'Unknown')
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

/**
 * 等级标签（null 安全）。
 *
 * `risk_level=null` 表示「未判定/待复核」，绝不能退化成 0 级「无风险」——
 * 否则会把漏检伪装成正常。后端 risk_level 可空，调用方一律走本函数。
 */
export function riskLevelLabel(level: number | null | undefined): string {
  if (level == null || !Number.isFinite(level)) {
    return tr('riskFormatter.severity.pending', '待复核')
  }
  return severityFromLevel(level)
}

/** 人工复核原因的可读文案（后端下发 snake_case code，未知 code 原样回退） */
export function reviewReasonLabel(reason: string | null | undefined): string {
  if (!reason) return ''
  return tr(`riskFormatter.reviewReasons.${snakeToCamel(reason)}`, reason)
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
): 'success' | 'warning' | 'info' | 'danger' {
  if (!direction) return 'info'
  if (direction === 'negative' || direction === 'score_down' || direction === 'decrease') return 'success'
  if (direction === 'positive' || direction === 'score_up' || direction === 'increase') return 'danger'
  return 'warning'
}

/** 数组格式化为文本 */
export function formatArrayText(value: unknown, separator = ', '): string {
  if (!Array.isArray(value) || !value.length) return tr('riskFormatter.arrayEmpty', 'N/A')
  return value.map(item => String(item)).join(separator)
}
