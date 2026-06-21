/**
 * 风险评估相关标签/格式化工具函数。
 *
 * TD-022 修复：从 UserRiskPage.vue 提取的纯函数和常量映射，
 * 便于单元测试和跨组件复用。
 */

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
  low: '#67c23a',      // 0-20: 绿色（低风险）
  mild: '#e6a23c',     // 21-40: 橙色（轻度）
  moderate: '#f56c6c', // 41-60: 红色（中度）
  high: '#c45656',     // 61+: 深红（较高）
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

/** 特征字段中文标签映射 */
export const featureLabelMap: Record<string, string> = {
  age: '年龄', gender: '性别', study_year: '年级', cgpa: 'GPA',
  stress_level: '压力水平', sleep_duration: '睡眠时长', social_support: '社会支持',
  financial_pressure: '经济压力', family_history: '家族史', academic_pressure: '学业压力',
  exercise_frequency: '运动频率', anxiety: '焦虑程度', panic_attack: '恐慌发作',
  treatment_seeking: '寻求治疗', is_student: '是否在校'
}

/** 严重程度中文标签映射 */
export const severityLabelMap: Record<string, string> = {
  none: '无风险', mild: '轻度', moderate: '中度', high: '较高', critical: '严重'
}

/** 模态中文标签映射 */
export const modalityLabelMap: Record<string, string> = {
  structured: '结构化',
  text: '文本',
  physiological: '生理',
  fused: '融合',
  questionnaire: '问卷'
}

/** 根据数值等级返回严重程度标签 */
export function severityFromLevel(level: number): string {
  const map: Record<number, string> = { 0: '无风险', 1: '轻度', 2: '中度', 3: '较高', 4: '严重' }
  return map[level] || '未知'
}

/** 路由族中文标签 */
export function routeFamilyLabel(family: string | null | undefined): string {
  if (!family) return '未知路由'
  switch (family) {
    case 'structured': return '结构化模型'
    case 'lite': return '轻量模型 (v1.25)'
    case 'anxiety_only': return '仅焦虑评估'
    case 'insufficient': return '信息不足'
    default: return family
  }
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
  switch (reason) {
    case 'full_features': return '特征覆盖充足，使用完整结构化模型'
    case 'lite_fallback': return '结构化特征不足，降级至轻量模型 (GAD-7 + 文本)'
    case 'anxiety_only_fallback': return '仅 GAD-7 可用，使用焦虑经验映射'
    case 'insufficient_data': return '数据不足，无法生成风险预测'
    default: return reason
  }
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
  if (!band) return '未知置信度'
  switch (band) {
    case 'high': return '高置信度'
    case 'medium': return '中等置信度'
    case 'low': return '低置信度'
    default: return band
  }
}

/** 因子方向中文标签 */
export function getFactorDirectionLabel(direction: string | undefined): string {
  if (!direction) return '未知'
  if (direction === 'positive') return '增加风险'
  if (direction === 'negative') return '降低风险'
  if (direction === 'score_up') return '分数上升'
  if (direction === 'score_down') return '分数下降'
  return direction
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
  if (!Array.isArray(value) || !value.length) return '暂无'
  return value.map(item => String(item)).join(separator)
}
